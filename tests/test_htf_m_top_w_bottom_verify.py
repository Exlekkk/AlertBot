"""1H/4H M-top + independent W-bottom verification layer (0.2 each).

Independent evidence keys structure_1h / structure_4h / structure_1h_demand /
structure_4h_demand. Must not reuse 15m results or mirror M↔W. Cannot alone
raise formal.
"""
from __future__ import annotations

import unittest

from engine.m15_w_bottom import (
    build_structure_1h_demand_context,
    build_structure_4h_demand_context,
    detect_small_w_bottom,
)
from engine.structure import (
    build_structure_1h_context,
    build_structure_4h_context,
    detect_small_m_top,
)
from engine.trial_decision import assess_trial_candidate, build_trial_context


def _bar(o, h, l, c, atr=100.0, open_time=1_700_000_000_000, **extra):
    row = {
        "open": float(o),
        "high": float(h),
        "low": float(l),
        "close": float(c),
        "atr": float(atr),
        "volume": 1000.0,
        "open_time": int(open_time),
    }
    row.update(extra)
    return row


def _m_top_bars(*, step_ms: int):
    bars = []
    ts = 1_730_100_000_000
    px = 81000.0
    for i in range(20):
        bars.append(_bar(px, px + 30, px - 30, px + 10, atr=80.0, open_time=ts + i * step_ms))
        px += 10
    bars.append(_bar(81200, 81590, 81150, 81400, atr=80.0, open_time=ts + 20 * step_ms))
    bars.append(_bar(81400, 81450, 81280, 81320, atr=80.0, open_time=ts + 21 * step_ms))
    bars.append(_bar(81320, 81759, 81240, 81246, atr=80.0, open_time=ts + 22 * step_ms))
    bars.append(_bar(81246, 81260, 81027, 81096, atr=80.0, open_time=ts + 23 * step_ms))
    bars.append(_bar(81096, 81215, 81024, 81065, atr=80.0, open_time=ts + 24 * step_ms))
    return bars


def _w_bottom_bars(*, step_ms: int):
    bars = []
    ts = 1_730_200_000_000
    px = 81200.0
    for i in range(18):
        bars.append(_bar(px, px + 25, px - 25, px - 8, atr=70.0, open_time=ts + i * step_ms))
        px -= 8
    bars.append(_bar(81050, 81080, 80420, 80580, atr=70.0, open_time=ts + 18 * step_ms))
    bars.append(_bar(80580, 80880, 80540, 80820, atr=70.0, open_time=ts + 19 * step_ms))
    bars.append(_bar(80820, 80900, 80680, 80720, atr=70.0, open_time=ts + 20 * step_ms))
    bars.append(_bar(80450, 80760, 80390, 80650, atr=70.0, open_time=ts + 21 * step_ms))
    bars.append(_bar(80650, 80950, 80610, 80910, atr=70.0, open_time=ts + 22 * step_ms))
    return bars


def _klines_1h_path():
    base_ts = 1_730_000_000_000
    klines = []
    px = 80700.0
    for i in range(40):
        o = px
        c = px + (15 if i % 2 == 0 else -10)
        klines.append(
            _bar(o, max(o, c) + 30, min(o, c) - 30, c, atr=400.0, open_time=base_ts + i * 3_600_000)
        )
        px = c
    klines.append(_bar(80600, 80800, 80380, 80740, atr=410.0, open_time=base_ts + 40 * 3_600_000))
    return klines


