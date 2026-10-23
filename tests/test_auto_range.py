"""Auto Range 契约字段与 Breakout/Deviation 语义冒烟测试。"""
from __future__ import annotations

import unittest

from engine.auto_range import build_auto_range_context
from engine.range_lock import build_range_lock_context


def _bar(o, h, l, c, atr=50.0, vol=100.0, ts=0):
    return {
        "open": float(o),
        "high": float(h),
        "low": float(l),
        "close": float(c),
        "atr": float(atr),
        "volume": float(vol),
        "open_time": ts,
    }


def _range_series(n=120, low=9800.0, high=10200.0):
    """在箱内来回旋转，制造触边与中线穿越。"""
    bars = []
    mid = (low + high) / 2.0
    for i in range(n):
        # 交替靠近上下沿
        if i % 4 == 0:
            o, c = mid, high - 10
            h, l = high - 5, mid - 20
        elif i % 4 == 1:
            o, c = high - 10, mid
            h, l = high - 8, mid - 30
        elif i % 4 == 2:
            o, c = mid, low + 10
            h, l = mid + 20, low + 5
        else:
            o, c = low + 10, mid
            h, l = mid + 30, low + 8
        bars.append(_bar(o, h, l, c, atr=40.0, ts=i * 3_600_000))
    return bars


class AutoRangeContractTests(unittest.TestCase):
    def test_context_has_contract_fields(self):
        ctx = build_auto_range_context(_range_series())
        for key in (
            "state",
            "high",
            "low",
            "mid",
            "q25",
            "q75",
            "bars_held",
            "height_pct",
            "last_event",
            "event_bar_ts",
            "approx",
        ):
            self.assertIn(key, ctx)
        self.assertTrue(ctx["approx"])
        self.assertIn(ctx["state"], {"none", "provisional", "live", "broken"})

    def test_range_lock_maps_auto_range_and_keeps_legacy_keys(self):
        bars = _range_series()
        ctx = build_range_lock_context(
            bars,
            {"text": "4H 震荡", "relation": "neutral"},
            {},
            {"direction": "neutral", "leg_type": "SHORT", "quality": 0},
            {"matrix_direction": "neutral"},
            {},
            vp={},
            ict={"coexist": False},
        )
        self.assertIn("auto_range", ctx)
        self.assertTrue(ctx["approx"])
        for key in ("active", "box_low", "box_high", "accepted_breakout", "cluster", "box_position"):
            self.assertIn(key, ctx)
        # Breakout 未发生时不应是 accepted
        if ctx["auto_range"].get("last_event") in {None, "deviation_up", "deviation_down"}:
            self.assertEqual(ctx["accepted_breakout"], "none")

    def test_ict_coexist_still_activates_lock(self):
        bars = _range_series(n=80)
        ctx = build_range_lock_context(
            bars,
            {"text": "4H 偏多", "relation": "aligned"},
            {},
            {"direction": "bull", "leg_type": "LONG", "quality": 90},
            {"matrix_direction": "bull"},
            {},
            vp={"inside_value_area": False},
            ict={"coexist": True, "source": "explicit_feed"},
        )
        self.assertTrue(ctx["active"])
        self.assertTrue(ctx["ict_ob_conflict"])


if __name__ == "__main__":
    unittest.main()
