import time

from config import (
    BINANCE_SYMBOL,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    WEBHOOK_LOG_FILE,
)
from engine.cooldown import SignalStateStore
from engine.indicators import enrich_klines
from engine.market_data import BinanceMarketDataClient
from engine.signals import detect_signals
from services.logger import get_logger
from services.telegram import format_engine_message, send_telegram_message


class SMCTScanner:
    def __init__(self, symbol: str = BINANCE_SYMBOL):
        self.symbol = symbol
        self.market_data = BinanceMarketDataClient()
        self.state_store = SignalStateStore()
        self.logger = get_logger("scanner", WEBHOOK_LOG_FILE)

    def _fetch_enriched(self, interval: str) -> list[dict]:
        klines = self.market_data.get_klines(self.symbol, interval=interval, limit=300)
        return enrich_klines(klines[:-1])

    def scan_once(self) -> dict:
        try:
            klines_1d = self._fetch_enriched("1d")
            klines_4h = self._fetch_enriched("4h")
            klines_1h = self._fetch_enriched("1h")
            klines_15m = self._fetch_enriched("15m")

            signal_result = detect_signals(
                self.symbol,
                klines_1d,
                klines_4h,
                klines_1h,
                klines_15m,
            )
            signals = signal_result["signals"]
            near_miss_signals = signal_result["near_miss_signals"]
            blocked_reasons = signal_result["blocked_reasons"]

            if not signals:
                self.logger.info(
                    "scan_no_signal symbol=%s near_miss_signals=%s blocked_reasons=%s",
                    self.symbol,
                    near_miss_signals,
                    blocked_reasons,
                )
                return {
                    "ok": True,
                    "signal": None,
                    "near_miss_signals": near_miss_signals,
                    "blocked_reasons": blocked_reasons,
                }

            sent_signals = []
            for signal in signals:
                if not self.state_store.should_send(signal):
                    self.logger.info(
                        "scan_state_skip symbol=%s signal=%s direction=%s",
                        signal["symbol"],
                        signal["signal"],
                        signal["direction"],
                    )
                    continue

                text = format_engine_message(
                    signal=signal["signal"],
                    symbol=signal["symbol"],
                    timeframe=signal["timeframe"],
                    priority=signal["priority"],
                    price=signal["price"],
                    trend_1h=signal["trend_1h"],
                    status=signal["status"],
                )
                telegram_result = send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, text)
                self.state_store.mark_sent(signal)
                sent_signals.append({"signal": signal["signal"], "telegram_result": telegram_result})
                self.logger.info("scan_signal_sent symbol=%s signal=%s", signal["symbol"], signal["signal"])

            self.logger.info(
                "scan_summary symbol=%s sent_signals=%s near_miss_signals=%s blocked_reasons=%s",
                self.symbol,
                sent_signals,
                near_miss_signals,
                blocked_reasons,
            )

            if not sent_signals:
                return {
                    "ok": True,
                    "signal": None,
                    "reason": "state_dedup",
                    "near_miss_signals": near_miss_signals,
                    "blocked_reasons": blocked_reasons,
                }

            return {
                "ok": True,
                "sent": sent_signals,
                "near_miss_signals": near_miss_signals,
                "blocked_reasons": blocked_reasons,
            }

        except Exception as exc:
            self.logger.exception("scan_failed error=%s", exc)
            return {"ok": False, "error": str(exc)}

    def run_forever(self, interval_seconds: int):
        self.logger.info("scanner_started symbol=%s interval=%s", self.symbol, interval_seconds)
        while True:
            self.scan_once()
            time.sleep(interval_seconds)
