import importlib
import sys
import types
import unittest


class SignalStateAndMessageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if "requests" not in sys.modules:
            sys.modules["requests"] = types.SimpleNamespace(post=lambda *args, **kwargs: None)
        cls.telegram = importlib.import_module("services.telegram")

    def test_state_store_dedup_and_upgrade(self):
        from engine.cooldown import SignalStateStore

        store = SignalStateStore(price_change_threshold=0.001)
        c_signal = {
            "signal": "C_LEFT_LONG",
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "direction": "long",
            "priority": 3,
            "status": "early",
            "price": 100.0,
        }

        self.assertTrue(store.should_send(c_signal))
        store.mark_sent(c_signal)

        self.assertFalse(store.should_send({**c_signal, "price": 100.05}))

        upgraded_signal = {
            **c_signal,
            "signal": "B_PULLBACK_LONG",
            "priority": 2,
            "status": "active",
            "price": 100.05,
        }
        self.assertTrue(store.should_send(upgraded_signal))

    def test_engine_message_has_only_expected_fields(self):
        message = self.telegram.format_engine_message(
            signal="A_LONG",
            symbol="BTCUSDT",
            timeframe="15m",
            priority=1,
            price=65000.12,
            trend_1h="bull",
            status="active",
        )
        for field in ["优先级", "类型", "标的", "价格", "周期", "1h方向", "状态"]:
            self.assertIn(field, message)

        for forbidden in ["触发", "来源", "SMCT", "BOS", "MSS", "FVG", "Evil MACD"]:
            self.assertNotIn(forbidden, message)


if __name__ == "__main__":
    unittest.main()
