from __future__ import annotations

import json
import math
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

    def _phase_rank(self, phase_name: str) -> int:
        return {"none": 0, "early": 1, "repair": 2, "continuation": 3}.get(phase_name, 0)

    def _normalized_zone(self, low: float | None, high: float | None, price: float) -> tuple[float, float]:
        low_v = float(price if low is None else low)
        high_v = float(price if high is None else high)
        if low_v > high_v:
            low_v, high_v = high_v, low_v
        if abs(high_v - low_v) < max(abs(price) * 0.0008, 8.0):
            pad = max(abs(price) * 0.0012, 12.0)
            low_v -= pad * 0.5
            high_v += pad * 0.5
        return low_v, high_v

    def _zone_overlap_ratio(self, prev_low: float, prev_high: float, curr_low: float, curr_high: float) -> float:
        intersection = max(0.0, min(prev_high, curr_high) - max(prev_low, curr_low))
        union = max(prev_high, curr_high) - min(prev_low, curr_low)
        if union <= 1e-9:
            return 1.0
        return max(0.0, min(1.0, intersection / union))

    def _basis_overlap_ratio(self, previous: dict[str, Any], current: dict[str, Any]) -> float:
        prev_basis = set(previous.get("structure_basis") or [])
        curr_basis = set(current.get("structure_basis") or [])
        if not prev_basis and not curr_basis:
            return 1.0
        if not prev_basis or not curr_basis:
            return 0.0
        inter = len(prev_basis & curr_basis)
        union = len(prev_basis | curr_basis)
        return inter / max(union, 1)

    def _context_similarity(self, previous: dict[str, Any], current: dict[str, Any]) -> float:
        score = 0.0
        if previous.get("signal") == current.get("signal"):
            score += 0.22
        if previous.get("phase_name") == current.get("phase_name"):
            score += 0.16
        if previous.get("trigger_state") == current.get("trigger_state"):
            score += 0.12
        if previous.get("trend_1h") == current.get("trend_1h"):
            score += 0.08
        if previous.get("bg_bias") == current.get("bg_bias"):
            score += 0.08
        return score

    def _price_similarity(self, previous: dict[str, Any], current: dict[str, Any]) -> float:
        prev_price = float(previous.get("price", 0.0) or 0.0)
        curr_price = float(current.get("price", 0.0) or 0.0)
        if prev_price <= 0 or curr_price <= 0:
            return 0.0
        ratio = self._price_change_ratio(prev_price, curr_price)
        base = max(float(previous.get("atr", 0.0) or 0.0), prev_price * 0.0012)
        normalized_move = abs(curr_price - prev_price) / max(base, 1e-9)
        tiny_bonus = 1.0 if ratio <= self.price_change_threshold else 0.0
        smooth = 1.0 / (1.0 + normalized_move)
        return min(1.0, 0.55 * smooth + 0.45 * tiny_bonus)

    def _signal_similarity(self, previous: dict[str, Any], current: dict[str, Any]) -> float:
        curr_price = float(current.get("price", previous.get("price", 0.0)) or 0.0)
        prev_low, prev_high = self._normalized_zone(previous.get("zone_low"), previous.get("zone_high"), float(previous.get("price", curr_price) or curr_price))
        curr_low, curr_high = self._normalized_zone(current.get("zone_low"), current.get("zone_high"), curr_price)
        zone_overlap = self._zone_overlap_ratio(prev_low, prev_high, curr_low, curr_high)
        basis_overlap = self._basis_overlap_ratio(previous, current)
        context_similarity = self._context_similarity(previous, current)
        price_similarity = self._price_similarity(previous, current)

        score = (
            0.30 * zone_overlap
            + 0.24 * basis_overlap
            + 0.22 * price_similarity
            + context_similarity
        )
        return max(0.0, min(1.0, score))

    def _novelty_score(self, previous: dict[str, Any], current: dict[str, Any]) -> float:
        prev_rank = int(previous.get("phase_rank", self._rank(previous.get("signal", ""))))
        curr_rank = int(current.get("phase_rank", self._rank(current.get("signal", ""))))
        prev_phase_rank = self._phase_rank(previous.get("phase_name", ""))
        curr_phase_rank = self._phase_rank(current.get("phase_name", ""))

        score = 0.0
        if curr_rank > prev_rank:
            score += 0.34
        elif curr_rank < prev_rank:
            score -= 0.18

        phase_delta = curr_phase_rank - prev_phase_rank
        if phase_delta > 0:
            score += min(0.20, phase_delta * 0.10)
        elif phase_delta < 0:
            score -= min(0.14, abs(phase_delta) * 0.07)

        if previous.get("trigger_state") != current.get("trigger_state"):
            score += 0.08
        if previous.get("signal") != current.get("signal"):
            score += 0.08
        if previous.get("phase_context") != current.get("phase_context"):
            score += 0.08
        if previous.get("trend_1h") != current.get("trend_1h"):
            score += 0.05
        if previous.get("bg_bias") != current.get("bg_bias"):
            score += 0.04
        if previous.get("signature") != current.get("signature"):
            score += 0.06
        return score

    def _time_release(self, previous: dict[str, Any], signal: dict[str, Any], now: float) -> float:
        cooldown_seconds = int(signal.get("cooldown_seconds", previous.get("cooldown_seconds", 1800)) or 1800)
        prev_sent_at = float(previous.get("sent_at", 0.0) or 0.0)
        elapsed = max(0.0, now - prev_sent_at)
        if cooldown_seconds <= 0:
            return 1.0
        return max(0.0, min(1.0, elapsed / cooldown_seconds))

    def should_send(self, signal: dict[str, Any]) -> bool:
        key = self._family_key(signal)
        previous = self.last_sent.get(key)
        if not previous:
            return True

        now = time.time()
        cooldown_seconds = int(signal.get("cooldown_seconds", 1800) or 1800)
        prev_sent_at = float(previous.get("sent_at", 0.0) or 0.0)
        elapsed = max(0.0, now - prev_sent_at)

        if signal["signal"].startswith("X_"):
            similarity = self._signal_similarity(previous, signal)
            release = self._time_release(previous, signal, now)
            if similarity >= 0.82 and release < 1.0:
                return False
            if signal.get("signature") == previous.get("signature") and elapsed < cooldown_seconds:
                return False
            return True

        similarity = self._signal_similarity(previous, signal)
        novelty = self._novelty_score(previous, signal)
        release = self._time_release(previous, signal, now)

        # 生命周期抑制：越像同一机会、距离上次越近，越倾向静默更新；
        # 真正出现阶段推进/结构变化时，novelty 会释放新的提醒。
        suppression_pressure = similarity * (1.0 - release)
        reissue_strength = novelty + release * 0.55

        if suppression_pressure >= 0.58 and reissue_strength <= 0.34:
            return False

        if similarity >= 0.78 and novelty <= 0.12 and elapsed < cooldown_seconds:
            return False

        if similarity >= 0.68 and novelty < 0 and release < 1.15:
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
            "last_direction": signal.get("direction", ""),
            "last_phase_1h": signal.get("phase_name", ""),
            "last_label": signal.get("signal", ""),
            "last_trigger_state": signal.get("trigger_state", ""),
            "trend_1h": signal.get("trend_1h", ""),
            "bg_bias": signal.get("bg_bias", ""),
            "trigger_state": signal.get("trigger_state", ""),
            "zone_low": signal.get("zone_low"),
            "zone_high": signal.get("zone_high"),
            "structure_basis": signal.get("structure_basis", []),
            "atr": signal.get("atr", 0.0),
            "last_sent_ts": now,
            "sent_at": now,
        }
        self._save()
