from __future__ import annotations

from typing import Any

from config import BINANCE_SYMBOL, KLINE_LIMIT, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, WEBHOOK_LOG_FILE
from engine.aux_filters import build_aux_filters_proxy
from engine.chart_indicators import build_chart_context
from engine.cooldown import SignalStateStore
from engine.indicators import enrich_klines
from engine.framework import build_htf_bias_context
from engine.liquidity import build_liquidity_context
from engine.key_zones import decide_key_zone_observation
from engine.late_filter import apply_late_filter
from engine.market_data import BinanceMarketDataClient
from engine.runtime_state import RuntimeStateStore
from engine.range_lock import build_range_lock_context
from engine.sweep_hunter import build_sweep_context, merge_sweep_into_liquidity
from engine.delta_profile import build_delta_profile_context, merge_delta_into_vp
from engine.ifvg import build_ifvg_context
from engine.structure import (
    build_dow_structure_context,
    build_structure_15m_context,
    build_structure_1h_context,
    build_structure_4h_context,
)
from engine.m15_w_bottom import (
    build_structure_15m_demand_context,
    build_structure_1h_demand_context,
    build_structure_4h_demand_context,
)
from engine.trend_matrix import build_trend_matrix_proxy
from engine.volume_profile import build_volume_profile_context
from engine.trend_messages import format_trend_message, should_send_alert_copy
from engine.trend_segments import decide_trend_segment
from engine.trend_snapshot import load_observation_state, load_trend_state, make_snapshot_key, save_observation_state, save_trend_state
from services.logger import get_logger
from services.telegram import TelegramSendError, send_telegram_message


