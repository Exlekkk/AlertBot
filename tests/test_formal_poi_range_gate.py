"""Formal POI gate (L 代拍 #40): 触达 inverted IFVG 才许主区；无箱禁 orphan range。"""
from __future__ import annotations

import unittest

from engine.key_zones import _auto_range_box_active, _select_zone, decide_key_zone_observation


def _bar(o, h, l, c, atr=100.0, open_time=1_700_000_000_000):
    return {
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "atr": atr,
        "volume": 1000.0,
        "open_time": open_time,
    }


def _klines_reject_upper():
    klines = [_bar(10000, 10050, 9950, 10000, open_time=1_700_000_000_000 + i * 3_600_000) for i in range(25)]
    klines += [
        _bar(10100, 10200, 10080, 10150, atr=100.0, open_time=1_700_000_000_000 + 25 * 3_600_000),
        _bar(10150, 10180, 10050, 10120, atr=100.0, open_time=1_700_000_000_000 + 26 * 3_600_000),
        # Touches prev_high area and rejects below.
        _bar(10080, 10140, 9950, 9990, atr=100.0, open_time=1_700_000_000_000 + 27 * 3_600_000),
    ]
    return klines


def _liq():
    return {
        "prev_low": 9600,
        "prev_high": 10100,
        "sweep_type": "none",
        "reclaim_or_reject": "none",
        "sweep_level": None,
        "recent_sweep_valid": False,
    }


def _msb_empty():
    return {
        "direction": "neutral",
        "leg_type": "SHORT",
        "quality": 0,
        "has_order_block_context": False,
        "metrics": {},
        "fibonacci": {},
    }


class AutoRangeBoxActiveTests(unittest.TestCase):
    def test_none_state_is_inactive(self):
        self.assertFalse(
            _auto_range_box_active({"auto_range": {"state": "none", "high": None, "low": None}})
        )

    def test_live_box_is_active(self):
        self.assertTrue(
            _auto_range_box_active({"auto_range": {"state": "live", "high": 110.0, "low": 100.0}})
        )

    def test_range_lock_box_is_active(self):
        self.assertTrue(
            _auto_range_box_active({}, {"active": True, "box_low": 100.0, "box_high": 110.0})
        )


