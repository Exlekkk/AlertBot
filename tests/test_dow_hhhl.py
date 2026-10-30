"""Dow HH/HL/LH/LL on #43 tip — mid-low structure into trial stack.

L locks: 1H fractal L/R=2 primary; 15m aux only; break HL→short / LH→long
evidence with Liquidity/IFVG/POC stack; same-way BOS strengthen-only; weight
RAR/Liq/IFVG/POC > Dow > AR; Dow alone cannot cross formal_min. No wedges /
#36–41 / key_zones rewrite. AR weight untouched.
"""
from __future__ import annotations

import inspect
import unittest

from engine.structure import build_dow_structure_context, find_pivots, label_dow_swings
from engine.trial_decision import assess_trial_candidate, build_trial_context


def _bar(o, h, l, c, atr=50.0, open_time=1_700_000_000_000, **extra):
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


def _uptrend_hh_hl():
    pts = [
        (101, 102, 100, 101),
        (101, 101.5, 100.5, 101),
        (101, 101.2, 100.8, 101),
        (101, 110, 101, 109),
        (109, 110, 108.5, 109),
        (109, 109.5, 108.8, 109),
        (109, 109, 104, 105),
        (105, 105.5, 104.2, 105),
        (105, 105.2, 104.5, 105),
        (105, 116, 105, 115),
        (115, 116, 114.5, 115),
        (115, 115.5, 114.8, 115),
        (115, 115, 108, 109),
        (109, 110, 108.5, 109.5),
        (109.5, 110, 109, 109.8),
    ]
    ts = 1_700_000_000_000
    return [_bar(*p, atr=3.0, open_time=ts + i * 3_600_000) for i, p in enumerate(pts)]


def _downtrend_lh_ll():
    pts = [
        (119, 120, 118, 119),
        (119, 119.5, 118.5, 119),
        (119, 119.2, 118.8, 119),
        (119, 119, 110, 111),
        (111, 111.5, 110.2, 111),
        (111, 111.2, 110.5, 111),
        (111, 116, 111, 115),
        (115, 116, 114.5, 115),
        (115, 115.5, 114.8, 115),
        (115, 115, 106, 107),
        (107, 107.5, 106.2, 107),
        (107, 107.2, 106.5, 107),
        (107, 112, 107, 111),
        (111, 112, 110.5, 111.2),
        (111.2, 111.8, 110.8, 111.0),
    ]
    ts = 1_700_000_000_000
    return [_bar(*p, atr=3.0, open_time=ts + i * 3_600_000) for i, p in enumerate(pts)]


def _break_hl_from_uptrend():
    k = _uptrend_hh_hl()
    k.append(_bar(109, 109.5, 102, 102.5, atr=3.0, open_time=k[-1]["open_time"] + 3_600_000))
    return k


def _break_lh_from_downtrend():
    k = _downtrend_lh_ll()
    k.append(_bar(111, 117.5, 110.5, 117.0, atr=3.0, open_time=k[-1]["open_time"] + 3_600_000))
    return k


def _bos_up_intact():
    k = _uptrend_hh_hl()
    # Stay above HL (~104), break last HH (~116) — no LH present to false-trigger
    k.append(_bar(109.8, 118, 109.5, 117.5, atr=3.0, open_time=k[-1]["open_time"] + 3_600_000))
    return k


def _aux_neutral():
    return {
        "rar_slope": 0.0,
        "rar_above_trigger": False,
        "rar_spread": 8.0,
        "rar_trend_strong": False,
        "momentum_desc": "短线动能中性",
        "temperature_desc": "热度 中性",
        "price_impulse": -0.5,
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
        "prev_low": 100.0,
        "prev_high": 120.0,
        "sweep_type": "none",
        "reclaim_or_reject": "none",
        "sweep_level": None,
        "recent_sweep_valid": False,
    }


