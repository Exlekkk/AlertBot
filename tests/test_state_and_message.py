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
        cls.signals = importlib.import_module("engine.signals")

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
            "signature": "C_LEFT_LONG:long:100-101:mss_up",
        }

        self.assertTrue(store.should_send(c_signal))
        store.mark_sent(c_signal)
        self.assertFalse(store.should_send({**c_signal, "price": 100.8}))

    def test_independent_classifiers_do_not_share_same_bucket_state(self):
        store = self._store()
        a_signal = {
            "signal": "A_LONG",
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "direction": "long",
            "priority": 1,
            "status": "active",
            "price": 100.0,
            "phase_rank": 3,
            "phase_name": "continuation",
            "phase_context": "long|continuation|neutral|long:continuation:t123",
            "phase_anchor": "long:continuation:t123",
            "h1_tai_bias": "support",
            "h1_tai_slot": "123:support",
            "signature": "A_LONG:long:100-101:mss_up,bos_up",
        }
        b_signal = {
            "signal": "B_PULLBACK_LONG",
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "direction": "long",
            "priority": 2,
            "status": "active",
            "price": 100.1,
            "phase_rank": 2,
            "phase_name": "repair",
            "phase_context": "long|repair|neutral|long:repair:t123",
            "phase_anchor": "long:repair:t123",
            "h1_tai_bias": "support",
            "h1_tai_slot": "123:support",
            "signature": "B_PULLBACK_LONG:long:100-101:mss_up,bullish_fvg_fill",
        }
        store.mark_sent(a_signal)
        self.assertTrue(store.should_send(b_signal))

    def test_same_classifier_same_anchor_tiny_move_is_blocked(self):
        store = self._store()
        a_signal = {
            "signal": "A_SHORT",
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "direction": "short",
            "priority": 1,
            "status": "active",
            "price": 100.0,
            "phase_rank": 3,
            "phase_name": "continuation",
            "phase_context": "short|continuation|neutral|short:continuation:t123",
            "phase_anchor": "short:continuation:t123",
            "h1_tai_bias": "support",
            "h1_tai_slot": "123:support",
            "signature": "A_SHORT:short:99-101:mss_down,bos_down",
        }
        store.mark_sent(a_signal)
        self.assertFalse(store.should_send({**a_signal, "price": 99.95}))

    def test_a_quality_filter_blocks_recent_impulse_trap(self):
        base = {
            "ema10": 100.0,
            "ema20": 99.0,
            "cm_macd_above_signal": True,
            "cm_hist_up": True,
            "cm_hist_down": False,
            "sss_hist": 1.0,
            "sss_bear_div": False,
            "sss_overbought_warning": False,
            "sss_bull_div": False,
            "sss_oversold_warning": False,
            "tai_rising": True,
            "atr": 10.0,
        }
        recent = [
            {**base, "high": 120.0, "low": 112.0, "close": 118.0},
            {**base, "high": 119.0, "low": 108.0, "close": 110.0},
            {**base, "high": 111.0, "low": 101.0, "close": 103.0},
            {**base, "high": 105.0, "low": 98.0, "close": 100.0},
            {**base, "high": 103.0, "low": 97.0, "close": 99.0},
            {**base, "high": 102.0, "low": 97.5, "close": 100.5},
        ]
        latest = recent[-1]
        prev = recent[-2]
        k_1h = {**base, "close": 101.0, "ema10": 100.5, "ema20": 100.0}
        p_1h = {**base, "close": 100.5, "ema10": 100.0, "ema20": 99.5}
        ok = self.signals._a_quality_filter(
            "long", latest, prev, k_1h, p_1h, "neutral", ["mss_up", "bos_up"], recent
        )
        self.assertFalse(ok)

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
