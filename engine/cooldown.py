import time


class SignalStateStore:
    def __init__(
        self,
        price_change_threshold: float = 0.001,
        b_signal_cooldown_seconds: int = 75 * 60,
        c_signal_cooldown_seconds: int = 45 * 60,
    ):
        self.price_change_threshold = price_change_threshold
        self.b_signal_cooldown_seconds = b_signal_cooldown_seconds
        self.c_signal_cooldown_seconds = c_signal_cooldown_seconds
        self.last_sent: dict[tuple[str, str, str], dict] = {}

    def _price_change_ratio(self, previous_price: float, current_price: float) -> float:
        base = max(abs(previous_price), 1e-9)
        return abs(current_price - previous_price) / base

    def _cooldown_seconds_for(self, signal_name: str) -> int:
        if signal_name.startswith("B_"):
            return self.b_signal_cooldown_seconds
        if signal_name.startswith("C_"):
            return self.c_signal_cooldown_seconds
        return 0

    def should_send(self, signal: dict) -> bool:
        key = (signal["symbol"], signal["timeframe"], signal["direction"])
        previous = self.last_sent.get(key)
        if not previous:
            return True

        same_signal = previous["signal"] == signal["signal"]
        same_status = previous["status"] == signal["status"]
        upgraded = (
            signal["priority"] < previous["priority"]
            or signal["status"] != previous["status"]
        )

        if upgraded:
            return True

        cooldown_seconds = self._cooldown_seconds_for(signal["signal"])
        if same_signal and same_status and cooldown_seconds > 0:
            elapsed = time.time() - previous.get("sent_at", 0.0)
            if elapsed < cooldown_seconds:
                return False

        tiny_price_move = (
            self._price_change_ratio(previous["price"], signal["price"])
            <= self.price_change_threshold
        )
        if same_signal and same_status and tiny_price_move:
            return False

        return True

    def mark_sent(self, signal: dict):
        key = (signal["symbol"], signal["timeframe"], signal["direction"])
        self.last_sent[key] = {
            "signal": signal["signal"],
            "priority": signal["priority"],
            "status": signal["status"],
            "price": signal["price"],
            "sent_at": time.time(),
        }