def _aux_neutral(*, impulse: float = -0.5):
    return {
        "rar_slope": 0.0,
        "rar_above_trigger": True,
        "rar_spread": 8.0,
        "rar_trend_strong": False,
        "momentum_desc": "短线动能中性",
        "temperature_desc": "热度 中性",
        "price_impulse": impulse,
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


def _liq():
    return {
        "prev_low": 80200.0,
        "prev_high": 81800.0,
        "sweep_type": "none",
        "reclaim_or_reject": "none",
        "sweep_level": None,
        "recent_sweep_valid": False,
    }


def _m_evidence(key: str, tag: str, timeframe: str):
    return {
        "auto_range": {"state": "none", "high": None, "low": None, "approx": True},
        "ifvg": {},
        "sweep": {},
        "delta_profile": {},
        key: {
            "approx": True,
            "timeframe": timeframe,
            "active": True,
            "supply_reject": True,
            "reject_high": 81759.0,
            "supply_zone": [81751.7, 82061.9],
            "small_m_top": {
                "active": True,
                "side": "short",
                "pattern": "small_m_top",
                "left_high": 81594.3,
                "right_high": 81759.0,
                "m_high": 81759.0,
                "taps_supply": True,
                "near_equal": False,
                "bars_ago": 0,
            },
            "reason": tag,
        },
    }


def _w_evidence(key: str, tag: str, timeframe: str):
    return {
        "auto_range": {"state": "none", "high": None, "low": None, "approx": True},
        "ifvg": {},
        "sweep": {},
        "delta_profile": {},
        key: {
            "approx": True,
            "timeframe": timeframe,
            "active": True,
            "demand_reclaim": True,
            "reclaim_low": 80390.0,
            "demand_zone": [80350.0, 80600.0],
            "small_w_bottom": {
                "active": True,
                "side": "long",
                "pattern": "small_w_bottom",
                "left_low": 80420.0,
                "right_low": 80390.0,
                "neckline": 80880.0,
                "w_low": 80390.0,
                "taps_demand": True,
                "near_equal": True,
                "neckline_reclaim": True,
                "false_bounce": False,
                "bars_ago": 0,
            },
            "reason": tag,
        },
    }


class HtfMTopDetectorTests(unittest.TestCase):
    def test_h1_m_top_context_independent(self):
        bars = _m_top_bars(step_ms=3_600_000)
        m = detect_small_m_top(bars, supply_zone=(81751.7, 82061.9), max_bars_ago=4)
        self.assertIsNotNone(m)
        ctx = build_structure_1h_context(bars, supply_zones=[(81751.7, 82061.9)])
        self.assertEqual(ctx["timeframe"], "1h")
        self.assertTrue(ctx["active"])
        self.assertEqual(ctx["reason"], "h1_supply_reject_m_top")
        self.assertNotEqual(ctx["reason"], "m15_supply_reject_m_top")

    def test_h4_m_top_context_independent(self):
        bars = _m_top_bars(step_ms=14_400_000)
        ctx = build_structure_4h_context(bars, supply_zones=[(81751.7, 82061.9)])
        self.assertEqual(ctx["timeframe"], "4h")
        self.assertTrue(ctx["active"])
        self.assertEqual(ctx["reason"], "h4_supply_reject_m_top")


class HtfWBottomDetectorTests(unittest.TestCase):
    def test_h1_w_bottom_independent_keys(self):
        bars = _w_bottom_bars(step_ms=3_600_000)
        w = detect_small_w_bottom(bars, demand_zone=(80350.0, 80600.0), max_bars_ago=4)
        self.assertIsNotNone(w)
        ctx = build_structure_1h_demand_context(bars, demand_zones=[(80350.0, 80600.0)])
        self.assertEqual(ctx["timeframe"], "1h")
        self.assertTrue(ctx["active"])
        self.assertEqual(ctx["reason"], "h1_demand_reclaim_w_bottom")
        self.assertNotIn("small_m_top", ctx)
        self.assertNotIn("supply_reject", ctx)

    def test_h4_w_bottom_independent_keys(self):
        bars = _w_bottom_bars(step_ms=14_400_000)
        ctx = build_structure_4h_demand_context(bars, demand_zones=[(80350.0, 80600.0)])
        self.assertEqual(ctx["timeframe"], "4h")
        self.assertTrue(ctx["active"])
        self.assertEqual(ctx["reason"], "h4_demand_reclaim_w_bottom")
        self.assertNotEqual(ctx["reason"], "m15_demand_reclaim_w_bottom")


class HtfVerifyTrialScoreTests(unittest.TestCase):
    def test_h1_m_scores_0_2_and_cannot_raise_formal(self):
        klines = _klines_1h_path()
        evidence = _m_evidence("structure_1h", "h1_supply_reject_m_top", "1h")
        trial = build_trial_context(
            klines,
            {"text": "4H 震荡", "relation": "neutral", "h4_direction": "neutral", "bias": "neutral"},
            _liq(),
            _msb_empty(),
            {},
            _aux_neutral(),
            evidence_bundle=evidence,
            range_lock={"active": False},
        )
        short_blob = " ".join(trial["evidence"]["short"])
        self.assertIn("h1_supply_reject_m_top:+0.20", short_blob)
        self.assertNotIn("m15_supply_reject_m_top", short_blob)
        assessment = assess_trial_candidate(
            "short",
            "UPPER_KEY_ZONE_REJECTION",
            (81751.7, 82061.9),
            82061.9,
            klines[-1],
            float(klines[-3]["close"]),
            "key_level",
            "rejected_below",
            trial,
            current_bar=len(klines) - 1,
        )
        self.assertFalse(assessment["directional_catalyst"], msg=assessment)
        self.assertIn("formal_without_directional_catalyst", assessment["hard_blocks"])
        self.assertFalse(assessment["allow_formal"], msg=assessment)

    def test_h4_m_scores_0_2(self):
        klines = _klines_1h_path()
        evidence = _m_evidence("structure_4h", "h4_supply_reject_m_top", "4h")
        trial = build_trial_context(
            klines,
            {"text": "4H 震荡", "relation": "neutral", "h4_direction": "neutral", "bias": "neutral"},
            _liq(),
            _msb_empty(),
            {},
            _aux_neutral(),
            evidence_bundle=evidence,
            range_lock={"active": False},
        )
        self.assertIn("h4_supply_reject_m_top:+0.20", " ".join(trial["evidence"]["short"]))

    def test_h1_w_scores_0_2_and_cannot_raise_formal(self):
        klines = _klines_1h_path()
        evidence = _w_evidence("structure_1h_demand", "h1_demand_reclaim_w_bottom", "1h")
        trial = build_trial_context(
            klines,
            {"text": "4H 震荡", "relation": "neutral", "h4_direction": "neutral", "bias": "neutral"},
            _liq(),
            _msb_empty(),
            {},
            _aux_neutral(impulse=0.2),
            evidence_bundle=evidence,
            range_lock={"active": False},
        )
        long_blob = " ".join(trial["evidence"]["long"])
        self.assertIn("h1_demand_reclaim_w_bottom:+0.20", long_blob)
        self.assertNotIn("m15_demand_reclaim_w_bottom", long_blob)
        zone = (80350.0, 80600.0)
        assessment = assess_trial_candidate(
            "long",
            "LOWER_KEY_ZONE_RECLAIM",
            zone,
            zone[0],
            klines[-1],
            float(klines[-3]["close"]),
            "key_level",
            "reclaimed_above",
            trial,
            current_bar=len(klines) - 1,
        )
        self.assertFalse(assessment["directional_catalyst"], msg=assessment)
        self.assertFalse(assessment["allow_formal"], msg=assessment)

    def test_h4_w_scores_0_2(self):
        klines = _klines_1h_path()
        evidence = _w_evidence("structure_4h_demand", "h4_demand_reclaim_w_bottom", "4h")
        trial = build_trial_context(
            klines,
            {"text": "4H 震荡", "relation": "neutral", "h4_direction": "neutral", "bias": "neutral"},
            _liq(),
            _msb_empty(),
            {},
            _aux_neutral(impulse=0.2),
            evidence_bundle=evidence,
            range_lock={"active": False},
        )
        self.assertIn("h4_demand_reclaim_w_bottom:+0.20", " ".join(trial["evidence"]["long"]))

    def test_15m_evidence_does_not_impersonate_h1(self):
        """Putting only structure_15m must not emit h1/h4 tags."""
        klines = _klines_1h_path()
        evidence = _m_evidence("structure_15m", "m15_supply_reject_m_top", "15m")
        trial = build_trial_context(
            klines,
            {"text": "4H 震荡", "relation": "neutral", "h4_direction": "neutral", "bias": "neutral"},
            _liq(),
            _msb_empty(),
            {},
            _aux_neutral(),
            evidence_bundle=evidence,
            range_lock={"active": False},
        )
        short_blob = " ".join(trial["evidence"]["short"])
        self.assertIn("m15_supply_reject_m_top:+0.20", short_blob)
        self.assertNotIn("h1_supply_reject_m_top", short_blob)
        self.assertNotIn("h4_supply_reject_m_top", short_blob)


if __name__ == "__main__":
    unittest.main()