class SMCTScanner:
    def __init__(self, symbol: str = BINANCE_SYMBOL):
        self.symbol = symbol
        self.market_data = BinanceMarketDataClient()
        self.state_store = SignalStateStore()
        self.runtime_state = RuntimeStateStore()
        self.logger = get_logger("scanner", WEBHOOK_LOG_FILE)

    def _fetch_enriched(self, interval: str) -> list[dict]:
        klines = self.market_data.get_klines(self.symbol, interval=interval, limit=KLINE_LIMIT)
        return enrich_klines(klines[:-1])

    def _htf_context(
        self,
        klines_4h: list[dict],
        direction_1h: str,
        *,
        liquidity: dict[str, Any] | None = None,
        msb: dict[str, Any] | None = None,
        ict: dict[str, Any] | None = None,
        chart: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # A short/partial feed cannot support the user's 4H framework.  Stay
        # neutral instead of falling back to the removed EMA model.
        if len(klines_4h) < 40:
            return {
                "h4_direction": "range",
                "h4_raw_direction": "neutral",
                "relation": "neutral",
                "text": "4H 数据不足，保持中性",
                "h4_strength": 0.0,
                "bias_scores": {"bull": 0.0, "bear": 0.0},
                "bias_evidence": [],
                "source": "insufficient_smc_ict_history",
            }
        return build_htf_bias_context(
            klines_4h,
            direction_1h,
            liquidity=liquidity,
            msb=msb,
            ict=ict,
            chart=chart,
        )

    def health_check(self) -> dict[str, Any]:
        return {
            "ok": True,
            "status": "ok",
            "symbol": self.symbol,
            "scanner": "SMCTScanner",
            "engine": "btc_smc_ict_chart_v1",
        }

    def healthcheck(self) -> dict[str, Any]:
        return self.health_check()

    def run_once(self) -> dict[str, Any]:
        try:
            klines_4h = self._fetch_enriched("4h")
            klines_1h = self._fetch_enriched("1h")
            liq = build_liquidity_context(klines_1h)
            chart_1h = build_chart_context(klines_1h)
            # ICT/MSB builders hard-deleted. msb shell carries OTE/fibonacci only.
            msb = {"direction": "neutral", "fibonacci": chart_1h.get("fibonacci", {})}
            ict: dict = {}
            matrix = build_trend_matrix_proxy(klines_1h)
            vp = build_volume_profile_context(klines_1h)
            aux = build_aux_filters_proxy(klines_1h, klines_4h)
            aux["volume_orderflow"] = chart_1h.get("volume_orderflow", {})
            aux["killzone"] = chart_1h.get("killzone", {})
            aux["fibonacci"] = chart_1h.get("fibonacci", {})
            liq_4h = build_liquidity_context(klines_4h)
            chart_4h = build_chart_context(klines_4h)
            msb_4h = {"direction": "neutral", "fibonacci": chart_4h.get("fibonacci", {})}
            ict_4h: dict = {}
            fib_trend = str((chart_1h.get("fibonacci") or {}).get("trend", "neutral"))
            direction_1h_source = fib_trend if fib_trend in {"bull", "bear"} else "neutral"
            htf = self._htf_context(
                klines_4h,
                "long" if direction_1h_source == "bull" else "short" if direction_1h_source == "bear" else "neutral",
                liquidity=liq_4h,
                msb=msb_4h,
                ict=ict_4h,
                chart=chart_4h,
            )
            # Evidence helpers (candle approx); merge into legacy liq/vp fields
            sweep = build_sweep_context(klines_1h)
            liq = merge_sweep_into_liquidity(liq, sweep)
            delta_profile = build_delta_profile_context(klines_1h)
            vp = merge_delta_into_vp(vp, delta_profile)
            ifvg = build_ifvg_context(klines_1h, timeframe="1h")
            # Per-TF structure: supply M-top (short aux) + independent demand W-bottom (long aux).
            # Each TF runs on its own closed bars + own IFVG zones — never copy 15m into 1H/4H.
            try:
                klines_15m = self._fetch_enriched("15m")
            except Exception as exc_15m:
                self.logger.warning("klines_15m_fetch_failed error=%s", exc_15m)
                klines_15m = []

            def _ifvg_supply_demand(ifvg_ctx: dict[str, Any]) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
                supply: list[tuple[float, float]] = []
                demand: list[tuple[float, float]] = []
                for z in list((ifvg_ctx or {}).get("zones") or []):
                    if not isinstance(z, dict) or z.get("invalidated") or not z.get("inverted"):
                        continue
                    if z.get("top") is None or z.get("bottom") is None:
                        continue
                    direction = int(z.get("direction") or 0)
                    band = (float(z["bottom"]), float(z["top"]))
                    if direction == 1:
                        supply.append(band)
                    elif direction == -1:
                        demand.append(band)
                return supply, demand

            supply_zones_1h, demand_zones_1h = _ifvg_supply_demand(ifvg)
            # 15m uses 1H inverted IFVG bands as proximate zones (same as prior tip).
            supply_zones_15m, demand_zones_15m = supply_zones_1h, demand_zones_1h
            try:
                ifvg_4h = build_ifvg_context(klines_4h, timeframe="4h")
            except Exception as exc_ifvg4:
                self.logger.warning("ifvg_4h_failed error=%s", exc_ifvg4)
                ifvg_4h = {"zones": [], "nearest_active": None, "approx": True, "timeframe": "4h"}
            supply_zones_4h, demand_zones_4h = _ifvg_supply_demand(ifvg_4h)

            def _safe_struct(label: str, timeframe: str, builder, klines, **kwargs):
                if not klines:
                    return {"approx": True, "timeframe": timeframe, "active": False, "reason": f"no_{timeframe}_klines"}
                try:
                    return builder(klines, **kwargs)
                except Exception as exc:
                    self.logger.warning("%s_failed error=%s", label, exc)
                    return {"approx": True, "timeframe": timeframe, "active": False, "reason": f"{label}_error"}

            structure_15m = _safe_struct(
                "structure_15m", "15m", build_structure_15m_context, klines_15m, supply_zones=supply_zones_15m
            )
            structure_15m_demand = _safe_struct(
                "structure_15m_demand",
                "15m",
                build_structure_15m_demand_context,
                klines_15m,
                demand_zones=demand_zones_15m,
            )
            structure_1h = _safe_struct(
                "structure_1h", "1h", build_structure_1h_context, klines_1h, supply_zones=supply_zones_1h
            )
            structure_1h_demand = _safe_struct(
                "structure_1h_demand",
                "1h",
                build_structure_1h_demand_context,
                klines_1h,
                demand_zones=demand_zones_1h,
            )
            structure_4h = _safe_struct(
                "structure_4h", "4h", build_structure_4h_context, klines_4h, supply_zones=supply_zones_4h
            )
            structure_4h_demand = _safe_struct(
                "structure_4h_demand",
                "4h",
                build_structure_4h_demand_context,
                klines_4h,
                demand_zones=demand_zones_4h,
            )
            range_lock = build_range_lock_context(klines_1h, htf, liq, msb, matrix, aux, vp, ict=ict)
            range_lock["imbalance"] = ifvg  # legacy side-channel; trial prefers evidence.ifvg
            # 1H Dow HH/HL/LH/LL (primary); 15m Dow is aux metadata only.
            try:
                structure_dow = build_dow_structure_context(klines_1h, timeframe="1h")
                if klines_15m:
                    structure_dow["aux_15m"] = build_dow_structure_context(
                        klines_15m, timeframe="15m", left=2, right=2
                    )
            except Exception as exc_dow:
                self.logger.warning("structure_dow_failed error=%s", exc_dow)
                structure_dow = {
                    "approx": True,
                    "timeframe": "1h",
                    "trend": "none",
                    "active_short_evidence": False,
                    "active_long_evidence": False,
                    "reason": "structure_dow_error",
                }
            evidence_bundle = {
                "auto_range": range_lock.get("auto_range"),
                "sweep": sweep,
                "delta_profile": delta_profile,
                "ifvg": ifvg,
                "structure_15m": structure_15m,
                "structure_15m_demand": structure_15m_demand,
                "structure_1h": structure_1h,
                "structure_1h_demand": structure_1h_demand,
                "structure_4h": structure_4h,
                "structure_4h_demand": structure_4h_demand,
                "structure_dow": structure_dow,
                "core_levels_filter": aux.get("core_levels_filter"),
            }
            trend_state = load_trend_state(self.symbol, "1h")
            decision = decide_trend_segment(self.symbol, "1h", htf, liq, msb, matrix, aux, trend_state=trend_state, vp=vp, ict=ict)

            observation_selected = False
            if not decision.get("should_alert"):
                try:
                    observation_state = load_observation_state(self.symbol, "1h")
                    observation = decide_key_zone_observation(
                        self.symbol,
                        "1h",
                        klines_1h,
                        htf,
                        liq,
                        msb,
                        matrix,
                        aux,
                        observation_state=observation_state,
                        vp=vp,
                        range_lock=range_lock,
                        ict=ict,
                        evidence_bundle=evidence_bundle,
                    )
                    if observation.get("observation_update") is not None and not observation.get("should_alert"):
                        save_observation_state(self.symbol, "1h", observation["observation_update"])
                    if observation.get("should_alert"):
                        decision = observation
                        observation_selected = True
                except Exception as obs_exc:
                    self.logger.warning("key_zone_observation_failed symbol=%s error=%s", self.symbol, obs_exc)

            decision = apply_late_filter(decision, klines_1h)
            if (
                observation_selected
                and not decision.get("should_alert")
                and decision.get("alert_type") in {"SECONDARY_CONFIRM_LOWER", "SECONDARY_CONFIRM_UPPER"}
                and decision.get("observation_update") is not None
            ):
                # A late/invalid secondary confirmation is terminal.  Clear its
                # pending state even though no Telegram message is sent.
                save_observation_state(self.symbol, "1h", decision["observation_update"])
            decision["evidence"] = evidence_bundle
            decision["signature"] = make_snapshot_key(decision)
            self.logger.info("trend_decision_debug symbol=%s payload=%s", self.symbol, decision)

            sent = 0
            if decision["should_alert"] and self.state_store.should_send(decision):
                if not should_send_alert_copy(decision):
                    # Kill 关键区观察 / 确认 / 二次确认 copy; keep scoring paths intact.
                    self.logger.info(
                        "alert_send_suppressed reason=non_trial_copy alert_type=%s",
                        decision.get("alert_type"),
                    )
                    if decision.get("observation_update") is not None:
                        save_observation_state(self.symbol, "1h", decision["observation_update"])
                    # Dedupe without Telegram delivery so the same non-trial
                    # observation does not re-enter the send path every scan.
                    self.state_store.mark_sent(decision)
                else:
                    msg = format_trend_message(decision)
                    try:
                        send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, msg)
                        self.state_store.mark_sent(decision)
                        self.runtime_state.mark_sent_signal(decision)
                        if decision.get("observation_update") is not None:
                            # Pending/confirmation state exists only for an alert
                            # that was actually delivered.  This prevents phantom
                            # second confirmations after Telegram failure or dedupe.
                            save_observation_state(self.symbol, "1h", decision["observation_update"])
                        if decision.get("alert_type") in {"BULLISH_STRUCTURE_SHIFT", "BEARISH_STRUCTURE_SHIFT"}:
                            save_trend_state(self.symbol, "1h", decision.get("direction", "neutral"), decision.get("signature", ""))
                        sent = 1
                    except TelegramSendError:
                        pass

            summary = {"decision": decision, "sent": sent}
            self.runtime_state.mark_scan(ok=True, symbol=self.symbol, summary=summary)
            return {"ok": True, "symbol": self.symbol, "sent": sent, "summary": summary}
        except Exception as exc:
            self.runtime_state.mark_scan(ok=False, symbol=self.symbol, summary={"error": str(exc)}, error=str(exc))
            self.logger.exception("scanner_failed symbol=%s error=%s", self.symbol, exc)
            try:
                from services.ops_status import notify_backend_error

                notify_backend_error("scanner.run_once", str(exc), state=self.runtime_state)
            except Exception as notify_exc:
                self.logger.warning("scanner_error_notify_failed error=%s", notify_exc)
            return {"ok": False, "symbol": self.symbol, "sent": 0, "error": str(exc)}
