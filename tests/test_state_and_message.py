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

    def test_same_classifier_same_anchor_c_signal_does_not_repeat(self):
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
            "market_heat": "cold",
        }
        self.assertTrue(store.should_send(c_signal))
        store.mark_sent(c_signal)
        self.assertFalse(store.should_send({**c_signal, "price": 100.8}))

    def test_publish_gate_blocks_opposite_direction_conflict(self):
        store = self._store()
        first = {
            "signal": "A_SHORT",
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "direction": "short",
            "priority": 1,
            "status": "active",
            "price": 100.0,
            "phase_rank": 3,
            "phase_name": "continuation",
            "phase_context": "short|continuation|neutral|short:continuation:t100",
            "phase_anchor": "short:continuation:t100",
            "h1_tai_bias": "support",
            "h1_tai_slot": "100:support",
            "trigger_state": "explosive",
            "market_heat": "cold",
        }
        store.mark_sent(first)
        opposite = {
            "signal": "B_PULLBACK_LONG",
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "direction": "long",
            "priority": 2,
            "status": "active",
            "price": 100.5,
            "phase_rank": 2,
            "phase_name": "repair",
            "phase_context": "long|repair|neutral|long:repair:t101",
            "phase_anchor": "long:repair:t101",
            "h1_tai_bias": "support",
            "h1_tai_slot": "101:support",
            "trigger_state": "ready",
            "market_heat": "cold",
        }
        self.assertFalse(store.should_send(opposite))

    def test_publish_gate_blocks_same_direction_cross_classifier_churn(self):
        store = self._store()
        first = {
            "signal": "A_SHORT",
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "direction": "short",
            "priority": 1,
            "status": "active",
            "price": 100.0,
            "phase_rank": 3,
            "phase_name": "continuation",
            "phase_context": "short|continuation|neutral|short:continuation:t100",
            "phase_anchor": "short:continuation:t100",
            "h1_tai_bias": "support",
            "h1_tai_slot": "100:support",
            "trigger_state": "explosive",
            "market_heat": "cold",
        }
        store.mark_sent(first)
        same_direction_other_classifier = {
            "signal": "B_PULLBACK_SHORT",
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "direction": "short",
            "priority": 2,
            "status": "active",
            "price": 99.8,
            "phase_rank": 2,
            "phase_name": "repair",
            "phase_context": "short|repair|neutral|short:repair:t101",
            "phase_anchor": "short:repair:t101",
            "h1_tai_bias": "support",
            "h1_tai_slot": "101:support",
            "trigger_state": "ready",
            "market_heat": "cold",
        }
        self.assertFalse(store.should_send(same_direction_other_classifier))

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
