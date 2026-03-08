from datetime import datetime, timedelta


class CooldownStore:
    def __init__(self, cooldown_seconds: int):
        self.cooldown_seconds = cooldown_seconds
        self.last_sent = {}

    def is_in_cooldown(self, key: tuple[str, str, str]) -> bool:
        now = datetime.now()
        previous = self.last_sent.get(key)
        if previous and now - previous < timedelta(seconds=self.cooldown_seconds):
            return True
        return False

    def mark_sent(self, key: tuple[str, str, str]):
        self.last_sent[key] = datetime.now()
