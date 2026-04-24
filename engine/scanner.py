from __future__ import annotations

import time
from typing import Any

from config import (
    BINANCE_SYMBOL,
    FREEZE_MODE_SEND_X_ONLY,
    KLINE_LIMIT,
    SEND_NEAR_MISS_SUMMARY,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    WEBHOOK_LOG_FILE,
)
from engine.x_signals import detect_x_signals
from engine.cooldown import SignalStateStore
from engine.indicators import enrich_klines
from engine.market_data import BinanceMarketDataClient
from engine.runtime_state import RuntimeStateStore
from engine.signals import detect_signals
from services.logger import get_logger
from services.telegram import TelegramSendError, format_engine_message, send_telegram_message


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

    def _build_entry_zone(self, signal: dict[str, Any], klines_15m: list[dict]) -> tuple[float, float]:
        zone_low = signal.get("zone_low")
        zone_high = signal.get("zone_high")
        if zone_low is not None and zone_high is not None:
            return self._safe_band(zone_low, zone_high)

        latest = klines_15m[-1]
        recent_8 = klines_15m[-8:]
        price = float(signal["price"])
        atr = max(float(latest.get("atr", 0.0)), price * 0.0015)
        ema10 = float(latest["ema10"])
        ema20 = float(latest["ema20"])
        recent_support = min(float(k["low"]) for k in recent_8)
        recent_resistance = max(float(k["high"]) for k in recent_8)
        signal_name = signal["signal"]

        if signal_name == "A_LONG":
            return self._safe_band(min(ema10, ema20, price - atr * 0.35), max(ema10, ema20, price - atr * 0.05))
        if signal_name == "A_SHORT":
            return self._safe_band(min(ema10, ema20, price + atr * 0.05), max(ema10, ema20, price + atr * 0.35))
        if signal_name == "B_PULLBACK_LONG":
            return self._safe_band(min(ema10, ema20, recent_support) - atr * 0.10, max(ema10, ema20) + atr * 0.08)
        if signal_name == "B_PULLBACK_SHORT":
            return self._safe_band(min(ema10, ema20) - atr * 0.08, max(ema10, ema20, recent_resistance) + atr * 0.10)
        if signal_name == "C_LEFT_LONG":
            return self._safe_band(min(recent_support, ema20) - atr * 0.18, max(ema10, ema20) + atr * 0.10)
        if signal_name == "C_LEFT_SHORT":
            return self._safe_band(min(ema10, ema20) - atr * 0.10, max(recent_resistance, ema20) + atr * 0.18)
        if signal_name == "X_BREAKOUT_LONG":
            return self._safe_band(min(ema10, ema20, price - atr * 1.10), max(ema10, recent_resistance) + atr * 0.08)
        if signal_name == "X_BREAKOUT_SHORT":
            return self._safe_band(min(ema10, recent_support) - atr * 0.08, max(ema10, ema20, price + atr * 1.10))
        return self._safe_band(price - atr * 0.12, price + atr * 0.12)

    def _prepare_signal(self, signal: dict[str, Any], klines_15m: list[dict]) -> dict[str, Any]:
        low, high = self._build_entry_zone(signal, klines_15m)
        merged = dict(signal)
        merged["entry_zone_low"] = low
        merged["entry_zone_high"] = high
        merged.setdefault("trigger_level", signal.get("breakout_level"))
        merged.setdefault("timeframe", "15m")
        merged.setdefault("phase_name", self._phase_name_from_signal(signal.get("signal", ""), signal.get("state_1h", "")))
        merged.setdefault("phase_rank", self._phase_rank_from_signal(signal.get("signal", "")))
        merged.setdefault("phase_context", signal.get("state_1h", "") or signal.get("status", "active"))
        merged.setdefault("phase_anchor", self._phase_anchor(signal))
        merged.setdefault("cooldown_seconds", self._cooldown_for(signal))
        merged.setdefault("narrative_kind", self._narrative_kind(signal))
        return merged

    @staticmethod
    def _phase_name_from_signal(signal_name: str, state_1h: str) -> str:
        if signal_name.startswith("A_") or "trend_drive" in state_1h:
            return "continuation"
        if signal_name.startswith("B_") or "repair" in state_1h:
            return "repair"
        if signal_name.startswith("C_") or "probe" in state_1h:
            return "early"
        if signal_name.startswith("X_"):
            return "abnormal"
        return "none"

    @staticmethod
    def _phase_rank_from_signal(signal_name: str) -> int:
        if signal_name.startswith("A_"):
            return 3
        if signal_name.startswith("B_"):
            return 2
        if signal_name.startswith("C_"):
            return 1
        if signal_name.startswith("X_"):
            return 4
        return 0

    @staticmethod
    def _phase_anchor(signal: dict[str, Any]) -> str:
        state_1h = signal.get("state_1h", "")
        direction = signal.get("direction", "na")
        bg = signal.get("background_4h_direction", "neutral")
        heat = signal.get("tai_heat_1h", "neutral")
        return f"{state_1h}|{direction}|{bg}|{heat}"

    @staticmethod
    def _cooldown_for(signal: dict[str, Any]) -> int:
        name = signal.get("signal", "")
        if name.startswith("X_"):
            return 1800
        if name.startswith("A_"):
            return 2400
        if name.startswith("B_"):
            return 1800
        return 3600

    @staticmethod
    def _narrative_kind(signal: dict[str, Any]) -> str:
        state_1h = signal.get("state_1h", "")
        if state_1h.startswith("trend_drive"):
            return "main"
        if state_1h.startswith("repair"):
            return "repair"
        if state_1h.startswith("probe"):
            return "early"
        if signal.get("signal", "").startswith("X_"):
            return "abnormal"
        return "watch"

    def _build_runtime_summary(
        self,
        signal_result: dict[str, Any],
        sent_signals: list[dict[str, Any]],
        x_signals: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "background_4h_direction": signal_result.get("background_4h_direction"),
            "state_1h": signal_result.get("state_1h"),
            "trigger_15m_state": signal_result.get("trigger_15m_state"),
            "tai_budget_mode": signal_result.get("tai_budget_mode"),
            "tai_heat_1h": signal_result.get("tai_heat_1h"),
            "tai_heat_4h": signal_result.get("tai_heat_4h"),
            "blocked_reasons": signal_result.get("blocked_reasons", []),
            "signals_detected": [s.get("signal") for s in signal_result.get("signals", [])],
            "x_signals_detected": [s.get("signal") for s in x_signals],
            "signals_sent": [s.get("signal") for s in sent_signals],
            "near_miss_signals": signal_result.get("near_miss_signals", []),
        }

    def _select_candidates(
        self,
        signal_result: dict[str, Any],
        x_signals: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        base_signals = [s for s in signal_result.get("signals", []) if not s.get("signal", "").startswith("X_")]
        budget = signal_result.get("tai_budget_mode", "normal")
        if budget == "frozen" and FREEZE_MODE_SEND_X_ONLY:
            return list(x_signals)
        candidates = list(x_signals)
        if budget != "frozen":
            candidates.extend(base_signals)
        return candidates

    def health_check(self) -> dict[str, Any]:
        snapshot = self.runtime_state.build_health_payload()
        return {
            "ok": snapshot.get("ok", False),
            "symbol": self.symbol,
            "runtime": snapshot,
        }

    def run_once(self) -> dict[str, Any]:
        try:
            self.logger.info("scanner_started symbol=%s interval=%s", self.symbol, 60)

            klines_1d = self._fetch_enriched("1d")
            klines_4h = self._fetch_enriched("4h")
            klines_1h = self._fetch_enriched("1h")
            klines_15m = self._fetch_enriched("15m")

            signal_result = detect_signals(self.symbol, klines_1d, klines_4h, klines_1h, klines_15m)
            x_signals = detect_x_signals(self.symbol, klines_1d, klines_4h, klines_1h, klines_15m)
            candidates = self._select_candidates(signal_result, x_signals)

            sent_signals: list[dict[str, Any]] = []

            for raw_signal in candidates:
                signal = self._prepare_signal(raw_signal, klines_15m)

                if not self.state_store.should_send(signal):
                    self.logger.info(
                        "signal_suppressed symbol=%s signal=%s state=%s trigger=%s budget=%s",
                        self.symbol,
                        signal.get("signal"),
                        signal.get("state_1h"),
                        signal.get("trigger_15m_state"),
                        signal.get("tai_budget_mode"),
                    )
                    continue

                message = format_engine_message(signal)
                try:
                    result = send_telegram_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, message)
                except TelegramSendError as exc:
                    self.logger.error(
                        "telegram_send_failed symbol=%s signal=%s state=%s trigger=%s budget=%s error=%s",
                        self.symbol,
                        signal.get("signal"),
                        signal.get("state_1h"),
                        signal.get("trigger_15m_state"),
                        signal.get("tai_budget_mode"),
                        exc,
                    )
                    continue

                self.state_store.mark_sent(signal)
                self.runtime_state.mark_sent_signal(signal)
                sent_signals.append(signal)

                self.logger.info(
                    "signal_sent symbol=%s signal=%s state=%s trigger=%s budget=%s telegram_ok=%s",
                    self.symbol,
                    signal.get("signal"),
                    signal.get("state_1h"),
                    signal.get("trigger_15m_state"),
                    signal.get("tai_budget_mode"),
                    result.get("ok"),
                )

            if SEND_NEAR_MISS_SUMMARY and signal_result.get("near_miss_signals"):
                self.logger.info(
                    "near_miss symbol=%s payload=%s",
                    self.symbol,
                    signal_result.get("near_miss_signals"),
                )

            summary = self._build_runtime_summary(signal_result, sent_signals, x_signals)
            self.runtime_state.mark_scan(ok=True, symbol=self.symbol, summary=summary)

            self.logger.info(
                "scan_cycle_complete symbol=%s state_1h=%s trigger=%s budget=%s sent=%s",
                self.symbol,
                summary.get("state_1h"),
                summary.get("trigger_15m_state"),
                summary.get("tai_budget_mode"),
                len(sent_signals),
            )

            return {"ok": True, "summary": summary, "sent": len(sent_signals)}

        except Exception as exc:
            self.logger.exception("scanner_run_failed symbol=%s error=%s", self.symbol, exc)
            self.runtime_state.mark_scan(ok=False, symbol=self.symbol, summary={}, error=str(exc))
            return {"ok": False, "error": str(exc)}

    def run_forever(self, interval_seconds: int = 60):
        while True:
            self.run_once()
            time.sleep(interval_seconds)
