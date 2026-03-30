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
        return f"ABC|{signal['symbol']}|{signal['timeframe']}|{signal['direction']}"

    def should_send(self, signal: dict[str, Any]) -> bool:
        key = self._family_key(signal)
        previous = self.last_sent.get(key)
        if not previous:
            return True

        now = time.time()
        cooldown_seconds = int(signal.get("cooldown_seconds", 1800) or 1800)
        prev_sent_at = float(previous.get("sent_at", 0.0))
        tiny_move = self._price_change_ratio(float(previous.get("price", 0.0)), float(signal.get("price", 0.0))) <= self.price_change_threshold

        # X 独立：只按签名与冷却期去重
        if signal["signal"].startswith("X_"):
            if signal.get("signature") == previous.get("signature") and now - prev_sent_at < cooldown_seconds:
                return False
            if tiny_move and now - prev_sent_at < cooldown_seconds:
                return False
            return True

        prev_rank = int(previous.get("phase_rank", self._rank(previous.get("signal", ""))))
        curr_rank = int(signal.get("phase_rank", self._rank(signal.get("signal", ""))))
        prev_context = previous.get("phase_context", "")
        curr_context = signal.get("phase_context", "")
        prev_phase = previous.get("phase_name", "")
        curr_phase = signal.get("phase_name", "")

        # 同方向同阶段同上下文：小波动不重发
        if prev_context == curr_context and prev_phase == curr_phase and tiny_move and now - prev_sent_at < cooldown_seconds:
            return False

        # A 直通：A 一旦成立，不能被 B/C 防抖拖住
        if curr_rank == 3:
            if prev_rank == 3 and prev_context == curr_context and now - prev_sent_at < cooldown_seconds and tiny_move:
                return False
            return True

        # B/C 防抖：同方向不允许无上下文变化的降级乱跳
        if curr_rank < prev_rank:
            if prev_context == curr_context and now - prev_sent_at < max(cooldown_seconds, 2 * 3600):
                return False
            if prev_phase == curr_phase and now - prev_sent_at < max(cooldown_seconds, 90 * 60):
                return False

        # 同等级但没有阶段/区间变化，不重发
        if curr_rank == prev_rank and prev_context == curr_context:
            if now - prev_sent_at < cooldown_seconds:
                return False

        return True

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
            "sent_at": time.time(),
        }
        self._save()