class OrphanRangeEdgeGateTests(unittest.TestCase):
    def test_ar_none_range_upper_only_does_not_select(self):
        """AR=none + only prev_high range touch → no formal POI (2026-10-27 incident)."""
        selected = _select_zone(
            _klines_reject_upper(),
            _liq(),
            _msb_empty(),
            evidence_bundle={"auto_range": {"state": "none", "high": None, "low": None}},
            range_lock={"active": False},
        )
        self.assertEqual(selected, {})

        decision = decide_key_zone_observation(
            "BTCUSDT",
            "1h",
            _klines_reject_upper(),
            {"text": "4H 震荡", "relation": "neutral"},
            _liq(),
            _msb_empty(),
            {},
            {"momentum_desc": "动能 偏弱", "temperature_desc": "热度 中性"},
            evidence_bundle={"auto_range": {"state": "none", "high": None, "low": None}},
            observation_state={"inside_zone": False, "reentry_count": 0},
            range_lock={"active": False},
        )
        self.assertFalse(decision["should_alert"])
        self.assertNotEqual(decision.get("zone_source"), "range_upper_zone")
        self.assertIn(decision.get("zone_source"), {"none", "pending_revalidation"})

    def test_inverted_ifvg_touch_selects_ifvg_zone(self):
        """触达 inverted IFVG → zone_source=ifvg_zone（AR=none 也可；优先于 orphan range）。"""
        ifvg_zone = (10050.0, 10140.0)
        evidence = {
            "auto_range": {"state": "none", "high": None, "low": None},
            "ifvg": {
                "nearest_active": {
                    "top": ifvg_zone[1],
                    "bottom": ifvg_zone[0],
                    "direction": 1,  # bullish origin inverted → resistance / upper
                    "inverted": True,
                    "invalidated": False,
                },
                "zones": [],
                "approx": True,
            },
        }
        selected = _select_zone(
            _klines_reject_upper(),
            _liq(),
            _msb_empty(),
            evidence_bundle=evidence,
            range_lock={"active": False},
        )
        self.assertEqual(selected.get("source"), "ifvg_zone")
        self.assertEqual(selected.get("side"), "upper")

        decision = decide_key_zone_observation(
            "BTCUSDT",
            "1h",
            _klines_reject_upper(),
            {"text": "4H 震荡", "relation": "neutral"},
            _liq(),
            _msb_empty(),
            {},
            {"momentum_desc": "动能 偏弱", "temperature_desc": "热度 中性", "rar_slope": -1.0},
            evidence_bundle=evidence,
            observation_state={"inside_zone": False, "reentry_count": 0},
            range_lock={"active": False},
        )
        self.assertEqual(decision["zone_source"], "ifvg_zone")
        # Formal short rejection path when candle rejected below IFVG.
        self.assertEqual(decision["direction"], "short")
        self.assertIn(decision["alert_type"], {"UPPER_KEY_ZONE_REJECTION", "UPPER_KEY_ZONE_TEST", "RANGE_UPPER_PROBE", "FAST_REBOUND_OBSERVE"})


    def test_nearby_untouched_inverted_ifvg_does_not_fire(self):
        """00:00 反例：旁边有 inverted IFVG 但本根未触达 → 不发。

        禁止硬套 IFVG 成图1区间，也禁止掉进 orphan range_upper。
        """
        # Reject near prev_high≈10100；IFVG 远在上方 10280–10380，本根 high=10140 碰不到。
        evidence = {
            "auto_range": {"state": "none", "high": None, "low": None},
            "ifvg": {
                "nearest_active": {
                    "top": 10380.0,
                    "bottom": 10280.0,
                    "direction": 1,
                    "inverted": True,
                    "invalidated": False,
                },
                "zones": [],
                "approx": True,
            },
        }
        selected = _select_zone(
            _klines_reject_upper(),
            _liq(),
            _msb_empty(),
            evidence_bundle=evidence,
            range_lock={"active": False},
        )
        self.assertEqual(selected, {})

        decision = decide_key_zone_observation(
            "BTCUSDT",
            "1h",
            _klines_reject_upper(),
            {"text": "4H 震荡", "relation": "neutral"},
            _liq(),
            _msb_empty(),
            {},
            {"momentum_desc": "动能 偏弱", "temperature_desc": "热度 中性"},
            evidence_bundle=evidence,
            observation_state={"inside_zone": False, "reentry_count": 0},
            range_lock={"active": False},
        )
        self.assertFalse(decision["should_alert"])
        self.assertNotEqual(decision.get("zone_source"), "ifvg_zone")
        self.assertNotEqual(decision.get("zone_source"), "range_upper_zone")
        self.assertIn(decision.get("zone_source"), {"none", "pending_revalidation"})

    def test_touched_inverted_ifvg_beats_orphan_range_geometry(self):
        """金标准：触达 inverted IFVG → 主区=IFVG（像图1 80968–81176），非 range_upper。"""
        ifvg_zone = (10050.0, 10140.0)
        evidence = {
            "auto_range": {"state": "none", "high": None, "low": None},
            "ifvg": {
                "nearest_active": {
                    "top": ifvg_zone[1],
                    "bottom": ifvg_zone[0],
                    "direction": 1,
                    "inverted": True,
                    "invalidated": False,
                },
                "zones": [],
                "approx": True,
            },
        }
        selected = _select_zone(
            _klines_reject_upper(),
            _liq(),  # prev_high=10100，若无闸会出 range_upper
            _msb_empty(),
            evidence_bundle=evidence,
            range_lock={"active": False},
        )
        self.assertEqual(selected.get("source"), "ifvg_zone")
        self.assertTrue(selected.get("inverted"))
        zl, zh = selected["zone"]
        self.assertAlmostEqual(zl, ifvg_zone[0], places=2)
        self.assertAlmostEqual(zh, ifvg_zone[1], places=2)



class ReentryCountTests(unittest.TestCase):
    def test_reentry_increments_only_on_outside_to_inside(self):
        evidence = {
            "auto_range": {"state": "none", "high": None, "low": None},
            "ifvg": {
                "nearest_active": {
                    "top": 10140.0,
                    "bottom": 10050.0,
                    "direction": 1,
                    "inverted": True,
                    "invalidated": False,
                },
                "zones": [],
                "approx": True,
            },
        }
        first = decide_key_zone_observation(
            "BTCUSDT",
            "1h",
            _klines_reject_upper(),
            {"text": "4H 震荡", "relation": "neutral"},
            _liq(),
            _msb_empty(),
            {},
            {"momentum_desc": "动能 偏弱", "temperature_desc": "热度 中性"},
            evidence_bundle=evidence,
            observation_state={"inside_zone": False, "reentry_count": 5},
        )
        self.assertEqual(first["observation_update"]["reentry_count"], 6)

        # Still inside same evaluation path with was_inside True → no bump.
        second = decide_key_zone_observation(
            "BTCUSDT",
            "1h",
            _klines_reject_upper(),
            {"text": "4H 震荡", "relation": "neutral"},
            _liq(),
            _msb_empty(),
            {},
            {"momentum_desc": "动能 偏弱", "temperature_desc": "热度 中性"},
            evidence_bundle=evidence,
            observation_state=first["observation_update"],
        )
        self.assertEqual(
            second["observation_update"]["reentry_count"],
            first["observation_update"]["reentry_count"],
        )


if __name__ == "__main__":
    unittest.main()
