from __future__ import annotations

from typing import Any

from config import BINANCE_SYMBOL, KLINE_LIMIT, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, WEBHOOK_LOG_FILE
from engine.aux_filters import build_aux_filters_proxy
from engine.chart_indicators import build_chart_context
from engine.cooldown import SignalStateStore
from engine.indicators import enrich_klines
from engine.framework import build_htf_bias_context
from engine.ict_ob import build_ict_ob_context
from engine.liquidity import build_liquidity_context
from engine.key_zones import decide_key_zone_observation
from engine.late_filter import apply_late_filter
from engine.market_data import BinanceMarketDataClient
from engine.msb_ob import build_msb_ob_context
from engine.runtime_state import RuntimeStateStore
from engine.range_lock import build_range_lock_context
from engine.trend_matrix import build_trend_matrix_proxy
from engine.volume_profile import build_volume_profile_context
from engine.trend_messages import format_trend_message
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
            msb = build_msb_ob_context(klines_1h, liq)
            ict = build_ict_ob_context(klines_1h)
            chart_1h = build_chart_context(klines_1h)
            msb["fibonacci"] = chart_1h.get("fibonacci", {})
            msb["classic_market"] = chart_1h.get("classic_market", {})
            ict["killzone"] = chart_1h.get("killzone", {})
            matrix = build_trend_matrix_proxy(klines_1h)
            vp = build_volume_profile_context(klines_1h)
            aux = build_aux_filters_proxy(klines_1h, klines_4h)
            aux["volume_orderflow"] = chart_1h.get("volume_orderflow", {})
            aux["killzone"] = chart_1h.get("killzone", {})
            aux["fibonacci"] = chart_1h.get("fibonacci", {})
            liq_4h = build_liquidity_context(klines_4h)
            msb_4h = build_msb_ob_context(klines_4h, liq_4h)
            ict_4h = build_ict_ob_context(klines_4h)
            chart_4h = build_chart_context(klines_4h)
            htf = self._htf_context(
                klines_4h,
                "long" if msb["direction"] == "bull" else "short" if msb["direction"] == "bear" else "neutral",
                liquidity=liq_4h,
                msb=msb_4h,
                ict=ict_4h,
                chart=chart_4h,
            )
            range_lock = build_range_lock_context(klines_1h, htf, liq, msb, matrix, aux, vp, ict=ict)
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
            decision["signature"] = make_snapshot_key(decision)
            self.logger.info("trend_decision_debug symbol=%s payload=%s", self.symbol, decision)

            sent = 0
            if decision["should_alert"] and self.state_store.should_send(decision):
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
            self.runtime_state.mark_scan(ok=False, symbol=self.symbol, summary={"error": str(exc)})
            self.logger.exception("scanner_failed symbol=%s error=%s", self.symbol, exc)
            return {"ok": False, "symbol": self.symbol, "sent": 0, "error": str(exc)}
