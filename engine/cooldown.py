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
        # 改为按具体 signal 独立去重，不再按 direction 共用状态。
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

    def _is_same_signal_family(self, previous_signal: str, current_signal: str) -> bool:
        # 现在要求 A 就是 A，B 就是 B，C 就是 C。
        # 这里直接只认“同一个具体 signal”。
        return previous_signal == current_signal

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

        signal_name = current["signal"]
        if signal_name.startswith("B_"):
            threshold = atr * self.b_upgrade_atr_ratio
        elif signal_name.startswith("C_"):
            threshold = atr * self.c_upgrade_atr_ratio
        else:
            threshold = 0.0

        if current["direction"] == "long":
            return current_price > previous_price + threshold
        return current_price < previous_price - threshold

    def _is_b_or_c_signal(self, signal_name: str) -> bool:
        return signal_name.startswith("B_") or signal_name.startswith("C_")

    def _signal_key(self, signal: dict) -> tuple[str, str, str]:
        # 独立 key：symbol + timeframe + 具体 signal
        # A_SHORT 不再压掉 B_PULLBACK_SHORT / C_LEFT_SHORT
        return (signal["symbol"], signal["timeframe"], signal["signal"])

    def should_send(self, signal: dict) -> bool:
        key = self._signal_key(signal)
        previous = self.last_sent.get(key)
        if not previous:
            return True

        same_signal = previous["signal"] == signal["signal"]
        same_status = previous["status"] == signal["status"]
        changed_status = signal["status"] != previous["status"]

        if changed_status:
            return True

        tiny_price_move = (
            self._price_change_ratio(previous["price"], signal["price"])
            <= self.price_change_threshold
        )

        if same_signal and same_status and tiny_price_move:
            return False

        if self._is_b_or_c_signal(signal["signal"]) and self._is_same_signal_family(previous["signal"], signal["signal"]):
            trend_upgrade = self._has_trend_upgrade(previous, signal)
            price_upgrade = self._has_price_upgrade(previous, signal)

            if not trend_upgrade and not price_upgrade:
                return False

        return True

    def mark_sent(self, signal: dict):
        key = self._signal_key(signal)
        self.last_sent[key] = {
            "signal": signal["signal"],
            "priority": signal.get("priority", 0),
            "status": signal["status"],
            "price": signal["price"],
            "trend_1h": signal.get("trend_1h", "neutral"),
            "atr": signal.get("atr", 0.0),
        }
