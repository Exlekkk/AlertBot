"""Formal POI gate: orphan range edges without Auto Range box must not fire."""
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
        """Inverted IFVG in hit range → zone_source=ifvg_zone even when AR=none."""
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
