from pathlib import Path
import importlib
import sys
import tempfile
import time
import types
import unittest


class SignalStateAndMessageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = str(Path(__file__).resolve().parents[1])
        if root not in sys.path:
            sys.path.insert(0, root)
        if "requests" not in sys.modules:
            sys.modules["requests"] = types.SimpleNamespace(post=lambda *args, **kwargs: None)
        cls.telegram = importlib.import_module("services.telegram")

    def _make_store(self):
        from engine.cooldown import SignalStateStore

        tmp = tempfile.NamedTemporaryFile(delete=False)
        tmp.close()
        return SignalStateStore(price_change_threshold=0.001, state_file=tmp.name)

    def test_state_store_allows_upgrade_from_c_to_b(self):
        store = self._make_store()
        c_signal = {
            "signal": "C_LEFT_LONG",
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "direction": "long",
            "priority": 3,
            "status": "watch",
            "price": 100.0,
            "zone_low": 99.0,
            "zone_high": 101.0,
            "structure_basis": ["support_sweep", "ema_reclaim"],
            "phase_name": "early",
            "phase_context": "long|early|supportive|100-101",
            "phase_rank": 1,
            "trigger_state": "weak",
            "trend_1h": "lean_bull",
            "bg_bias": "supportive",
            "atr": 1.0,
        }

        self.assertTrue(store.should_send(c_signal))
        store.mark_sent(c_signal)

        upgraded_signal = {
            **c_signal,
            "signal": "B_PULLBACK_LONG",
            "priority": 2,
            "status": "active",
            "price": 100.15,
            "phase_name": "repair",
            "phase_context": "long|repair|supportive|100-101",
            "phase_rank": 2,
            "trigger_state": "ready",
        }
        self.assertTrue(store.should_send(upgraded_signal))

    def test_state_store_suppresses_repeated_a_continuation(self):
        store = self._make_store()
        a_signal = {
            "signal": "A_LONG",
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "direction": "long",
            "priority": 1,
            "status": "active",
            "price": 68000.0,
            "zone_low": 67600.0,
            "zone_high": 68040.0,
            "structure_basis": ["bos", "fvg_support", "liquidity_sweep"],
            "phase_name": "continuation",
            "phase_context": "long|continuation|supportive|67600-68040",
            "phase_rank": 3,
            "trigger_state": "ready",
            "trend_1h": "lean_bull",
            "bg_bias": "supportive",
            "atr": 120.0,
            "cooldown_seconds": 45 * 60,
        }

        self.assertTrue(store.should_send(a_signal))
        store.mark_sent(a_signal)

        repeated_signal = {
            **a_signal,
            "price": 68018.0,
            "zone_low": 67610.0,
            "zone_high": 68042.0,
        }
        self.assertFalse(store.should_send(repeated_signal))

    def test_state_store_allows_reissue_when_setup_meaningfully_changes(self):
        store = self._make_store()
        first_signal = {
            "signal": "A_LONG",
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "direction": "long",
            "priority": 1,
            "status": "active",
            "price": 68000.0,
            "zone_low": 67600.0,
            "zone_high": 68040.0,
            "structure_basis": ["bos", "fvg_support"],
            "phase_name": "continuation",
            "phase_context": "long|continuation|supportive|67600-68040",
            "phase_rank": 3,
            "trigger_state": "ready",
            "trend_1h": "lean_bull",
            "bg_bias": "supportive",
            "atr": 120.0,
            "cooldown_seconds": 45 * 60,
        }
        self.assertTrue(store.should_send(first_signal))
        store.mark_sent(first_signal)

        previous = store.last_sent[store._family_key(first_signal)]
        previous["sent_at"] = time.time() - 50 * 60

        changed_signal = {
            **first_signal,
            "price": 68680.0,
            "zone_low": 68220.0,
            "zone_high": 68820.0,
            "structure_basis": ["bos", "new_sweep", "breakout_hold"],
            "phase_context": "long|continuation|supportive|68220-68820",
            "trigger_state": "explosive",
        }
        self.assertTrue(store.should_send(changed_signal))

    def test_engine_message_has_current_expected_fields(self):
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

        for forbidden in ["BOS", "MSS", "FVG", "Evil MACD"]:
            self.assertNotIn(forbidden, message)


if __name__ == "__main__":
    unittest.main()
