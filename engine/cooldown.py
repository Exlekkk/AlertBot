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

    def _phase_rank(self, phase_name: str) -> int:
        return {
            "none": 0,
            "early": 1,
            "repair": 2,
            "continuation": 3,
            "abnormal": 1,
            "external": 1,
        }.get(phase_name, 0)

    def _family_key(self, signal: dict[str, Any]) -> str:
        signal_name = str(signal.get("signal", ""))
        symbol = str(signal.get("symbol", "unknown"))
        timeframe = str(signal.get("timeframe", "15m"))
        direction = str(signal.get("direction", "na"))

        if signal_name.startswith("X_"):
            return f"FAMILY|X|{symbol}|{timeframe}|{signal_name}|{direction}"

        phase_anchor = str(signal.get("phase_anchor", ""))
        if phase_anchor:
            return f"FAMILY|ABC|{symbol}|{timeframe}|{direction}|{phase_anchor}"
        return f"FAMILY|ABC|{symbol}|{timeframe}|{direction}"

    def _directional_slot_key(self, signal: dict[str, Any]) -> str:
        symbol = str(signal.get("symbol", "unknown"))
        timeframe = str(signal.get("timeframe", "15m"))
        direction = str(signal.get("direction", "na"))
        phase_anchor = str(signal.get("phase_anchor", ""))
        return f"SLOT|{symbol}|{timeframe}|{direction}|{phase_anchor}"

    def _get_effective_rank(self, signal: dict[str, Any]) -> int:
        phase_rank = int(signal.get("phase_rank", 0) or 0)
        if phase_rank > 0:
            return phase_rank
        return self._signal_rank(str(signal.get("signal", "")))

    def should_send(self, signal: dict[str, Any]) -> bool:
        self._load()

        family_key = self._family_key(signal)
        slot_key = self._directional_slot_key(signal)

        previous_family = self.last_sent.get(family_key)
        previous_slot = self.last_sent.get(slot_key)

        now = time.time()
        cooldown_seconds = int(signal.get("cooldown_seconds", 1800) or 1800)
        signal_name = str(signal.get("signal", ""))
        signal_price = float(signal.get("price", 0.0) or 0.0)
        signal_signature = str(signal.get("signature", ""))

        # 1) 同 family 去重
        if previous_family:
            prev_sent_at = float(previous_family.get("sent_at", 0.0))
            prev_price = float(previous_family.get("price", 0.0))
            prev_signature = str(previous_family.get("signature", ""))
            tiny_move = self._price_change_ratio(prev_price, signal_price) <= self.price_change_threshold

            if now - prev_sent_at < cooldown_seconds:
                if signal_signature and prev_signature and signal_signature == prev_signature:
                    return False
                if tiny_move:
                    return False

        # 2) 同方向同 anchor 压成单叙事
        if previous_slot:
            prev_sent_at = float(previous_slot.get("sent_at", 0.0))
            prev_price = float(previous_slot.get("price", 0.0))
            prev_signal = str(previous_slot.get("signal", ""))
            prev_rank = int(previous_slot.get("rank", self._signal_rank(prev_signal)))
            curr_rank = self._get_effective_rank(signal)
            tiny_move = self._price_change_ratio(prev_price, signal_price) <= self.price_change_threshold
            same_signal = prev_signal == signal_name
            within_cooldown = now - prev_sent_at < cooldown_seconds

            # 同一段里完全相同信号，直接压掉
            if same_signal and within_cooldown:
                return False

            # A/B/C 已经发过时，X 不应该紧跟着把同一段再讲一遍
            if signal_name.startswith("X_") and not prev_signal.startswith("X_") and within_cooldown and tiny_move:
                return False

            # 如果前一条是 X，后一条是 A/B/C，允许主叙事覆盖异动叙事
            if prev_signal.startswith("X_") and not signal_name.startswith("X_"):
                return True

            # 同一 anchor 下，低等级不能覆盖高等级
            if curr_rank < prev_rank and within_cooldown:
                return False

            # 同等级小波动重复，压掉
            if curr_rank == prev_rank and within_cooldown and tiny_move:
                return False

            # 高等级升级允许一次
            if curr_rank > prev_rank:
                return True

            # 同段里不是升级，而且价格变化也很小，就不再播
            if within_cooldown and tiny_move:
                return False

        return True

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
            "h1_tai_bias": str(signal.get("h1_tai_bias", "flat")),
            "h1_tai_slot": str(signal.get("h1_tai_slot", "")),
            "rank": self._get_effective_rank(signal),
            "sent_at": time.time(),
        }

        self.last_sent[family_key] = payload
        self.last_sent[slot_key] = payload
        self._save()
