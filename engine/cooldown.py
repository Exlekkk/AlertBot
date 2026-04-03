from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


class SignalStateStore:
    def __init__(
        self,
        price_change_threshold: float = 0.001,
        state_file: str | None = None,
    ):
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
        classifier = signal["signal"].split("_", 1)[0]
        return f"{classifier}|{signal['symbol']}|{signal['timeframe']}|{signal['direction']}"

    def _phase_rank(self, phase_name: str) -> int:
        return {"none": 0, "early": 1, "repair": 2, "continuation": 3}.get(phase_name, 0)

    def _tai_bias_rank(self, tai_bias: str) -> int:
        return {"drag": 0, "flat": 1, "support": 2, "drive": 3}.get(tai_bias, 1)

    def should_send(self, signal: dict[str, Any]) -> bool:
        key = self._family_key(signal)
        previous = self.last_sent.get(key)
        if not previous:
            return True

        now = time.time()
        cooldown_seconds = int(signal.get("cooldown_seconds", 1800) or 1800)
        prev_sent_at = float(previous.get("sent_at", 0.0))
        tiny_move = self._price_change_ratio(float(previous.get("price", 0.0)), float(signal.get("price", 0.0))) <= self.price_change_threshold

        if signal["signal"].startswith("X_"):
            if signal.get("signature") == previous.get("signature") and now - prev_sent_at < cooldown_seconds:
                return False
            if tiny_move and now - prev_sent_at < cooldown_seconds:
                return False
            return True

        prev_rank = int(previous.get("phase_rank", self._rank(previous.get("signal", ""))))
        curr_rank = int(signal.get("phase_rank", self._rank(signal.get("signal", ""))))
        prev_anchor = str(previous.get("phase_anchor", ""))
        curr_anchor = str(signal.get("phase_anchor", ""))
        same_anchor = bool(prev_anchor) and prev_anchor == curr_anchor

        if same_anchor:
            if previous.get("signal") == signal.get("signal"):
                if now - prev_sent_at < cooldown_seconds:
                    return False
                if tiny_move:
                    return False
            if curr_rank == prev_rank and tiny_move and now - prev_sent_at < cooldown_seconds:
                return False
            if curr_rank < prev_rank and now - prev_sent_at < max(cooldown_seconds // 2, 20 * 60):
                return False
            return True

        if tiny_move and now - prev_sent_at < cooldown_seconds and signal.get("phase_context") == previous.get("phase_context"):
            return False
        return True

    def mark_sent(self, signal: dict[str, Any]):
        key = self._family_key(signal)
        now = time.time()
        self.last_sent[key] = {
            "signal": signal["signal"],
            "status": signal.get("status", "active"),
            "price": signal.get("price", 0.0),
            "signature": signal.get("signature", ""),
            "cooldown_seconds": int(signal.get("cooldown_seconds", 1800) or 1800),
            "phase_rank": int(signal.get("phase_rank", self._rank(signal.get("signal", "")))),
            "phase_name": signal.get("phase_name", ""),
            "phase_context": signal.get("phase_context", ""),
            "phase_anchor": signal.get("phase_anchor", ""),
            "h1_tai_bias": signal.get("h1_tai_bias", "flat"),
            "h1_tai_slot": signal.get("h1_tai_slot", ""),
            "last_direction": signal.get("direction", ""),
            "last_phase_1h": signal.get("phase_name", ""),
            "last_label": signal.get("signal", ""),
            "last_trigger_state": signal.get("trigger_state", ""),
            "last_sent_ts": now,
            "sent_at": now,
        }
        self._save()
