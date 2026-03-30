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

    def _signal_key(self, signal: dict[str, Any]) -> str:
        # X 独立，ABC 按具体 signal 独立；重启后继续生效
        return f"{signal['symbol']}|{signal['timeframe']}|{signal['signal']}|{signal['direction']}"

    def should_send(self, signal: dict[str, Any]) -> bool:
        key = self._signal_key(signal)
        previous = self.last_sent.get(key)
        if not previous:
            return True

        now = time.time()
        cooldown_seconds = int(signal.get('cooldown_seconds', 1800) or 1800)
        signature = signal.get('signature', '')
        prev_signature = previous.get('signature', '')
        same_signature = signature == prev_signature and bool(signature)
        tiny_price_move = self._price_change_ratio(float(previous.get('price', 0.0)), float(signal.get('price', 0.0))) <= self.price_change_threshold

        # 同签名 + 冷却期内，重启也不重发
        if same_signature and now - float(previous.get('sent_at', 0.0)) < cooldown_seconds:
            return False

        # 同类同状态且价格几乎没动，不重发
        if previous.get('status') == signal.get('status') and tiny_price_move and now - float(previous.get('sent_at', 0.0)) < cooldown_seconds:
            return False

        return True

    def mark_sent(self, signal: dict[str, Any]):
        key = self._signal_key(signal)
        self.last_sent[key] = {
            'signal': signal['signal'],
            'status': signal.get('status', 'active'),
            'price': signal.get('price', 0.0),
            'signature': signal.get('signature', ''),
            'cooldown_seconds': int(signal.get('cooldown_seconds', 1800) or 1800),
            'sent_at': time.time(),
        }
        self._save()
