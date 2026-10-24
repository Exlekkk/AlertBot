"""Unclosed abnormal-volume weak reminder tests (L-locked frequency + copy)."""
from __future__ import annotations

import os
import unittest
from unittest import mock

from engine.volume_weak import (
    DEFAULT_COOLDOWN_BARS_15M,
    DEFAULT_MIN_VOLUME_RATIO,
    DEFAULT_OPPOSITE_COOLDOWN_BARS,
    evaluate_forming_volume_weak,
    format_volume_weak_message,
    should_send_volume_weak_tg,
)
from engine.x_signals import MIN_15M_ABNORMAL_VOLUME, MIN_1H_ABNORMAL_VOLUME


def _bar(*, o, h, l, c, vol, vol_sma=1000.0, ts=0):
    return {
        "open": float(o),
        "high": float(h),
        "low": float(l),
        "close": float(c),
        "volume": float(vol),
        "vol_sma20": float(vol_sma),
        "atr": 50.0,
        "open_time": ts,
    }


class VolumeWeakFrequencyTests(unittest.TestCase):
    def test_locked_frequency_constants(self):
        self.assertEqual(DEFAULT_MIN_VOLUME_RATIO, 1.8)
        self.assertEqual(DEFAULT_COOLDOWN_BARS_15M, 4)
        self.assertEqual(DEFAULT_OPPOSITE_COOLDOWN_BARS, 2)
        self.assertEqual(MIN_15M_ABNORMAL_VOLUME, 6000.0)
        self.assertEqual(MIN_1H_ABNORMAL_VOLUME, 12000.0)

    def test_decision_carries_locked_cooldowns(self):
        bars = [
            _bar(o=100, h=101, l=99, c=100.5, vol=500, vol_sma=500, ts=1),
            _bar(o=100.5, h=101, l=100, c=100.8, vol=500, vol_sma=500, ts=2),
            _bar(
                o=100,
                h=105,
                l=99,
                c=104,
                vol=MIN_15M_ABNORMAL_VOLUME + 100,
                vol_sma=1000.0,
                ts=3,
            ),
        ]
        d = evaluate_forming_volume_weak("BTCUSDT", bars, None)
        self.assertTrue(d["should_alert"])
        self.assertEqual(d["recommended_cooldown_bars"], 4)
        self.assertEqual(d["opposite_cooldown_bars"], 2)

    def test_ratio_just_below_lock_is_silent(self):
        """Prefer miss: abs floor met but ratio 1.79 < 1.8 -> no alert."""
        bars = [
            _bar(o=100, h=101, l=99, c=100, vol=100, ts=1),
            _bar(o=100, h=101, l=99, c=100, vol=100, ts=2),
            _bar(
                o=100,
                h=105,
                l=99,
                c=104,
                vol=MIN_15M_ABNORMAL_VOLUME + 100,
                vol_sma=(MIN_15M_ABNORMAL_VOLUME + 100) / 1.79,
                ts=3,
            ),
        ]
        d = evaluate_forming_volume_weak("BTCUSDT", bars)
        self.assertFalse(d["should_alert"])
        self.assertEqual(d["reason"], "volume_not_abnormal")


