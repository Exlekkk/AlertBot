from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from config import SMCT_SIGNAL_STATE_FILE


class SignalStateStore:
    def __init__(
        self,
        price_change_threshold: float = 0.001,
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
        except Exception:
            self.last_sent = {}

    def _save(self) -> None:
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps(self.last_sent, ensure_ascii=False, indent=2))
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
        if signal_name.startswith("X_"):
            return 4
        return 0

    def _family_key(self, signal: dict[str, Any]) -> str:
        if signal["signal"].startswith("X_"):
            return f"X|{signal['symbol']}|{signal.get('timeframe','15m')}|{signal['signal']}|{signal.get('direction','na')}"
        if signal.get("phase_anchor"):
            return f"ABC|{signal['symbol']}|{signal.get('timeframe','15m')}|{signal.get('direction','na')}|{signal['phase_anchor']}"
        return f"ABC|{signal['symbol']}|{signal.get('timeframe','15m')}|{signal.get('direction','na')}"

    def should_send(self, signal: dict[str, Any]) -> bool:
        key = self._family_key(signal)
        previous = self.last_sent.get(key)
        if not previous:
            return True

        now = time.time()
        cooldown_seconds = int(signal.get("cooldown_seconds", 1800) or 1800)
        prev_sent_at = float(previous.get("sent_at", 0.0))
        tiny_move = self._price_change_ratio(
            float(previous.get("price", 0.0)),
            float(signal.get("price", 0.0)),
        ) <= self.price_change_threshold

        if now - prev_sent_at >= cooldown_seconds:
            return True

        if signal.get("signature") and signal.get("signature") == previous.get("signature"):
            return False

        prev_rank = int(previous.get("phase_rank", self._rank(previous.get("signal", ""))))
        curr_rank = int(signal.get("phase_rank", self._rank(signal.get("signal", ""))))

        if curr_rank > prev_rank:
            return True

        if curr_rank <= prev_rank and tiny_move:
            return False

        return not tiny_move

    def mark_sent(self, signal: dict[str, Any]):
        key = self._family_key(signal)
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
            "sent_at": time.time(),
        }
        self._save()
