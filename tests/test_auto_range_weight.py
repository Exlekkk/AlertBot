"""Auto Range low-weight contract (L 2026-10-25)."""
from __future__ import annotations

import unittest

from engine.trial_decision import assess_trial_candidate, build_trial_context


def _bar(o, h, l, c, atr=20.0, vol=100.0, ts=0):
    return {
        "open": float(o),
        "high": float(h),
        "low": float(l),
        "close": float(c),
        "atr": float(atr),
        "volume": float(vol),
        "open_time": ts,
    }


def _flat_bars(n=50, base=10000.0):
    return [_bar(base, base + 10, base - 10, base, ts=i * 3600000) for i in range(n)]


class AutoRangeLowWeightTests(unittest.TestCase):
    def _ctx(self, auto_range, *, range_lock=None):
        htf = {"bias": "neutral", "text": "neutral", "relation": "neutral"}
        matrix = {"rar_slope": 0.0, "inertia_slope": 0.0, "momentum_text": "", "temperature": ""}
        aux = {"price_impulse": 0.0}
        rl = range_lock if range_lock is not None else {"active": False}
        return build_trial_context(
            _flat_bars(),
            htf,
            {},
            {},
            matrix,
            aux,
            evidence_bundle={"auto_range": auto_range},
            range_lock=rl,
        )

    def test_pending_break_never_scores_direction(self):
        ctx = self._ctx({"pending_break": "up", "last_event": None})
        blob = " ".join(ctx["evidence"]["long"] + ctx["evidence"]["short"])
        self.assertNotIn("range_reclaim", blob)
        self.assertNotIn("range_breakout", blob)
        self.assertNotIn("range_break_pending", blob)

    def test_deviation_score_is_demoted_to_half(self):
        ctx = self._ctx({"last_event": "deviation_down", "pending_break": None})
        long_reasons = ctx["evidence"]["long"]
        hits = [r for r in long_reasons if r.startswith("range_reclaim_after_break_down:")]
        self.assertEqual(len(hits), 1)
        self.assertIn("+0.50", hits[0])
        self.assertNotIn("+1.50", hits[0])

    def test_confirmed_breakout_is_annotation_only_weight(self):
        ctx = self._ctx({"last_event": "breakout_up", "pending_break": None})
        long_reasons = ctx["evidence"]["long"]
        hits = [r for r in long_reasons if r.startswith("range_breakout_up_annotation:")]
        self.assertEqual(len(hits), 1)
        self.assertIn("+0.50", hits[0])

    def test_breakout_does_not_sole_drive_directional_catalyst(self):
        """accepted_breakout alone must not unlock formal catalyst (L: no high-weight drive)."""
        htf = {"bias": "neutral", "text": "neutral", "relation": "neutral"}
        matrix = {"rar_slope": 0.0, "inertia_slope": 0.0, "momentum_text": "", "temperature": ""}
        aux = {"price_impulse": 0.0}
        trial = build_trial_context(
            _flat_bars(),
            htf,
            {},
            {"fibonacci": {}},
            matrix,
            aux,
            evidence_bundle={
                "auto_range": {"last_event": "breakout_up", "pending_break": None},
            },
            range_lock={"active": True, "accepted_breakout": "up", "box_low": 9900.0, "box_high": 10100.0},
        )
        trial["chart_framework_active"] = True
        trial["scores"] = {"long": 10.0, "short": 1.0}
        # Keep only Auto Range annotation evidence — no sweep/RAR/IFVG pairing.
        trial["evidence"]["long"] = [
            r for r in trial["evidence"]["long"] if "range_breakout" in r or "range_reclaim" in r
        ]
        trial["evidence_bundle_keys"] = ["auto_range"]
        # Non-POI zone_source: Auto Range annotation must not unlock catalyst alone
        # (pairing with OTE/IFVG/RAR as weak catalyst remains allowed elsewhere).
        result = assess_trial_candidate(
            "long",
            "LOWER_KEY_ZONE_RECLAIM",
            (9990.0, 10010.0),
            9980.0,
            {"open": 10000.0, "high": 10020.0, "low": 9990.0, "close": 10005.0, "atr": 20.0},
            10000.0,
            "range_box",
            "reclaimed_above",
            trial,
            current_bar=20,
        )
        self.assertFalse(result["directional_catalyst"])
        self.assertIn("formal_without_directional_catalyst", result["hard_blocks"])

    def test_deviation_with_pending_does_not_score(self):
        # Safety: if both set, prefer pending silence over scoring stale event.
        ctx = self._ctx({"last_event": "deviation_down", "pending_break": "up"})
        blob = " ".join(ctx["evidence"]["long"])
        self.assertNotIn("range_reclaim_after_break_down", blob)


if __name__ == "__main__":
    unittest.main()
