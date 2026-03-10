class SignalStateStore:
    def __init__(self, price_change_threshold: float = 0.001):
        self.price_change_threshold = price_change_threshold
        self.last_sent: dict[tuple[str, str, str], dict] = {}

    def _price_change_ratio(self, previous_price: float, current_price: float) -> float:
        base = max(abs(previous_price), 1e-9)
        return abs(current_price - previous_price) / base

    def should_send(self, signal: dict) -> bool:
        key = (signal["symbol"], signal["timeframe"], signal["direction"])
        previous = self.last_sent.get(key)
        if not previous:
            return True

        same_signal = previous["signal"] == signal["signal"]
        same_status = previous["status"] == signal["status"]
        no_upgrade = signal["priority"] >= previous["priority"]
        tiny_price_move = self._price_change_ratio(previous["price"], signal["price"]) <= self.price_change_threshold

        return not (same_signal and same_status and no_upgrade and tiny_price_move)

    def mark_sent(self, signal: dict):
        key = (signal["symbol"], signal["timeframe"], signal["direction"])
        self.last_sent[key] = {
            "signal": signal["signal"],
            "priority": signal["priority"],
            "status": signal["status"],
            "price": signal["price"],
        }
