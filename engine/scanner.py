import time

from config import (
    ALERT_COOLDOWN_SECONDS,
    BINANCE_SYMBOL,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    WEBHOOK_LOG_FILE,
)
from engine.cooldown import CooldownStore
from engine.indicators import enrich_klines
from engine.market_data import BinanceMarketDataClient
from engine.signals import detect_signals
from services.logger import get_logger
from services.telegram import format_alert_message, send_telegram_message


class SMCTScanner:
    def __init__(self, symbol: str = BINANCE_SYMBOL):
        self.symbol = symbol
        self.market_data = BinanceMarketDataClient()
        self.cooldown = CooldownStore(ALERT_COOLDOWN_SECONDS)
        self.logger = get_logger("scanner", WEBHOOK_LOG_FILE)

    def _fetch_enriched(self, interval: str) -> list[dict]:
        klines = self.market_data.get_klines(self.symbol, interval=interval, limit=300)
        # 只使用已收盘K线
        return enrich_klines(klines[:-1])

    def scan_once(self) -> dict:
        try:
            klines_4h = self._fetch_enriched("4h")
            klines_1h = self._fetch_enriched("1h")
            klines_15m = self._fetch_enriched("15m")
            signals = detect_signals(self.symbol, klines_4h, klines_1h, klines_15m)
            if not signals:
                self.logger.info("scan_no_signal symbol=%s", self.symbol)
                return {"ok": True, "signal": None}

            top = signals[0]
            key = (top["symbol"], top["timeframe"], top["signal"])
            if self.cooldown.is_in_cooldown(key):
                self.logger.info("scan_cooldown_skip symbol=%s signal=%s", top["symbol"], top["signal"])
                return {"ok": True, "signal": None, "reason": "cooldown"}

            text = format_alert_message(
                signal=top["signal"],
                symbol=top["symbol"],
                timeframe=top["timeframe"],
                context=top["context"],
                trigger=top["trigger"],
                source="SMCT Engine",
            )
            telegram_result = send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, text)
            self.cooldown.mark_sent(key)
            self.logger.info("scan_signal_sent symbol=%s signal=%s", top["symbol"], top["signal"])
            return {"ok": True, "signal": top["signal"], "telegram_result": telegram_result}
        except Exception as exc:
            self.logger.exception("scan_failed error=%s", exc)
            return {"ok": False, "error": str(exc)}

    def run_forever(self, interval_seconds: int):
        self.logger.info("scanner_started symbol=%s interval=%s", self.symbol, interval_seconds)
        while True:
            self.scan_once()
            time.sleep(interval_seconds)
