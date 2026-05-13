from __future__ import annotations

from typing import Any

from config import BINANCE_SYMBOL, KLINE_LIMIT, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, WEBHOOK_LOG_FILE
from engine.aux_filters import build_aux_filters_proxy
from engine.cooldown import SignalStateStore
from engine.indicators import enrich_klines
from engine.liquidity import build_liquidity_context
from engine.market_data import BinanceMarketDataClient
from engine.msb_ob import build_msb_ob_context
from engine.runtime_state import RuntimeStateStore
from engine.trend_matrix import build_trend_matrix_proxy
from engine.trend_messages import format_trend_message
from engine.trend_segments import decide_trend_segment
from engine.trend_snapshot import load_trend_state, make_snapshot_key, save_trend_state
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

    def _htf_context(self, klines_4h: list[dict], direction_1h: str) -> dict[str, Any]:
        h4 = "bull" if float(klines_4h[-1].get("ema10", 0)) > float(klines_4h[-1].get("ema20", 0)) else "bear"
        if direction_1h == "neutral":
            relation = "neutral"
        else:
            relation = "aligned" if (h4 == "bull" and direction_1h == "long") or (h4 == "bear" and direction_1h == "short") else "counter"
            macd = float(klines_4h[-1].get("macd", 0))
            if relation == "counter" and ((h4 == "bull" and macd > 80) or (h4 == "bear" and macd < -80)):
                relation = "strong_counter"
        text = "4H 偏多" if h4 == "bull" else "4H 偏空"
        return {"h4_direction": h4, "relation": relation, "text": text}

    def run_once(self) -> dict[str, Any]:
        try:
            klines_4h = self._fetch_enriched("4h")
            klines_1h = self._fetch_enriched("1h")
            liq = build_liquidity_context(klines_1h)
            msb = build_msb_ob_context(klines_1h, liq)
            matrix = build_trend_matrix_proxy(klines_1h)
            aux = build_aux_filters_proxy(klines_1h, klines_4h)
            htf = self._htf_context(klines_4h, "long" if msb["direction"] == "bull" else "short" if msb["direction"] == "bear" else "neutral")
            trend_state = load_trend_state(self.symbol, "1h")
            decision = decide_trend_segment(self.symbol, "1h", htf, liq, msb, matrix, aux, trend_state=trend_state)
            decision["signature"] = make_snapshot_key(decision)
            self.logger.info("trend_decision_debug symbol=%s payload=%s", self.symbol, decision)

            sent = 0
            if decision["should_alert"] and self.state_store.should_send(decision):
                msg = format_trend_message(decision)
                try:
                    send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, msg)
                    self.state_store.mark_sent(decision)
                    self.runtime_state.mark_sent_signal(decision)
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
