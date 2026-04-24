from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from config import SMCT_SIGNAL_STATE_FILE


logger = logging.getLogger("scanner")


class SignalStateStore:
    def __init__(
        self,
        price_change_threshold: float = 0.0015,
        state_file: str | None = None,
    ):
        self.price_change_threshold = price_change_threshold
        self.state_file = Path(state_file or SMCT_SIGNAL_STATE_FILE)
        self.last_sent: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        try:
            if self.state_file.exists():
                self.last_sent = json.loads(self.state_file.read_text())
        except Exception as exc:
            logger.warning("signal_state_load_failed file=%s error=%s", self.state_file, exc)
            self.last_sent = {}

    def _save(self) -> None:
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp_file = self.state_file.with_suffix(self.state_file.suffix + ".tmp")
            tmp_file.write_text(json.dumps(self.last_sent, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp_file.replace(self.state_file)
        except Exception as exc:
            logger.warning("signal_state_save_failed file=%s error=%s", self.state_file, exc)

    def _price_change_ratio(self, previous_price: float, current_price: float) -> float:
        base = max(abs(previous_price), 1e-9)
        return abs(current_price - previous_price) / base

    def _signal_rank(self, signal_name: str) -> int:
        if signal_name.startswith("A_"):
            return 4
        if signal_name.startswith("B_"):
            return 3
        if signal_name.startswith("C_"):
            return 2
        if signal_name.startswith("X_"):
            return 1
        return 0

    def _threshold_for(self, signal: dict[str, Any]) -> float:
        name = str(signal.get("signal", ""))
        if name.startswith("X_"):
            return max(self.price_change_threshold * 0.9, 0.0012)
        if name.startswith("C_"):
            return max(self.price_change_threshold * 2.2, 0.0035)
        if name.startswith("B_"):
            return max(self.price_change_threshold * 1.8, 0.0025)
        if name.startswith("A_"):
            return max(self.price_change_threshold * 1.3, 0.0020)
        return self.price_change_threshold

    def _phase_rank(self, phase_name: str) -> int:
        return {
            "none": 0,
            "early": 1,
            "repair": 2,
            "continuation": 3,
            "abnormal": 1,
            "external": 1,
        }.get(phase_name, 0)

    @staticmethod
    def _is_x_signal(signal: dict[str, Any]) -> bool:
        return str(signal.get("signal", "")).startswith("X_") or bool(signal.get("x_lane"))

    def _family_key(self, signal: dict[str, Any]) -> str:
        signal_name = str(signal.get("signal", ""))
        symbol = str(signal.get("symbol", "unknown"))
        timeframe = str(signal.get("timeframe", "15m"))
        direction = str(signal.get("direction", "na"))

        if self._is_x_signal(signal):
            abnormal_type = str(signal.get("abnormal_type", "")) or signal_name
            return f"FAMILY|X|{symbol}|{timeframe}|{direction}|{abnormal_type}"

        phase_anchor = str(signal.get("phase_anchor", ""))
        return f"FAMILY|ABC|{symbol}|{timeframe}|{direction}|{signal_name}|{phase_anchor}"

    def _directional_slot_key(self, signal: dict[str, Any]) -> str:
        symbol = str(signal.get("symbol", "unknown"))
        timeframe = str(signal.get("timeframe", "15m"))
        direction = str(signal.get("direction", "na"))
        phase_anchor = str(signal.get("phase_anchor", ""))

        if self._is_x_signal(signal):
            abnormal_type = str(signal.get("abnormal_type", "")) or str(signal.get("signal", ""))
            return f"SLOT|X|{symbol}|{timeframe}|{direction}|{abnormal_type}"

        return f"SLOT|ABC|{symbol}|{timeframe}|{direction}|{phase_anchor}"

    def _get_effective_rank(self, signal: dict[str, Any]) -> int:
        if self._is_x_signal(signal):
            return 1
        phase_rank = int(signal.get("phase_rank", 0) or 0)
        if phase_rank > 0:
            return phase_rank
        return self._signal_rank(str(signal.get("signal", "")))

    def _should_send_x(self, signal: dict[str, Any]) -> bool:
        family_key = self._family_key(signal)
        slot_key = self._directional_slot_key(signal)

        previous_family = self.last_sent.get(family_key)
        previous_slot = self.last_sent.get(slot_key)

        now = time.time()
        cooldown_seconds = int(signal.get("cooldown_seconds", 1800) or 1800)
        signal_name = str(signal.get("signal", ""))
        signal_price = float(signal.get("price", 0.0) or 0.0)
        signal_signature = str(signal.get("signature", ""))
        curr_threshold = self._threshold_for(signal)

        if previous_family:
            prev_sent_at = float(previous_family.get("sent_at", 0.0))
            prev_price = float(previous_family.get("price", 0.0))
            prev_signature = str(previous_family.get("signature", ""))
            tiny_move = self._price_change_ratio(prev_price, signal_price) <= curr_threshold

            if now - prev_sent_at < cooldown_seconds:
                if signal_signature and prev_signature and signal_signature == prev_signature:
                    return False
                if tiny_move:
                    return False

        if previous_slot:
            prev_sent_at = float(previous_slot.get("sent_at", 0.0))
            prev_price = float(previous_slot.get("price", 0.0))
            prev_signal = str(previous_slot.get("signal", ""))
            within_cooldown = now - prev_sent_at < cooldown_seconds
            tiny_move = self._price_change_ratio(prev_price, signal_price) <= curr_threshold

            if prev_signal == signal_name and within_cooldown:
                return False
            if within_cooldown and tiny_move:
                return False

        return True

    def _should_send_abc(self, signal: dict[str, Any]) -> bool:
        family_key = self._family_key(signal)
        slot_key = self._directional_slot_key(signal)

        previous_family = self.last_sent.get(family_key)
        previous_slot = self.last_sent.get(slot_key)

        now = time.time()
        cooldown_seconds = int(signal.get("cooldown_seconds", 1800) or 1800)
        signal_name = str(signal.get("signal", ""))
        signal_price = float(signal.get("price", 0.0) or 0.0)
        signal_signature = str(signal.get("signature", ""))
        curr_phase = str(signal.get("phase_name", ""))
        curr_state = str(signal.get("state_1h", ""))
        curr_threshold = self._threshold_for(signal)

        if previous_family:
            prev_sent_at = float(previous_family.get("sent_at", 0.0))
            prev_price = float(previous_family.get("price", 0.0))
            prev_signature = str(previous_family.get("signature", ""))
            tiny_move = self._price_change_ratio(prev_price, signal_price) <= curr_threshold

            if now - prev_sent_at < cooldown_seconds:
                if signal_signature and prev_signature and signal_signature == prev_signature:
                    return False
                if tiny_move:
                    return False

        if previous_slot:
            prev_sent_at = float(previous_slot.get("sent_at", 0.0))
            prev_price = float(previous_slot.get("price", 0.0))
            prev_signal = str(previous_slot.get("signal", ""))
            prev_phase = str(previous_slot.get("phase_name", ""))
            prev_state = str(previous_slot.get("state_1h", ""))
            prev_rank = int(previous_slot.get("rank", 0))
            curr_rank = self._get_effective_rank(signal)
            tiny_move = self._price_change_ratio(prev_price, signal_price) <= curr_threshold
            within_cooldown = now - prev_sent_at < cooldown_seconds

            if prev_signal == signal_name and within_cooldown:
                return False

            if prev_state == curr_state and prev_signal != signal_name and within_cooldown:
                return False

            if prev_phase in {"continuation", "repair"} and curr_phase == "early" and within_cooldown:
                return False

            if prev_phase == curr_phase and within_cooldown and tiny_move:
                return False

            upgraded = prev_phase == "early" and curr_phase == "repair"
            upgraded = upgraded or (prev_phase in {"early", "repair"} and curr_phase == "continuation")
            if upgraded and curr_rank >= prev_rank:
                return True

            if within_cooldown and tiny_move:
                return False

        return True

    def should_send(self, signal: dict[str, Any]) -> bool:
        self._load()
        if self._is_x_signal(signal):
            return self._should_send_x(signal)
        return self._should_send_abc(signal)

    def mark_sent(self, signal: dict[str, Any]):
        family_key = self._family_key(signal)
        slot_key = self._directional_slot_key(signal)
        signal_name = str(signal.get("signal", ""))

        payload = {
            "signal": signal_name,
            "status": signal.get("status", "active"),
            "price": float(signal.get("price", 0.0) or 0.0),
            "signature": str(signal.get("signature", "")),
            "cooldown_seconds": int(signal.get("cooldown_seconds", 1800) or 1800),
            "phase_rank": int(signal.get("phase_rank", self._phase_rank(str(signal.get("phase_name", ""))))),
            "phase_name": str(signal.get("phase_name", "")),
            "phase_context": str(signal.get("phase_context", "")),
            "phase_anchor": str(signal.get("phase_anchor", "")),
            "state_1h": str(signal.get("state_1h", "")),
            "h1_tai_bias": str(signal.get("h1_tai_bias", "flat")),
            "h1_tai_slot": str(signal.get("h1_tai_slot", "")),
            "rank": self._get_effective_rank(signal),
            "sent_at": time.time(),
        }

        self.last_sent[family_key] = payload
        self.last_sent[slot_key] = payload
        self._save()
