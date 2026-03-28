class SignalStateStore:
    def __init__(
        self,
        price_change_threshold: float = 0.001,
        b_upgrade_atr_ratio: float = 0.4,
        c_upgrade_atr_ratio: float = 0.25,
    ):
        self.price_change_threshold = price_change_threshold
        self.b_upgrade_atr_ratio = b_upgrade_atr_ratio
        self.c_upgrade_atr_ratio = c_upgrade_atr_ratio
        # ABC 按方向阶段去重；X 继续独立去重。
        self.last_sent: dict[tuple[str, str, str], dict] = {}

    def _price_change_ratio(self, previous_price: float, current_price: float) -> float:
        base = max(abs(previous_price), 1e-9)
        return abs(current_price - previous_price) / base

    def _trend_score(self, trend_1h: str) -> int:
        mapping = {
            "bear": 0,
            "lean_bear": 1,
            "neutral": 2,
            "lean_bull": 3,
            "bull": 4,
        }
        return mapping.get(trend_1h, 2)

    def _stage_name(self, signal_name: str) -> str:
        if signal_name.startswith("A_"):
            return "A"
        if signal_name.startswith("B_"):
            return "B"
        if signal_name.startswith("C_"):
            return "C"
        return signal_name

    def _is_x_signal(self, signal_name: str) -> bool:
        return signal_name.startswith("X_")

    def _has_trend_upgrade(self, previous: dict, current: dict) -> bool:
        prev_score = self._trend_score(previous.get("trend_1h", "neutral"))
        curr_score = self._trend_score(current.get("trend_1h", "neutral"))
        if current["direction"] == "long":
            return curr_score > prev_score
        return curr_score < prev_score

    def _has_price_upgrade(self, previous: dict, current: dict) -> bool:
        previous_price = previous["price"]
        current_price = current["price"]
        atr = max(float(current.get("atr", 0.0)), 1e-9)

        stage = self._stage_name(current["signal"])
        if stage == "B":
            threshold = atr * self.b_upgrade_atr_ratio
        elif stage == "C":
            threshold = atr * self.c_upgrade_atr_ratio
        else:
            threshold = atr * 0.15

        if current["direction"] == "long":
            return current_price > previous_price + threshold
        return current_price < previous_price - threshold

    def _signal_key(self, signal: dict) -> tuple[str, str, str]:
        if self._is_x_signal(signal["signal"]):
            return (signal["symbol"], signal["timeframe"], signal["signal"])
        return (signal["symbol"], signal["timeframe"], signal["direction"])

    def should_send(self, signal: dict) -> bool:
        key = self._signal_key(signal)
        previous = self.last_sent.get(key)
        if not previous:
            return True

        changed_status = signal["status"] != previous["status"]
        if changed_status:
            return True

        stage_now = self._stage_name(signal["signal"])
        stage_prev = previous.get("stage", self._stage_name(previous["signal"]))

        # ABC 阶段切换时，允许重发；这样同方向只保留当前阶段。
        if stage_now != stage_prev:
            return True

        tiny_price_move = (
            self._price_change_ratio(previous["price"], signal["price"])
            <= self.price_change_threshold
        )
        if previous["signal"] == signal["signal"] and previous["status"] == signal["status"] and tiny_price_move:
            return False

        trend_upgrade = self._has_trend_upgrade(previous, signal)
        price_upgrade = self._has_price_upgrade(previous, signal)

        if not trend_upgrade and not price_upgrade:
            return False
        return True

    def mark_sent(self, signal: dict):
        key = self._signal_key(signal)
        self.last_sent[key] = {
            "signal": signal["signal"],
            "stage": self._stage_name(signal["signal"]),
            "priority": signal.get("priority", 0),
            "status": signal["status"],
            "price": signal["price"],
            "trend_1h": signal.get("trend_1h", "neutral"),
            "atr": signal.get("atr", 0.0),
            "direction": signal["direction"],
        }
