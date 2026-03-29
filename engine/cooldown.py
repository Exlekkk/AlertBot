import time


class SignalStateStore:
    def __init__(
        self,
        price_change_threshold: float = 0.0015,
        a_min_repeat_seconds: int = 60 * 60,
        b_min_repeat_seconds: int = 75 * 60,
        c_min_repeat_seconds: int = 90 * 60,
        downgrade_lock_seconds: int = 2 * 60 * 60,
    ):
        self.price_change_threshold = price_change_threshold
        self.a_min_repeat_seconds = a_min_repeat_seconds
        self.b_min_repeat_seconds = b_min_repeat_seconds
        self.c_min_repeat_seconds = c_min_repeat_seconds
        self.downgrade_lock_seconds = downgrade_lock_seconds
        # ABC: 按 symbol + timeframe + direction 去重；X 独立。
        self.last_sent: dict[tuple[str, str, str], dict] = {}

    def _signal_key(self, signal: dict) -> tuple[str, str, str]:
        if signal["signal"].startswith("X_"):
            return (signal["symbol"], signal["timeframe"], signal["signal"])
        return (signal["symbol"], signal["timeframe"], signal["direction"])

    def _stage_name(self, signal_name: str) -> str:
        if signal_name.startswith("A_"):
            return "A"
        if signal_name.startswith("B_"):
            return "B"
        if signal_name.startswith("C_"):
            return "C"
        return signal_name

    def _stage_rank(self, stage_name: str) -> int:
        return {"C": 1, "B": 2, "A": 3}.get(stage_name, 0)

    def _trend_score(self, trend_1h: str) -> int:
        mapping = {
            "bear": 0,
            "lean_bear": 1,
            "neutral": 2,
            "lean_bull": 3,
            "bull": 4,
        }
        return mapping.get(trend_1h, 2)

    def _price_change_ratio(self, previous_price: float, current_price: float) -> float:
        base = max(abs(previous_price), 1e-9)
        return abs(current_price - previous_price) / base

    def _min_repeat_seconds(self, stage_name: str) -> int:
        if stage_name == "A":
            return self.a_min_repeat_seconds
        if stage_name == "B":
            return self.b_min_repeat_seconds
        if stage_name == "C":
            return self.c_min_repeat_seconds
        return 45 * 60

    def _effective_min_repeat_seconds(self, stage_name: str, signal: dict) -> int:
        base = self._min_repeat_seconds(stage_name)
        score = int(signal.get("h1_tai_score", 2))
        rising = bool(signal.get("h1_tai_rising", False))
        multiplier = float(signal.get("h1_tai_repeat_multiplier", 1.0))
        zero_point = bool(signal.get("h1_tai_zero_point", False))
        zero_exception = bool(signal.get("h1_tai_zero_exception", False))
        if zero_point and not zero_exception:
            multiplier = max(multiplier, 3.0)
        elif zero_point and zero_exception:
            multiplier = max(multiplier, 2.2)
        elif score <= 1 and not rising:
            multiplier = max(multiplier, 1.8)
        elif score >= 4 and rising:
            multiplier = min(multiplier, 0.75)
        return max(15 * 60, int(base * multiplier))

    def _tai_allows_upgrade(self, signal: dict) -> bool:
        zero_point = bool(signal.get("h1_tai_zero_point", False))
        zero_exception = bool(signal.get("h1_tai_zero_exception", False))
        if zero_point and not zero_exception:
            return False
        if zero_point and zero_exception:
            return False
        score = int(signal.get("h1_tai_score", 2))
        rising = bool(signal.get("h1_tai_rising", False))
        return score >= 3 or (score >= 2 and rising)

    def _zone_changed_enough(self, previous: dict, current: dict) -> bool:
        prev_low = previous.get("zone_low")
        prev_high = previous.get("zone_high")
        curr_low = current.get("zone_low")
        curr_high = current.get("zone_high")
        if None in (prev_low, prev_high, curr_low, curr_high):
            return False
        prev_mid = (float(prev_low) + float(prev_high)) / 2.0
        curr_mid = (float(curr_low) + float(curr_high)) / 2.0
        atr = max(float(current.get("atr", 0.0)), 1e-9)
        return abs(curr_mid - prev_mid) >= atr * 0.8

    def _has_trend_upgrade(self, previous: dict, current: dict) -> bool:
        prev_score = self._trend_score(previous.get("trend_1h", "neutral"))
        curr_score = self._trend_score(current.get("trend_1h", "neutral"))
        if current["direction"] == "long":
            return curr_score > prev_score
        return curr_score < prev_score

    def should_send(self, signal: dict) -> bool:
        key = self._signal_key(signal)
        previous = self.last_sent.get(key)
        if not previous:
            return True

        now = time.time()
        elapsed = now - float(previous.get("sent_ts", 0.0))
        changed_status = signal.get("status") != previous.get("status")
        if changed_status:
            return True

        if signal["signal"].startswith("X_"):
            tiny_price_move = self._price_change_ratio(previous["price"], signal["price"]) <= self.price_change_threshold
            if tiny_price_move and elapsed < 20 * 60:
                return False
            return True

        stage_now = self._stage_name(signal["signal"])
        stage_prev = previous.get("stage", self._stage_name(previous["signal"]))
        rank_now = self._stage_rank(stage_now)
        rank_prev = self._stage_rank(stage_prev)

        same_phase = signal.get("phase_group") == previous.get("phase_group")
        same_signal = signal["signal"] == previous["signal"]
        tiny_price_move = self._price_change_ratio(previous["price"], signal["price"]) <= self.price_change_threshold
        trend_upgrade = self._has_trend_upgrade(previous, signal)
        zone_upgrade = self._zone_changed_enough(previous, signal)

        # 同方向退级，2小时内不允许反复切换。
        if rank_now < rank_prev and elapsed < self.downgrade_lock_seconds and same_phase:
            return False

        # 同方向同阶段：必须满足最小重发间隔，并且出现趋势/区间升级。
        if rank_now == rank_prev:
            if elapsed < self._effective_min_repeat_seconds(stage_now, signal):
                return False
            if same_phase and same_signal and tiny_price_move and not trend_upgrade and not zone_upgrade:
                return False
            if same_phase and not trend_upgrade and not zone_upgrade:
                return False
            if not self._tai_allows_upgrade(signal) and not trend_upgrade and not zone_upgrade:
                return False
            return True

        # 同方向升阶：必须先经过 1h TAI 节奏放行。
        if rank_now > rank_prev:
            if not self._tai_allows_upgrade(signal):
                return False
            if elapsed < 15 * 60 and same_phase and not trend_upgrade and not zone_upgrade:
                return False
            return True

        return True

    def mark_sent(self, signal: dict):
        key = self._signal_key(signal)
        self.last_sent[key] = {
            "signal": signal["signal"],
            "stage": self._stage_name(signal["signal"]),
            "status": signal.get("status", "active"),
            "price": signal["price"],
            "trend_1h": signal.get("trend_1h", "neutral"),
            "atr": signal.get("atr", 0.0),
            "direction": signal.get("direction"),
            "phase_group": signal.get("phase_group"),
            "zone_low": signal.get("zone_low"),
            "zone_high": signal.get("zone_high"),
            "sent_ts": time.time(),
        }
