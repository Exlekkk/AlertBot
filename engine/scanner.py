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
from engine.opportunity_watch import detect_opening_watch
from engine.signals import detect_signals
from services.logger import get_logger
from services.telegram import format_engine_message, send_telegram_message


class SMCTScanner:
    def __init__(self, symbol: str = BINANCE_SYMBOL):
        self.symbol = symbol
        self.market_data = BinanceMarketDataClient()
        self.state_store = SignalStateStore()
        self.logger = get_logger("scanner", WEBHOOK_LOG_FILE)
        self.watch_state = {"direction": None, "level": 0, "signature": "", "quiet": 0}

    def _fetch_enriched(self, interval: str) -> list[dict]:
        klines = self.market_data.get_klines(self.symbol, interval=interval, limit=300)
        return enrich_klines(klines[:-1])

    def _should_send_watch(self, signal: dict) -> bool:
        direction = signal["direction"]
        level = signal.get("level", 0)
        signature = signal.get("signature", "")

        prev_direction = self.watch_state["direction"]
        prev_level = self.watch_state["level"]
        prev_signature = self.watch_state["signature"]

        should_send = False
        if prev_direction != direction:
            should_send = True
        elif level > prev_level:
            should_send = True
        elif level == 4 and signature != prev_signature:
            should_send = True

        if should_send:
            self.watch_state.update(
                {
                    "direction": direction,
                    "level": level,
                    "signature": signature,
                    "quiet": 0,
                }
            )
        return should_send

    def _mark_watch_quiet(self):
        self.watch_state["quiet"] += 1
        if self.watch_state["quiet"] >= 3:
            self.watch_state = {"direction": None, "level": 0, "signature": "", "quiet": 0}

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

            watch_sent = []
            watch_signals = []
            if not signals:
                watch_signals = detect_opening_watch(self.symbol, klines_1d, klines_4h, klines_1h, klines_15m)
                if watch_signals:
                    for signal in watch_signals:
                        if not self._should_send_watch(signal):
                            continue
                        telegram_result = send_telegram_message(
                            TELEGRAM_BOT_TOKEN,
                            TELEGRAM_CHAT_ID,
                            signal["text"],
                        )
                        watch_sent.append({"signal": signal["signal"], "telegram_result": telegram_result})
                        self.logger.info(
                            "scan_watch_sent symbol=%s signal=%s direction=%s level=%s signature=%s",
                            signal["symbol"],
                            signal["signal"],
                            signal["direction"],
                            signal.get("level"),
                            signal.get("signature"),
                        )
                else:
                    self._mark_watch_quiet()
            else:
                self.watch_state = {"direction": None, "level": 0, "signature": "", "quiet": 0}

            if not signals and not watch_sent:
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

            self.logger.info(
                "scan_summary symbol=%s sent_signals=%s watch_sent=%s near_miss_signals=%s blocked_reasons=%s",
                self.symbol,
                sent_signals,
                watch_sent,
                near_miss_signals,
                blocked_reasons,
            )

            if not sent_signals and not watch_sent:
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
                "watch_sent": watch_sent,
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