class VolumeWeakEvalTests(unittest.TestCase):
    def test_forming_abnormal_volume_long(self):
        bars = [
            _bar(o=100, h=101, l=99, c=100.5, vol=500, vol_sma=500, ts=1),
            _bar(o=100.5, h=101, l=100, c=100.8, vol=500, vol_sma=500, ts=2),
            _bar(
                o=100,
                h=105,
                l=99,
                c=104,
                vol=MIN_15M_ABNORMAL_VOLUME + 100,
                vol_sma=1000.0,
                ts=3,
            ),
        ]
        d = evaluate_forming_volume_weak("BTCUSDT", bars, None)
        self.assertTrue(d["should_alert"])
        self.assertEqual(d["side"], "long")
        self.assertTrue(d["forming"])
        self.assertTrue(d["formal_1h_isolated"])
        self.assertEqual(d["family"], "volume_weak")

    def test_below_threshold_silent(self):
        bars = [
            _bar(o=100, h=101, l=99, c=100, vol=100, ts=1),
            _bar(o=100, h=101, l=99, c=100, vol=100, ts=2),
            _bar(o=100, h=101, l=99, c=101, vol=500, vol_sma=1000.0, ts=3),
        ]
        d = evaluate_forming_volume_weak("BTCUSDT", bars)
        self.assertFalse(d["should_alert"])
        self.assertEqual(d["reason"], "volume_not_abnormal")

    def test_tg_gated_off_by_default(self):
        bars = [
            _bar(o=100, h=101, l=99, c=100, vol=100, ts=1),
            _bar(o=100, h=101, l=99, c=100, vol=100, ts=2),
            _bar(
                o=110,
                h=111,
                l=100,
                c=101,
                vol=MIN_15M_ABNORMAL_VOLUME + 50,
                vol_sma=1000.0,
                ts=3,
            ),
        ]
        d = evaluate_forming_volume_weak("BTCUSDT", bars)
        self.assertTrue(d["should_alert"])
        with mock.patch.dict(os.environ, {"SMCT_ABNORMAL_VOLUME_WEAK_ENABLED": "0"}, clear=False):
            self.assertFalse(should_send_volume_weak_tg(d))

    def test_tg_on_when_env_enabled(self):
        bars = [
            _bar(o=100, h=101, l=99, c=100, vol=100, ts=1),
            _bar(o=100, h=101, l=99, c=100, vol=100, ts=2),
            _bar(
                o=110,
                h=111,
                l=100,
                c=101,
                vol=MIN_15M_ABNORMAL_VOLUME + 50,
                vol_sma=1000.0,
                ts=3,
            ),
        ]
        with mock.patch.dict(os.environ, {"SMCT_ABNORMAL_VOLUME_WEAK_ENABLED": "1"}, clear=False):
            d = evaluate_forming_volume_weak("BTCUSDT", bars)
            self.assertTrue(d["should_alert"])
            self.assertTrue(should_send_volume_weak_tg(d))


class VolumeWeakFormatTests(unittest.TestCase):
    def test_long_copy_locked(self):
        msg = format_volume_weak_message(
            {
                "should_alert": True,
                "side": "long",
                "symbol": "BTCUSDT",
                "volume_15m": 7123.4,
                "volume_ratio_15m": 2.14,
            }
        )
        self.assertIn("\U0001f4cd BTC \u672a\u6536\u76d8\u653e\u91cf\u5f31\u63d0\u9192", msg)
        self.assertIn("\u504f\u591a\U0001f7e2", msg)
        self.assertIn("vol\u22487123", msg)
        self.assertIn("ratio\u22482.1", msg)
        self.assertIn("\u8fd9\u4e0d\u662f 1H \u6b63\u5f0f\u89c2\u5bdf", msg)
        self.assertIn("\u6700\u7ec8\u4ee5 1H / 4H \u4e3a\u51c6", msg)
        self.assertNotIn("\u8bd5\u591a", msg)
        self.assertNotIn("\u8bd5\u7a7a", msg)
        self.assertNotIn("\u8349\u7a3f", msg)
        self.assertNotIn("TODO", msg)
        lines = msg.split("\n")
        self.assertEqual(lines[0], "\U0001f4cd BTC \u672a\u6536\u76d8\u653e\u91cf\u5f31\u63d0\u9192")
        self.assertEqual(lines[1], "")
        self.assertTrue(lines[2].startswith("15m "))

    def test_short_copy_uses_red_marker(self):
        msg = format_volume_weak_message(
            {
                "side": "short",
                "symbol": "BTCUSDT",
                "volume_15m": 8000,
                "volume_ratio_15m": 3.0,
            }
        )
        self.assertIn("\u504f\u7a7a\U0001f534", msg)
        self.assertNotIn("\u504f\u591a\U0001f7e2", msg)
        self.assertIn("vol\u22488000", msg)
        self.assertIn("ratio\u22483.0", msg)
        self.assertNotIn("\u8bd5\u591a", msg)
        self.assertNotIn("\u8bd5\u7a7a", msg)


if __name__ == "__main__":
    unittest.main()
