from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


class SignalStateStore:
    def __init__(self, price_change_threshold: float = 0.001, state_file: str | None = None):
        self.price_change_threshold = price_change_threshold
        self.state_file = Path(state_file or os.getenv("SMCT_SIGNAL_STATE_FILE", "/opt/smct-alert/signal_state.json"))
        self.last_sent: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        try:
            if self.state_file.exists():
                self.last_sent = json.loads(self.state_file.read_text())
        except Exception:
            self.last_sent = {}

    def _save(self) -> None:
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps(self.last_sent, ensure_ascii=False))
        except Exception:
            pass

    def _price_change_ratio(self, previous_price: float, current_price: float) -> float:
        base = max(abs(previous_price), 1e-9)
        return abs(current_price - previous_price) / base

    def _rank(self, signal_name: str) -> int:
        if signal_name.startswith("A_"):
            return 3
        if signal_name.startswith("B_"):
            return 2
        if signal_name.startswith("C_"):
            return 1
        return 0

    def _family_key(self, signal: dict[str, Any]) -> str:
        if signal["signal"].startswith("X_"):
            return f"X|{signal['symbol']}|{signal['timeframe']}|{signal['signal']}|{signal['direction']}"
        return f"ABC|{signal['symbol']}|{signal['timeframe']}"

    def _signal_bucket_key(self, signal: dict[str, Any]) -> str:
        if signal["signal"].startswith("X_"):
            return f"X_BUCKET|{signal['symbol']}|{signal['timeframe']}|{signal['signal']}|{signal['direction']}"
        return f"ABC_BUCKET|{signal['symbol']}|{signal['timeframe']}|{signal['signal']}|{signal['direction']}"

    def should_send(self, signal: dict[str, Any]) -> bool:
        bucket_key = self._signal_bucket_key(signal)
        bucket_prev = self.last_sent.get(bucket_key)
        now = time.time()
        cooldown_seconds = int(signal.get("cooldown_seconds", 1800) or 1800)

        if bucket_prev:
            tiny_move = self._price_change_ratio(float(bucket_prev.get("price", 0.0)), float(signal.get("price", 0.0))) <= self.price_change_threshold
            if signal["signal"].startswith("X_"):
                if signal.get("signature") == bucket_prev.get("signature") and now - float(bucket_prev.get("sent_at", 0.0)) < cooldown_seconds:
                    return False
            if tiny_move and now - float(bucket_prev.get("sent_at", 0.0)) < cooldown_seconds:
                return False

        if signal["signal"].startswith("X_"):
            return True

        family_key = self._family_key(signal)
        previous = self.last_sent.get(family_key)
        if not previous:
            return True

        prev_sent_at = float(previous.get("sent_at", 0.0))
        prev_price = float(previous.get("price", 0.0))
        curr_price = float(signal.get("price", 0.0))
        tiny_move = self._price_change_ratio(prev_price, curr_price) <= self.price_change_threshold
        prev_rank = int(previous.get("phase_rank", self._rank(previous.get("signal", ""))))
        curr_rank = int(signal.get("phase_rank", self._rank(signal.get("signal", ""))))
        prev_signal = previous.get("signal", "")
        curr_signal = signal.get("signal", "")
        prev_direction = previous.get("direction", "")
        curr_direction = signal.get("direction", "")
        prev_segment = previous.get("segment_id", "")
        curr_segment = signal.get("segment_id", "")
        prev_state = previous.get("state_1h", previous.get("phase_name", ""))
        curr_state = signal.get("state_1h", signal.get("phase_name", ""))
        prev_heat = previous.get("tai_heat_1h", "neutral")
        curr_heat = signal.get("tai_heat_1h", "neutral")
        heat_restricted = bool(signal.get("heat_restricted"))

        # Keep one dominant narrative per segment. Do not allow direction conflict.
        if prev_segment == curr_segment and prev_direction and curr_direction and prev_direction != curr_direction:
            return False

        # Inside the same segment, do not let lower-rank categories steal narrative control.
        if prev_segment == curr_segment and curr_rank < prev_rank:
            return False

        # Same signal, same segment, tiny movement: suppress.
        if prev_signal == curr_signal and prev_segment == curr_segment and tiny_move and now - prev_sent_at < cooldown_seconds:
            return False

        # Same direction and same segment: only allow if upgrading or materially moving.
        if prev_segment == curr_segment and prev_direction == curr_direction:
            if curr_rank == prev_rank and tiny_move and now - prev_sent_at < cooldown_seconds:
                return False
            if curr_rank > prev_rank:
                return True
            if curr_rank < prev_rank:
                return False

        # In restricted heat, be much stricter across nearby narrative changes.
        if heat_restricted and tiny_move and now - prev_sent_at < max(cooldown_seconds, 60 * 60):
            return False

        # Do not flip from a valid A narrative into B/C of the same direction too quickly.
        if prev_rank == 3 and curr_rank < 3 and prev_direction == curr_direction and now - prev_sent_at < max(cooldown_seconds, 75 * 60):
            return False

        # If the prior state was range neutral and new state is meaningful, allow.
        if prev_state == "range_neutral" and curr_state != "range_neutral":
            return True

        # If heat improves materially and state changes, allow.
        heat_order = {"cold": 0, "cool": 1, "neutral": 2, "warm": 3, "hot": 4}
        if heat_order.get(curr_heat, 2) > heat_order.get(prev_heat, 2) and curr_state != prev_state:
            return True

        return True

    def mark_sent(self, signal: dict[str, Any]):
        now = time.time()
        payload = {
            "signal": signal["signal"],
            "status": signal.get("status", "active"),
            "price": signal.get("price", 0.0),
            "signature": signal.get("signature", ""),
            "cooldown_seconds": int(signal.get("cooldown_seconds", 1800) or 1800),
            "phase_rank": int(signal.get("phase_rank", self._rank(signal.get("signal", "")))),
            "phase_name": signal.get("phase_name", ""),
            "direction": signal.get("direction", ""),
            "state_1h": signal.get("state_1h", signal.get("phase_name", "")),
            "trigger_15m_state": signal.get("trigger_15m_state", signal.get("trigger_state", "")),
            "tai_heat_1h": signal.get("tai_heat_1h", "neutral"),
            "segment_id": signal.get("segment_id", ""),
            "sent_at": now,
        }
        self.last_sent[self._signal_bucket_key(signal)] = payload
        self.last_sent[self._family_key(signal)] = payload
        self._save()