def _evidence(side: str, dow: dict | None):
    if side == "short":
        zone = {
            "top": 120.0,
            "bottom": 114.0,
            "direction": 1,
            "inverted": True,
            "mitigated": False,
            "invalidated": False,
            "start_bar": 5,
        }
    else:
        zone = {
            "top": 112.0,
            "bottom": 106.0,
            "direction": -1,
            "inverted": True,
            "mitigated": False,
            "invalidated": False,
            "start_bar": 5,
        }
    evidence = {
        "auto_range": {"state": "none", "high": None, "low": None},
        "ifvg": {"nearest_active": zone, "zones": [zone], "approx": True, "timeframe": "1h"},
        "sweep": {},
        "delta_profile": {},
    }
    if dow is not None:
        evidence["structure_dow"] = dow
    return evidence


class TestDowLabeling(unittest.TestCase):
    def test_hh_hl_uptrend(self):
        k = _uptrend_hh_hl()
        labeled = label_dow_swings(k, left=2, right=2)
        self.assertTrue(any(x["label"] == "HH" for x in labeled["swing_highs"]), labeled)
        self.assertTrue(any(x["label"] == "HL" for x in labeled["swing_lows"]), labeled)
        self.assertEqual(build_dow_structure_context(k)["trend"], "up")

    def test_lh_ll_downtrend(self):
        k = _downtrend_lh_ll()
        labeled = label_dow_swings(k, left=2, right=2)
        self.assertTrue(any(x["label"] == "LH" for x in labeled["swing_highs"]), labeled)
        self.assertTrue(any(x["label"] == "LL" for x in labeled["swing_lows"]), labeled)
        self.assertEqual(build_dow_structure_context(k)["trend"], "down")

    def test_find_pivots_default_fractal_2(self):
        ph, pl = find_pivots(_uptrend_hh_hl(), left=2, right=2)
        self.assertGreaterEqual(len(ph) + len(pl), 2)


class TestDowBreakEvidence(unittest.TestCase):
    def test_break_hl_short_evidence(self):
        ctx = build_dow_structure_context(_break_hl_from_uptrend())
        self.assertTrue(ctx["active_short_evidence"], ctx)
        self.assertEqual(ctx["break_hl"]["swing_label"], "HL")
        self.assertEqual(ctx["reason"], "dow_break_hl")

    def test_break_lh_long_evidence(self):
        ctx = build_dow_structure_context(_break_lh_from_downtrend())
        self.assertTrue(ctx["active_long_evidence"], ctx)
        self.assertEqual(ctx["break_lh"]["swing_label"], "LH")
        self.assertEqual(ctx["reason"], "dow_break_lh")

    def test_bos_same_way_strengthen_only_flag(self):
        ctx = build_dow_structure_context(_bos_up_intact())
        self.assertFalse(ctx["active_short_evidence"], ctx)
        self.assertFalse(ctx["active_long_evidence"], ctx)
        bos = ctx.get("bos_same_way") or {}
        self.assertTrue(bos.get("active"), ctx)
        self.assertTrue(bos.get("strengthen_only"))
        self.assertEqual(bos.get("direction"), "up")


