from __future__ import annotations

import json
import os
import time
from typing import Any

from config import BINANCE_SYMBOL, KLINE_LIMIT, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, WEBHOOK_LOG_FILE
from engine.aux_filters import build_aux_filters_proxy
from engine.chart_indicators import build_chart_context
from engine.cooldown import SignalStateStore
from engine.indicators import enrich_klines
from engine.early_observation import early_observation_mode, evaluate_early_observation
from engine.early_observation_state import EarlyObservationStore
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
from engine.trend_matrix import build_trend_matrix_proxy
from engine.volume_profile import build_volume_profile_context
from engine.trend_messages import format_prealert_message, format_trend_message, should_send_alert_copy
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

    def _early_store(self, mode: str) -> EarlyObservationStore:
        path = os.getenv("SMCT_EARLY_OBSERVATION_STATE_FILE", "/opt/smct-alert/state/early_observation.sqlite3")
        return EarlyObservationStore(path + (".shadow" if mode == "shadow" else ""))

    def _run_early_observations(self, closed, htf, liq, msb, matrix, aux, vp, range_lock, evidence, *, mode):
        if mode == "off":
            return {"sent": 0, "decisions": []}
        store = self._early_store(mode)
        sent = 0
        decisions = []
        try:
            # The 1H observation wins simultaneous same-area source candidates.
            for timeframe in ("1h", "15m"):
                raw = self.market_data.get_klines(self.symbol, interval=timeframe, limit=KLINE_LIMIT)
                now_ms = int(time.time()*1000)
                d = evaluate_early_observation(
                    self.symbol, timeframe, raw, closed, htf, liq, msb, matrix,
                    aux, vp, range_lock, evidence, now_ms=now_ms,
                    observation_state=load_observation_state(self.symbol, "1h") if timeframe == "1h" else {},
                )
                if d["should_alert"]:
                    d["delivery_eligible"] = store.reserve(d, now_ms)
                    if d["delivery_eligible"]:
                        if mode == "shadow":
                            store.delivered(d)  # shadow ledger only
                        else:
                            msg = format_prealert_message(d) if timeframe == "15m" else format_trend_message(d)
                            try:
                                send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, msg)
                            except TelegramSendError:
                                # Unknown transport outcome: retain reservation;
                                # never build formal pending state from this lane.
                                d["delivery_outcome"] = "unknown_reserved"
                            else:
                                store.delivered(d)
                                sent += 1
                                d["delivery_outcome"] = "delivered"
                self.logger.info("early_observation mode=%s payload=%s", mode, json.dumps(d, ensure_ascii=False))
                decisions.append(d)
        finally:
            store.close()
        return {"sent": sent, "decisions": decisions}

    def run_once(self, *, shadow: bool = False) -> dict[str, Any]:
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
            range_lock = build_range_lock_context(klines_1h, htf, liq, msb, matrix, aux, vp, ict=ict)
            range_lock["imbalance"] = ifvg  # legacy side-channel; trial prefers evidence.ifvg
            evidence_bundle = {
                "auto_range": range_lock.get("auto_range"),
                "sweep": sweep,
                "delta_profile": delta_profile,
                "ifvg": ifvg,
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
                    if observation.get("observation_update") is not None and not observation.get("should_alert") and not shadow:
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
                if not shadow:
                    save_observation_state(self.symbol, "1h", decision["observation_update"])
            decision["evidence"] = evidence_bundle
            decision["signature"] = make_snapshot_key(decision)
            self.logger.info("trend_decision_debug symbol=%s payload=%s", self.symbol, decision)

            mode = "shadow" if shadow else early_observation_mode()
            already_observed = False
            if mode == "live" and decision["should_alert"] and should_send_alert_copy(decision):
                try:
                    ledger = self._early_store(mode)
                    try:
                        already_observed = ledger.already_observed_close(decision, int(klines_1h[-1]["open_time"]))
                    finally:
                        ledger.close()
                except Exception as ledger_exc:
                    self.logger.warning("early_close_dedupe_unavailable error=%s", ledger_exc)
                if already_observed:
                    self.logger.info("alert_send_suppressed reason=already_observed_forming_close")
            sent = 0
            if not shadow and not already_observed and decision["should_alert"] and self.state_store.should_send(decision):
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

            early = {"sent": 0, "decisions": []}
            if not (decision["should_alert"] and should_send_alert_copy(decision)):
                try:
                    early = self._run_early_observations(
                        klines_1h, htf, liq, msb, matrix, aux, vp, range_lock, evidence_bundle, mode=mode)
                except Exception as early_exc:
                    # Optional data/ledger failure cannot block closed 1H scans.
                    self.logger.warning("early_observation_failed error=%s", early_exc)
                    early["error"] = str(early_exc)
            sent += early["sent"]
            summary = {"decision": decision, "sent": sent, "early_observation": early}
            if not shadow:
                self.runtime_state.mark_scan(ok=True, symbol=self.symbol, summary=summary)
            return {"ok": True, "symbol": self.symbol, "sent": sent, "summary": summary}
        except Exception as exc:
            if not shadow:
                self.runtime_state.mark_scan(ok=False, symbol=self.symbol, summary={"error": str(exc)}, error=str(exc))
            self.logger.exception("scanner_failed symbol=%s error=%s", self.symbol, exc)
            try:
                from services.ops_status import notify_backend_error

                if not shadow:
                    notify_backend_error("scanner.run_once", str(exc), state=self.runtime_state)
            except Exception as notify_exc:
                self.logger.warning("scanner_error_notify_failed error=%s", notify_exc)
            return {"ok": False, "symbol": self.symbol, "sent": 0, "error": str(exc)}
