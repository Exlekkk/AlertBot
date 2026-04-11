
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from config import SMCT_SIGNAL_STATE_FILE


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

    def _threshold_for(self, signal: dict[str, Any]) -> float:
        stage = int(signal.get("stage_rank", signal.get("phase_rank", 0)) or 0)
        if stage <= 1:
            return max(self.price_change_threshold * 2.6, 0.0038)
        if stage == 2:
            return max(self.price_change_threshold * 1.8, 0.0025)
        return max(self.price_change_threshold * 1.2, 0.0018)

    def _family_key(self, signal: dict[str, Any]) -> str:
        symbol = str(signal.get("symbol", "unknown"))
        timeframe = str(signal.get("timeframe", "15m"))
        signal_name = str(signal.get("signal", ""))
        direction = str(signal.get("direction", "na"))
        signature = str(signal.get("signature", ""))
        return f"FAMILY|{symbol}|{timeframe}|{signal_name}|{direction}|{signature}"

    def _market_key(self, signal: dict[str, Any]) -> str:
        key = str(signal.get("market_lock_key", "")).strip()
        if key:
            return f"MARKET|{key}"
        symbol = str(signal.get("symbol", "unknown"))
        timeframe = str(signal.get("timeframe", "15m"))
        return f"MARKET|{symbol}|{timeframe}"

    def _state_rank(self, signal: dict[str, Any]) -> int:
        return int(signal.get("stage_rank", signal.get("phase_rank", 0)) or 0)

    def should_send(self, signal: dict[str, Any]) -> bool:
        self._load()

        family_key = self._family_key(signal)
        market_key = self._market_key(signal)

        previous_family = self.last_sent.get(family_key)
        previous_market = self.last_sent.get(market_key)

        now = time.time()
        cooldown_seconds = int(signal.get("cooldown_seconds", 1800) or 1800)
        signal_price = float(signal.get("price", 0.0) or 0.0)
        signal_name = str(signal.get("signal", ""))
        signal_direction = str(signal.get("direction", "na"))
        signal_state = str(signal.get("state_1h", ""))
        signal_budget = str(signal.get("tai_budget_mode", "normal"))
        signal_trigger = str(signal.get("trigger_15m_state", "idle"))
        signal_reversal_strength = int(signal.get("reversal_strength", 0) or 0)
        stage_rank = self._state_rank(signal)

        # Exact-family duplicate suppression.
        if previous_family:
            prev_sent_at = float(previous_family.get("sent_at", 0.0))
            prev_price = float(previous_family.get("price", 0.0))
            tiny_move = self._price_change_ratio(prev_price, signal_price) <= self._threshold_for(signal)
            if now - prev_sent_at < cooldown_seconds and tiny_move:
                return False

        if not previous_market:
            return True

        prev_sent_at = float(previous_market.get("sent_at", 0.0))
        prev_price = float(previous_market.get("price", 0.0))
        prev_direction = str(previous_market.get("direction", "na"))
        prev_signal = str(previous_market.get("signal", ""))
        prev_state = str(previous_market.get("state_1h", ""))
        prev_budget = str(previous_market.get("tai_budget_mode", "normal"))
        prev_trigger = str(previous_market.get("trigger_15m_state", "idle"))
        prev_stage_rank = int(previous_market.get("stage_rank", previous_market.get("phase_rank", 0)) or 0)

        within_cooldown = now - prev_sent_at < max(cooldown_seconds, int(previous_market.get("cooldown_seconds", cooldown_seconds)))
        tiny_move = self._price_change_ratio(prev_price, signal_price) <= self._threshold_for(signal)

        if not within_cooldown:
            return True

        same_direction = prev_direction == signal_direction

        # Same-side narrative: allow only if the phase truly matures or price expands enough.
        if same_direction:
            if prev_signal == signal_name and tiny_move:
                return False
            if stage_rank < prev_stage_rank:
                return False
            if stage_rank == prev_stage_rank and tiny_move:
                return False
            return True

        # Opposite-side publication: no fixed ladder, but reversal must be real.
        cold_environment = signal_budget in {"restricted", "frozen"} or prev_budget in {"restricted", "frozen"}
        required_reversal = 4 if cold_environment else 3

        decisive_state_flip = (
            signal_state != prev_state
            and (
                signal_trigger.startswith("confirm_")
                or prev_trigger.startswith("confirm_")
                or stage_rank >= prev_stage_rank
            )
        )

        if signal_reversal_strength < required_reversal:
            return False

        if not decisive_state_flip:
            return False

        if cold_environment and tiny_move:
            return False

        return True

    def mark_sent(self, signal: dict[str, Any]) -> None:
        family_key = self._family_key(signal)
        market_key = self._market_key(signal)

        payload = {
            "signal": str(signal.get("signal", "")),
            "direction": str(signal.get("direction", "na")),
            "state_1h": str(signal.get("state_1h", "")),
            "trigger_15m_state": str(signal.get("trigger_15m_state", "idle")),
            "price": float(signal.get("price", 0.0) or 0.0),
            "signature": str(signal.get("signature", "")),
            "cooldown_seconds": int(signal.get("cooldown_seconds", 1800) or 1800),
            "phase_rank": int(signal.get("phase_rank", 0) or 0),
            "stage_rank": int(signal.get("stage_rank", signal.get("phase_rank", 0)) or 0),
            "phase_name": str(signal.get("phase_name", "")),
            "phase_context": str(signal.get("phase_context", "")),
            "phase_anchor": str(signal.get("phase_anchor", "")),
            "tai_budget_mode": str(signal.get("tai_budget_mode", "normal")),
            "reversal_strength": int(signal.get("reversal_strength", 0) or 0),
            "market_lock_key": str(signal.get("market_lock_key", "")),
            "sent_at": time.time(),
        }

        self.last_sent[family_key] = payload
        self.last_sent[market_key] = payload
        self._save()
