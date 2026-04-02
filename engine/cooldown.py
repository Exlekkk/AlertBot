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

    def _family_key(self, signal: dict[str, Any]) -> str:
        signal_name = signal.get("signal", "")
        if signal_name.startswith("X_"):
            return f"X|{signal['symbol']}|{signal['timeframe']}|{signal_name}|{signal['direction']}"
        # A / B / C 各自独立完整，不共享同一个去重桶。
        return f"ABC|{signal['symbol']}|{signal['timeframe']}|{signal_name}|{signal['direction']}"

    def should_send(self, signal: dict[str, Any]) -> bool:
        key = self._family_key(signal)
        previous = self.last_sent.get(key)
        if not previous:
            return True

        now = time.time()
        cooldown_seconds = int(signal.get("cooldown_seconds", previous.get("cooldown_seconds", 1800)) or 1800)
        prev_sent_at = float(previous.get("sent_at", 0.0))
        tiny_move = self._price_change_ratio(float(previous.get("price", 0.0)), float(signal.get("price", 0.0))) <= self.price_change_threshold

        prev_anchor = str(previous.get("phase_anchor", ""))
        curr_anchor = str(signal.get("phase_anchor", ""))
        same_anchor = bool(prev_anchor) and prev_anchor == curr_anchor

        prev_signature = str(previous.get("signature", ""))
        curr_signature = str(signal.get("signature", ""))
        same_signature = bool(curr_signature) and curr_signature == prev_signature

        prev_tai_slot = str(previous.get("h1_tai_slot", ""))
        curr_tai_slot = str(signal.get("h1_tai_slot", ""))
        tai_slot_changed = bool(curr_tai_slot) and curr_tai_slot != prev_tai_slot

        signal_name = str(signal.get("signal", ""))
        is_c = signal_name.startswith("C_")

        if same_anchor:
            # C 作为独立分类器：同一段观察只出生一次，除非真的切到新的节奏槽位且价格位移明显。
            if is_c:
                if now - prev_sent_at < cooldown_seconds:
                    return False
                if same_signature and (tiny_move or not tai_slot_changed):
                    return False
                return not tiny_move or tai_slot_changed

            # A / B 作为独立分类器：同一 anchor 下只接受“新信息增量”，不再走跨桶升级/降级补位。
            if now - prev_sent_at < cooldown_seconds and (same_signature or tiny_move) and not tai_slot_changed:
                return False
            if same_signature and tiny_move:
                return False
            return True

        # 跨 anchor 视为该分类器的新一段机会，但短时间内的几乎同价重复依旧拦住。
        if tiny_move and now - prev_sent_at < max(cooldown_seconds // 2, 15 * 60):
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
            "phase_rank": int(signal.get("phase_rank", 0)),
            "phase_name": signal.get("phase_name", ""),
            "phase_context": signal.get("phase_context", ""),
            "phase_anchor": signal.get("phase_anchor", ""),
            "h1_tai_bias": signal.get("h1_tai_bias", "flat"),
            "h1_tai_slot": signal.get("h1_tai_slot", ""),
            "last_direction": signal.get("direction", ""),
            "last_trigger_state": signal.get("trigger_state", ""),
            "sent_at": now,
        }
        self._save()
