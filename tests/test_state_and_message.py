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

    def _store(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        tmp.close()
        return importlib.import_module("engine.cooldown").SignalStateStore(
            price_change_threshold=0.001,
            state_file=tmp.name,
        )

    def test_same_anchor_c_signal_does_not_repeat(self):
        store = self._store()
        c_signal = {
            "signal": "C_LEFT_LONG",
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "direction": "long",
            "priority": 3,
            "status": "watch",
            "price": 100.0,
            "phase_rank": 1,
            "phase_name": "early",
            "phase_context": "long|early|neutral|long:early:t123",
            "phase_anchor": "long:early:t123",
            "h1_tai_bias": "flat",
            "h1_tai_slot": "123:flat",
        }

        self.assertTrue(store.should_send(c_signal))
        store.mark_sent(c_signal)
        self.assertFalse(store.should_send({**c_signal, "price": 100.8}))

    def test_upgrade_requires_h1_tai_cooperation(self):
        store = self._store()
        c_signal = {
            "signal": "C_LEFT_LONG",
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "direction": "long",
            "priority": 3,
            "status": "watch",
            "price": 100.0,
            "phase_rank": 1,
            "phase_name": "early",
            "phase_context": "long|early|neutral|long:early:t123",
            "phase_anchor": "long:early:t123",
            "h1_tai_bias": "flat",
            "h1_tai_slot": "123:flat",
        }
        store.mark_sent(c_signal)

        blocked_upgrade = {
            **c_signal,
            "signal": "A_LONG",
            "phase_rank": 3,
            "phase_name": "continuation",
            "phase_context": "long|continuation|neutral|long:early:t123",
            "price": 101.0,
            "h1_tai_bias": "flat",
            "h1_tai_slot": "123:flat",
        }
        self.assertFalse(store.should_send(blocked_upgrade))

        allowed_upgrade = {
            **blocked_upgrade,
            "h1_tai_bias": "support",
            "h1_tai_slot": "124:support",
        }
        self.assertTrue(store.should_send(allowed_upgrade))
    def test_same_anchor_phase_upgrade_can_open_without_new_tai_slot(self):
        store = self._store()
        c_signal = {
            "signal": "C_LEFT_SHORT",
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "direction": "short",
            "priority": 3,
            "status": "watch",
            "price": 100.0,
            "phase_rank": 1,
            "phase_name": "early",
            "phase_context": "short|early|neutral|short:early:t123",
            "phase_anchor": "short:early:t123",
            "h1_tai_bias": "flat",
            "h1_tai_slot": "123:flat",
            "trigger_state": "weak",
        }
        store.mark_sent(c_signal)

        upgrade = {
            **c_signal,
            "signal": "B_PULLBACK_SHORT",
            "phase_rank": 2,
            "phase_name": "repair",
            "price": 98.8,
            "trigger_state": "ready",
        }
        self.assertTrue(store.should_send(upgrade))

    def test_cross_anchor_rearm_allows_new_watch_after_old_stronger_signal(self):
        store = self._store()
        prev_signal = {
            "signal": "A_LONG",
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "direction": "long",
            "priority": 1,
            "status": "active",
            "price": 100.0,
            "phase_rank": 3,
            "phase_name": "continuation",
            "phase_context": "long|continuation|neutral|long:continuation:t100",
            "phase_anchor": "long:continuation:t100",
            "h1_tai_bias": "support",
            "h1_tai_slot": "100:support",
            "trigger_state": "ready",
        }
        store.mark_sent(prev_signal)

        rearm = {
            **prev_signal,
            "signal": "C_LEFT_LONG",
            "phase_rank": 1,
            "phase_name": "early",
            "phase_context": "long|early|neutral|long:early:t101",
            "phase_anchor": "long:early:t101",
            "price": 99.6,
            "trigger_state": "weak",
        }
        self.assertTrue(store.should_send(rearm))


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
        for field in ["交易提示", "操作建议", "标的", "参考价位区间", "总体趋势方向", "预计启动时段", "状态"]:
            self.assertIn(field, message)

        for forbidden in ["来源", "SMCT", "BOS", "MSS", "FVG", "Evil MACD"]:
            self.assertNotIn(forbidden, message)


if __name__ == "__main__":
    unittest.main()
