from __future__ import annotations

import time

from config import BINANCE_SYMBOL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, WEBHOOK_LOG_FILE
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

    @staticmethod
    def _safe_band(low: float, high: float) -> tuple[float, float]:
        low = float(low)
        high = float(high)
        if low > high:
            low, high = high, low
        if abs(high - low) < max(abs(high) * 0.0008, 8.0):
            pad = max(abs(high) * 0.0012, 12.0)
            low -= pad * 0.5
            high += pad * 0.5
        return round(low, 2), round(high, 2)

    def _build_entry_zone(self, signal: dict, klines_15m: list[dict]) -> tuple[float, float]:
        zone_low = signal.get("zone_low")
        zone_high = signal.get("zone_high")
        if zone_low is not None and zone_high is not None:
            return self._safe_band(zone_low, zone_high)

        latest = klines_15m[-1]
        recent_6 = klines_15m[-6:]
        recent_8 = klines_15m[-8:]

        price = float(signal["price"])
        atr = max(float(latest.get("atr", 0.0)), price * 0.0015)
        ema10 = float(latest["ema10"])
        ema20 = float(latest["ema20"])
        recent_support = min(float(k["low"]) for k in recent_8)
        recent_resistance = max(float(k["high"]) for k in recent_8)
        local_reclaim = max(float(k["close"]) for k in recent_6[:-1]) if len(recent_6) > 1 else price
        local_reject = min(float(k["close"]) for k in recent_6[:-1]) if len(recent_6) > 1 else price

        signal_name = signal["signal"]

        if signal_name == "A_LONG":
            return self._safe_band(min(ema10, ema20, price - atr * 0.35), max(ema10, ema20, price - atr * 0.05))
        if signal_name == "A_SHORT":
            return self._safe_band(min(ema10, ema20, price + atr * 0.05), max(ema10, ema20, price + atr * 0.35))
        if signal_name == "B_PULLBACK_LONG":
            return self._safe_band(min(ema10, ema20, recent_support) - atr * 0.10, max(ema10, ema20, local_reclaim) + atr * 0.08)
        if signal_name == "B_PULLBACK_SHORT":
            return self._safe_band(min(ema10, ema20, local_reject) - atr * 0.08, max(ema10, ema20, recent_resistance) + atr * 0.10)
        if signal_name == "C_LEFT_LONG":
            return self._safe_band(min(recent_support, ema20) - atr * 0.18, max(ema10, ema20) + atr * 0.10)
        if signal_name == "C_LEFT_SHORT":
            return self._safe_band(min(ema10, ema20) - atr * 0.10, max(recent_resistance, ema20) + atr * 0.18)
        if signal_name == "X_BREAKOUT_LONG":
            breakout_level = float(signal.get("breakout_level") or recent_resistance)
            return self._safe_band(max(ema10, breakout_level - atr * 0.55), max(price, breakout_level + atr * 0.35))
        if signal_name == "X_BREAKOUT_SHORT":
            breakout_level = float(signal.get("breakout_level") or recent_support)
            return self._safe_band(min(price, breakout_level - atr * 0.35), min(ema10, breakout_level + atr * 0.55))
        return self._safe_band(price - atr * 0.12, price + atr * 0.12)

    def health_check(self) -> dict:
        klines_1d = self._fetch_enriched("1d")
        klines_4h = self._fetch_enriched("4h")
        klines_1h = self._fetch_enriched("1h")
        klines_15m = self._fetch_enriched("15m")
        signal_result = detect_signals(self.symbol, klines_1d, klines_4h, klines_1h, klines_15m)
        return {
            "ok": True,
            "symbol": self.symbol,
            "bars": {
                "1d": len(klines_1d),
                "4h": len(klines_4h),
                "1h": len(klines_1h),
                "15m": len(klines_15m),
            },
            "signals_checked": len(signal_result.get("signals", [])),
            "watch_checked": 0,
        }

    def scan_once(self) -> dict:
        try:
            klines_1d = self._fetch_enriched("1d")
            klines_4h = self._fetch_enriched("4h")
            klines_1h = self._fetch_enriched("1h")
            klines_15m = self._fetch_enriched("15m")

            signal_result = detect_signals(self.symbol, klines_1d, klines_4h, klines_1h, klines_15m)
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

                entry_zone_low, entry_zone_high = self._build_entry_zone(signal, klines_15m)
                text = format_engine_message(
                    signal=signal["signal"],
                    symbol=signal["symbol"],
                    timeframe=signal["timeframe"],
                    priority=signal["priority"],
                    price=signal["price"],
                    trend_1h=signal["trend_1h"],
                    status=signal["status"],
                    entry_zone_low=entry_zone_low,
                    entry_zone_high=entry_zone_high,
                    start_window_text=signal.get("start_window_text"),
                )
                telegram_result = send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, text)
                self.state_store.mark_sent(signal)
                sent_signals.append(
                    {
                        "signal": signal["signal"],
                        "entry_zone": [entry_zone_low, entry_zone_high],
                        "telegram_result": telegram_result,
                    }
                )
                self.logger.info(
                    "scan_signal_sent symbol=%s signal=%s entry_zone=[%.2f, %.2f] basis=%s",
                    signal["symbol"],
                    signal["signal"],
                    entry_zone_low,
                    entry_zone_high,
                    signal.get("structure_basis"),
                )

            if not sent_signals:
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
                "scan_summary symbol=%s sent_signals=%s near_miss_signals=%s blocked_reasons=%s",
                self.symbol,
                sent_signals,
                near_miss_signals,
                blocked_reasons,
            )
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
