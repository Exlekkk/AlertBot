import importlib
import sys
import tempfile
import types
import unittest


class SignalStateAndMessageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if "requests" not in sys.modules:
            sys.modules["requests"] = types.SimpleNamespace(post=lambda *args, **kwargs: None)
        cls.telegram = importlib.import_module("services.telegram")

    def test_state_store_blocks_conflicting_direction_same_segment(self):
        from engine.cooldown import SignalStateStore

        with tempfile.TemporaryDirectory() as tmp:
            store = SignalStateStore(price_change_threshold=0.001, state_file=f"{tmp}/state.json")
            a_short = {
                "signal": "A_SHORT",
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "direction": "short",
                "status": "active",
                "price": 100.0,
                "phase_rank": 3,
                "state_1h": "trend_drive_short",
                "segment_id": "BTCUSDT|15m|trend_drive_short|short|neutral",
                "cooldown_seconds": 1800,
            }
            self.assertTrue(store.should_send(a_short))
            store.mark_sent(a_short)

            conflicting_b_long = {
                "signal": "B_PULLBACK_LONG",
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "direction": "long",
                "status": "active",
                "price": 100.05,
                "phase_rank": 2,
                "state_1h": "repair_long",
                "segment_id": "BTCUSDT|15m|trend_drive_short|short|neutral",
                "cooldown_seconds": 1800,
            }
            self.assertFalse(store.should_send(conflicting_b_long))

    def test_state_store_blocks_lower_rank_same_segment(self):
        from engine.cooldown import SignalStateStore

        with tempfile.TemporaryDirectory() as tmp:
            store = SignalStateStore(price_change_threshold=0.001, state_file=f"{tmp}/state.json")
            a_long = {
                "signal": "A_LONG",
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "direction": "long",
                "status": "active",
                "price": 100.0,
                "phase_rank": 3,
                "state_1h": "trend_drive_long",
                "segment_id": "BTCUSDT|15m|trend_drive_long|long|warm",
                "cooldown_seconds": 1800,
            }
            self.assertTrue(store.should_send(a_long))
            store.mark_sent(a_long)

            b_long = {
                "signal": "B_PULLBACK_LONG",
                "symbol": "BTCUSDT",
                "timeframe": "15m",
                "direction": "long",
                "status": "active",
                "price": 100.02,
                "phase_rank": 2,
                "state_1h": "repair_long",
                "segment_id": "BTCUSDT|15m|trend_drive_long|long|warm",
                "cooldown_seconds": 1800,
            }
            self.assertFalse(store.should_send(b_long))

    def test_tai_heat_is_heat_not_direction(self):
        from engine.signals import _tai_heat, _tai_budget_mode

        k = {"tai_value": 9.0, "tai_p20": 10.0, "tai_p40": 20.0, "tai_p60": 30.0, "tai_p80": 40.0}
        self.assertEqual(_tai_heat(k), "cold")
        self.assertEqual(_tai_budget_mode(_tai_heat(k)), "restricted")

        k2 = {"tai_value": 35.0, "tai_p20": 10.0, "tai_p40": 20.0, "tai_p60": 30.0, "tai_p80": 40.0}
        self.assertEqual(_tai_heat(k2), "warm")
        self.assertEqual(_tai_budget_mode(_tai_heat(k2)), "expanded")

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
        for field in ["交易提示", "操作建议", "标的", "参考价位区间", "总体趋势方向", "状态"]:
            self.assertIn(field, message)

        for forbidden in ["触发", "来源", "SMCT", "BOS", "MSS", "FVG", "Evil MACD"]:
            self.assertNotIn(forbidden, message)


if __name__ == "__main__":
    unittest.main()
