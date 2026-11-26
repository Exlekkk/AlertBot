"""Hard gate: 1h Dow bullish OR core_levels lean=bull → forbid formal short.

Baseline tip 2290937. Kills A2/A3-class against-structure formal shorts.
A1-class same-way short (Dow break HL, lean≠bull) must still pass the gate.
No long-side mirror in this knife.
"""
from __future__ import annotations

import unittest

from engine.structure import build_dow_structure_context
from engine.trial_decision import assess_trial_candidate, build_trial_context

from tests.test_dow_hhhl import (
    _aux_neutral,
    _break_hl_from_uptrend,
    _break_lh_from_downtrend,
    _evidence,
    _liq,
    _msb_empty,
    _uptrend_hh_hl,
)


def _aux_with_core(lean: str):
    aux = _aux_neutral()
    aux["core_levels_filter"] = {
        "allowed": True,
        "filter_only": True,
        "lean": lean,
        "squeeze": False,
        "midline_event": None,
    }
    return aux


def _assess_short(k, evidence, aux, alert_type="UPPER_KEY_ZONE_REJECTION", zone_source="ifvg_zone"):
    trial = build_trial_context(
        k,
        {"text": "4H 震荡", "h4_direction": "neutral"},
        _liq(),
        _msb_empty(),
        {},
        aux,
        evidence_bundle=evidence,
        range_lock={"active": False},
    )
    zone = (114.0, 120.0)
    return assess_trial_candidate(
        "short",
        alert_type,
        zone,
        zone[1],
        k[-1],
        float(k[-3]["close"]),
        zone_source,
        "rejected_below",
        trial,
        current_bar=len(k) - 1,
    ), trial


class TestFormalShortBullStructureGate(unittest.TestCase):
    def test_context_exposes_dow_and_lean(self):
        k = _uptrend_hh_hl()
        dow = build_dow_structure_context(k)
        evidence = _evidence("short", dow)
        evidence["core_levels_filter"] = {
            "allowed": True,
            "filter_only": True,
            "lean": "bull",
            "squeeze": False,
        }
        trial = build_trial_context(
            k,
            {"text": "", "h4_direction": "neutral"},
            _liq(),
            _msb_empty(),
            {},
            _aux_neutral(),
            evidence_bundle=evidence,
            range_lock={"active": False},
        )
        self.assertEqual(trial["core_levels_lean"], "bull")
        self.assertEqual(trial["structure_dow"]["trend"], "up")
        self.assertFalse(trial["structure_dow"]["active_short_evidence"])

    def test_a2_dow_long_and_lean_bull_blocks_formal_short(self):
        """A2-class: Dow break LH (active long) + lean bull → block."""
        k = _break_lh_from_downtrend()
        dow = build_dow_structure_context(k)
        self.assertTrue(dow["active_long_evidence"], dow)
        evidence = _evidence("short", dow)
        # Give short side a strong stack so only the new gate should stop formal.
        evidence["structure_15m"] = {
            "active": True,
            "supply_reject": True,
            "small_m_top": {"active": True},
        }
        assessment, trial = _assess_short(k, evidence, _aux_with_core("bull"))
        self.assertEqual(trial["core_levels_lean"], "bull")
        self.assertTrue(trial["structure_dow"]["active_long_evidence"])
        self.assertIn("formal_short_blocked_by_bull_structure", assessment["hard_blocks"])
        self.assertFalse(assessment["allow_formal"], assessment)

    def test_a3_trend_up_blocks_formal_short(self):
        """A3-class: 1h Dow trend=up (偏多) blocks formal short even lean neutral."""
        k = _uptrend_hh_hl()
        dow = build_dow_structure_context(k)
        self.assertEqual(dow["trend"], "up", dow)
        self.assertFalse(dow["active_short_evidence"], dow)
        evidence = _evidence("short", dow)
        evidence["structure_15m"] = {
            "active": True,
            "supply_reject": True,
            "small_m_top": {"active": True},
        }
        assessment, trial = _assess_short(k, evidence, _aux_with_core("neutral"))
        self.assertEqual(trial["structure_dow"]["trend"], "up")
        self.assertIn("formal_short_blocked_by_bull_structure", assessment["hard_blocks"])
        self.assertFalse(assessment["allow_formal"], assessment)

    def test_lean_bull_alone_blocks_formal_short(self):
        """core_levels lean=bull alone forbids formal short (OR gate)."""
        k = _break_hl_from_uptrend()
        # Force Dow short evidence off by wiping structure_dow to neutral none.
        evidence = _evidence("short", {
            "trend": "none",
            "active_long_evidence": False,
            "active_short_evidence": False,
            "reason": "dow_no_clear_trend",
            "break_hl": None,
            "break_lh": None,
            "bos_same_way": None,
        })
        evidence["structure_15m"] = {
            "active": True,
            "supply_reject": True,
            "small_m_top": {"active": True},
        }
        assessment, _ = _assess_short(k, evidence, _aux_with_core("bull"))
        self.assertIn("formal_short_blocked_by_bull_structure", assessment["hard_blocks"])
        self.assertFalse(assessment["allow_formal"], assessment)

    def test_a1_dow_short_lean_neutral_gate_not_fired(self):
        """A1-class: Dow break HL + lean neutral → gate must NOT fire."""
        k = _break_hl_from_uptrend()
        dow = build_dow_structure_context(k)
        self.assertTrue(dow["active_short_evidence"], dow)
        evidence = _evidence("short", dow)
        evidence["structure_15m"] = {
            "active": True,
            "supply_reject": True,
            "small_m_top": {"active": True},
        }
        assessment, trial = _assess_short(k, evidence, _aux_with_core("neutral"))
        self.assertTrue(trial["structure_dow"]["active_short_evidence"])
        self.assertEqual(trial["core_levels_lean"], "neutral")
        self.assertNotIn("formal_short_blocked_by_bull_structure", assessment["hard_blocks"])
        # Other gates may still block; this knife only asserts the bull gate is quiet.
        self.assertTrue(assessment["directional_catalyst"], assessment)

    def test_long_side_unaffected(self):
        """No long-side mirror: Dow short / lean bear must not invent a long veto here."""
        k = _break_hl_from_uptrend()
        dow = build_dow_structure_context(k)
        evidence = _evidence("long", dow)
        aux = _aux_with_core("bear")
        trial = build_trial_context(
            k,
            {"text": "4H 震荡", "h4_direction": "neutral"},
            _liq(),
            _msb_empty(),
            {},
            aux,
            evidence_bundle=evidence,
            range_lock={"active": False},
        )
        zone = (106.0, 112.0)
        assessment = assess_trial_candidate(
            "long",
            "LOWER_KEY_ZONE_RECLAIM",
            zone,
            zone[0],
            k[-1],
            float(k[-3]["close"]),
            "ifvg_zone",
            "reclaimed_above",
            trial,
            current_bar=len(k) - 1,
        )
        self.assertNotIn("formal_short_blocked_by_bull_structure", assessment["hard_blocks"])
        # Also ensure we did not invent a formal_long_blocked_* tag.
        self.assertFalse(any("formal_long_blocked" in b for b in assessment["hard_blocks"]))


if __name__ == "__main__":
    unittest.main()