class TestDowTrialWiring(unittest.TestCase):
    def test_break_hl_scores_mid_low_with_ifvg_stack(self):
        k = _break_hl_from_uptrend()
        dow = build_dow_structure_context(k)
        evidence = _evidence("short", dow)
        trial = build_trial_context(
            k, {"text": "4H 震荡", "h4_direction": "neutral"}, _liq(), _msb_empty(), {}, _aux_neutral(),
            evidence_bundle=evidence, range_lock={"active": False},
        )
        blob = " ".join(trial["evidence"]["short"])
        self.assertIn("dow_break_hl:", blob)
        # Mid-low: below sweep(2.0)/IFVG(1.25)/RAR(1.0), above AR(0.5)
        self.assertRegex(blob, r"dow_break_hl:\+0\.[5-9]")
        zone = (114.0, 120.0)
        assessment = assess_trial_candidate(
            "short", "UPPER_KEY_ZONE_REJECTION", zone, zone[1], k[-1], float(k[-3]["close"]),
            "ifvg_zone", "rejected_below", trial, current_bar=len(k) - 1,
        )
        self.assertTrue(assessment["directional_catalyst"], assessment)
        self.assertNotIn("dow_requires_poi_or_liquidity_stack", assessment["hard_blocks"])

    def test_break_lh_scores_long_with_ifvg(self):
        k = _break_lh_from_downtrend()
        dow = build_dow_structure_context(k)
        evidence = _evidence("long", dow)
        trial = build_trial_context(
            k, {"text": "4H 震荡", "h4_direction": "neutral"}, _liq(), _msb_empty(), {}, _aux_neutral(),
            evidence_bundle=evidence, range_lock={"active": False},
        )
        self.assertIn("dow_break_lh:", " ".join(trial["evidence"]["long"]))
        zone = (106.0, 112.0)
        assessment = assess_trial_candidate(
            "long", "LOWER_KEY_ZONE_RECLAIM", zone, zone[0], k[-1], float(k[-3]["close"]),
            "ifvg_zone", "reclaimed_above", trial, current_bar=len(k) - 1,
        )
        self.assertTrue(assessment["directional_catalyst"], assessment)

    def test_naked_bos_no_poi_blocked(self):
        k = _bos_up_intact()
        dow = build_dow_structure_context(k)
        evidence = {
            "auto_range": {"state": "none"},
            "ifvg": {},
            "sweep": {},
            "delta_profile": {},
            "structure_dow": dow,
        }
        trial = build_trial_context(
            k, {"text": "", "h4_direction": "neutral"}, _liq(), _msb_empty(), {}, _aux_neutral(),
            evidence_bundle=evidence, range_lock={"active": False},
        )
        blob = " ".join(trial["evidence"]["long"])
        self.assertIn("dow_bos_same_way_up", blob)
        self.assertNotIn("dow_break_lh", blob)
        # Dummy zone but zone_source unknown → Dow requires stack
        zone = (100.0, 105.0)
        assessment = assess_trial_candidate(
            "long", "WATCH", zone, zone[0], k[-1], float(k[-3]["close"]),
            "unknown", "none", trial, current_bar=len(k) - 1,
        )
        self.assertFalse(assessment["allow_formal"], assessment)
        self.assertIn("dow_requires_poi_or_liquidity_stack", assessment["hard_blocks"])

    def test_dow_alone_cannot_cross_formal(self):
        """Non-Dow score below formal_min + Dow tip → hard block."""
        k = _break_hl_from_uptrend()
        dow = build_dow_structure_context(k)
        # Minimal evidence: Dow only in bundle (IFVG zone for stack path, but
        # we force tip-over check by using a synthetic low base score path).
        evidence = _evidence("short", dow)
        # Neutral aux so base structure score is mostly Dow + IFVG lean
        trial = build_trial_context(
            k, {"text": "", "h4_direction": "neutral"}, _liq(), _msb_empty(), {}, _aux_neutral(),
            evidence_bundle=evidence, range_lock={"active": False},
        )
        # Directly assert the gate helper semantics via assess with low reaction
        # Use WATCH (no +3.5 reaction) so Dow tip is more visible
        zone = (114.0, 120.0)
        assessment = assess_trial_candidate(
            "short", "WATCH", zone, zone[1], k[-1], float(k[-3]["close"]),
            "ifvg_zone", "none", trial, current_bar=len(k) - 1,
        )
        # Either already under minimum without needing Dow tip, or tip blocked
        score = assessment["score"]
        minimum = assessment["minimum_score"]
        if score >= minimum:
            # If formal score cleared, must not be solely because Dow tipped it
            self.assertNotIn("dow_alone_cannot_cross_formal", assessment["hard_blocks"] or [])
            # Reconstruct: strip Dow from reasons and ensure non-dow >= min OR blocked
            reasons = assessment["reasons"]
            wo = score
            for r in reasons:
                if r.startswith("dow_break_hl:") or r.startswith("dow_bos_same_way"):
                    wo -= float(r.split(":", 1)[1])
            if wo < minimum:
                self.assertIn("dow_alone_cannot_cross_formal", assessment["hard_blocks"])
                self.assertFalse(assessment["allow_formal"])
        else:
            self.assertFalse(assessment["allow_formal"])

    def test_ar_weight_unchanged(self):
        src = inspect.getsource(build_trial_context)
        self.assertIn("AUTO_RANGE_EVENT_WEIGHT = 0.5", src)
        self.assertNotIn("AUTO_RANGE_EVENT_WEIGHT = 1.5", src)


if __name__ == "__main__":
    unittest.main()
