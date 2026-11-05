"""Independent 15m W-bottom / demand-reclaim verification layer (0.2).

Own module engine/m15_w_bottom.py, evidence key structure_15m_demand,
tag m15_demand_reclaim_w_bottom. Must NOT reuse m15_supply_reject_m_top.
Cannot alone raise formal.
"""
from __future__ import annotations

import unittest

from engine.m15_w_bottom import build_structure_15m_demand_context, detect_small_w_bottom
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


def _w_bottom_bars():
    """Synthetic 15m path with a clear W into a demand band then reclaim."""
    bars = []
    ts = 1_730_200_000_000
    px = 81200.0
    for i in range(18):
        bars.append(_bar(px, px + 25, px - 25, px - 8, atr=70.0, open_time=ts + i * 900_000))
        px -= 8
    # Left trough taps demand ~80400-80600
    bars.append(_bar(81050, 81080, 80420, 80580, atr=70.0, open_time=ts + 18 * 900_000))
    # Neckline bounce
    bars.append(_bar(80580, 80880, 80540, 80820, atr=70.0, open_time=ts + 19 * 900_000))
    bars.append(_bar(80820, 80900, 80680, 80720, atr=70.0, open_time=ts + 20 * 900_000))
    # Right trough re-taps demand + bullish hammer reclaim (open near lows, close up)
    bars.append(_bar(80450, 80760, 80390, 80650, atr=70.0, open_time=ts + 21 * 900_000))
    # Follow-through reclaim / neckline test
    bars.append(_bar(80650, 80950, 80610, 80910, atr=70.0, open_time=ts + 22 * 900_000))
    return bars


def _klines_1h_neutral():
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
    # Lower zone reclaim style bar
    klines.append(
        _bar(80600, 80800, 80380, 80740, atr=410.0, open_time=base_ts + 40 * 3_600_000)
    )
    return klines


def _evidence_demand(*, with_w: bool = True, with_ifvg: bool = False):
    evidence = {
        "auto_range": {"state": "none", "high": None, "low": None, "approx": True},
        "ifvg": {},
        "sweep": {},
        "delta_profile": {},
    }
    if with_ifvg:
        lower = {
            "top": 80600.0,
            "bottom": 80350.0,
            "direction": -1,
            "inverted": True,
            "mitigated": False,
            "invalidated": False,
            "start_bar": 8,
        }
        evidence["ifvg"] = {
            "nearest_active": lower,
            "zones": [lower],
            "approx": True,
            "timeframe": "1h",
        }
    if with_w:
        evidence["structure_15m_demand"] = {
            "approx": True,
            "timeframe": "15m",
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
            "reason": "m15_demand_reclaim_w_bottom",
        }
    return evidence


def _aux_neutral():
    return {
        "rar_slope": 0.0,
        "rar_above_trigger": True,
        "rar_spread": 8.0,
        "rar_trend_strong": False,
        "momentum_desc": "短线动能中性",
        "temperature_desc": "热度 中性",
        "price_impulse": 0.2,
    }


def _msb_empty():
    return {
        "direction": "neutral",
        "leg_type": "LONG",
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


class WBottomDetectorTests(unittest.TestCase):
    def test_detect_small_w_bottom_with_demand_tap(self):
        bars = _w_bottom_bars()
        w = detect_small_w_bottom(bars, demand_zone=(80350.0, 80600.0), max_bars_ago=6)
        self.assertIsNotNone(w)
        self.assertTrue(w["active"])
        self.assertEqual(w["pattern"], "small_w_bottom")
        self.assertEqual(w["side"], "long")
        self.assertTrue(w["taps_demand"] or w["near_equal"])
        ctx = build_structure_15m_demand_context(bars, demand_zones=[(80350.0, 80600.0)])
        self.assertTrue(ctx["demand_reclaim"])
        self.assertTrue(ctx["active"])
        self.assertEqual(ctx["reason"], "m15_demand_reclaim_w_bottom")
        self.assertIsNotNone(ctx["small_w_bottom"])

    def test_independent_from_m_top_keys(self):
        bars = _w_bottom_bars()
        ctx = build_structure_15m_demand_context(bars, demand_zones=[(80350.0, 80600.0)])
        self.assertNotIn("small_m_top", ctx)
        self.assertNotIn("supply_reject", ctx)
        self.assertNotEqual(ctx.get("reason"), "m15_supply_reject_m_top")


class WBottomTrialScoreTests(unittest.TestCase):
    def test_w_bottom_scores_verification_weight_on_long(self):
        klines = _klines_1h_neutral()
        evidence = _evidence_demand(with_w=True, with_ifvg=False)
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
        long_blob = " ".join(trial["evidence"]["long"])
        self.assertIn("m15_demand_reclaim_w_bottom:+0.20", long_blob)
        self.assertNotIn("m15_supply_reject_m_top", long_blob)
        self.assertNotIn("m15_demand_reclaim_w_bottom", " ".join(trial["evidence"]["short"]))

    def test_w_bottom_alone_cannot_raise_formal(self):
        klines = _klines_1h_neutral()
        evidence = _evidence_demand(with_w=True, with_ifvg=False)
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
        self.assertIn("m15_demand_reclaim_w_bottom", " ".join(trial["evidence"]["long"]))
        self.assertFalse(assessment["directional_catalyst"], msg=assessment)
        self.assertIn("formal_without_directional_catalyst", assessment["hard_blocks"])
        self.assertFalse(assessment["allow_formal"], msg=assessment)


if __name__ == "__main__":
    unittest.main()
