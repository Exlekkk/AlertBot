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

    def test_engine_message_uses_compact_template_for_a(self):
        message = self.telegram.format_engine_message(
            signal="A_LONG",
            symbol="BTCUSDT",
            timeframe="15m",
            priority=1,
            price=65000.12,
            trend_1h="bull",
            status="active",
            confidence=88,
        )
        for field in ["交易提示｜A类｜BTCUSDT", "背景：", "区间：", "关键位：", "观察：", "状态："]:
            self.assertIn(field, message)

        for old_field in ["操作建议", "标的", "总体趋势方向", "预计启动时段", "时效说明"]:
            self.assertNotIn(old_field, message)

    def test_engine_message_uses_compact_template_for_x(self):
        message = self.telegram.format_engine_message(
            signal="X_BREAKOUT_SHORT",
            symbol="BTCUSDT",
            timeframe="15m",
            priority=4,
            price=66700.0,
            trend_1h="bear",
            status="active",
            trigger_level=66781.91,
            entry_zone_low=66722.16,
            entry_zone_high=66861.27,
            abnormal_type="上插针扫流动性",
            confidence=95,
        )
        for field in ["异动预警｜X类｜BTCUSDT", "背景：", "关键位：", "反抽观察区：", "观察：", "状态："]:
            self.assertIn(field, message)


if __name__ == "__main__":
    unittest.main()
