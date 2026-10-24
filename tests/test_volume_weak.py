"""Unclosed abnormal-volume weak reminder scaffold tests."""
from __future__ import annotations

import os
import unittest
from unittest import mock

from engine.volume_weak import (
    DEFAULT_MIN_VOLUME_RATIO,
    evaluate_forming_volume_weak,
    format_volume_weak_message_draft,
    should_send_volume_weak_tg,
)
from engine.x_signals import MIN_15M_ABNORMAL_VOLUME


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


class VolumeWeakTests(unittest.TestCase):
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
        # ratio = 6100/1000 = 6.1 >= 1.8; bullish body
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
            self.assertFalse(d.get("tg_enabled") and should_send_volume_weak_tg(d))

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

    def test_draft_copy_forbids_formal_trial_words(self):
        d = {
            "should_alert": True,
            "side": "long",
            "symbol": "BTCUSDT",
            "volume_15m": 7000,
            "volume_ratio_15m": 2.1,
        }
        msg = format_volume_weak_message_draft(d)
        self.assertIn("弱提醒", msg)
        self.assertNotIn("试多", msg)
        self.assertNotIn("试空", msg)
        self.assertIn("TODO(L)", msg)

    def test_default_min_ratio_is_draft_value(self):
        self.assertGreaterEqual(DEFAULT_MIN_VOLUME_RATIO, 1.8)


if __name__ == "__main__":
    unittest.main()
