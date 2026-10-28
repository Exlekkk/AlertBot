"""RAR regime scoring / resonance (L 2026-10-28 修订): 高权计分互通，非 hard_block 一票否决。"""
from __future__ import annotations

import unittest

from engine.aux_filters import build_aux_filters_proxy
from engine.trial_decision import (
    assess_trial_candidate,
    build_trial_context,
    _rar_adverse_penalty,
    _rar_bandwidth_expansion,
)


def _bar(o, h, l, c, atr=20.0, vol=100.0, ts=0, **extra):
    row = {
        "open": float(o),
        "high": float(h),
        "low": float(l),
        "close": float(c),
        "atr": float(atr),
        "volume": float(vol),
        "open_time": ts,
    }
    row.update(extra)
    return row


def _flat_bars(n=50, base=10000.0):
    return [_bar(base, base + 10, base - 10, base, ts=i * 3600000) for i in range(n)]


def _base_aux(**overrides):
    aux = {
        "rar_slope": 0.0,
        "rar_above_trigger": False,
        "rar_spread": 5.0,
        "rar_trend_strong": False,
        "rar_spread_rising": False,
        "rar_vs_trigger_weakening": False,
        "rar_vs_trigger_strengthening": False,
        "momentum_desc": "短线动能一般",
        "price_impulse": 0.0,
    }
    aux.update(overrides)
    return aux


def _ctx(side: str, aux: dict, *, h4_neutral: bool = False, with_ifvg: bool = True):
    htf = {
        "h4_direction": "neutral" if h4_neutral else ("bull" if side == "long" else "bear"),
        "text": "4H 震荡" if h4_neutral else ("4H 偏多" if side == "long" else "4H 偏空"),
        "bias": "neutral" if h4_neutral else side,
    }
    evidence = {}
    if with_ifvg:
        evidence["ifvg"] = {
            "nearest_active": {
                "top": 10020.0,
                "bottom": 9990.0,
                "direction": 1 if side == "short" else -1,
                "inverted": True,
                "invalidated": False,
            }
        }
    return build_trial_context(
        _flat_bars(),
        htf,
        {},
        {"fibonacci": {}},
        {},
        aux,
        evidence_bundle=evidence,
        range_lock={"active": False},
    )


def _assess_from_ctx(side: str, trial: dict, *, zone_source: str = "ifvg_zone"):
    alert = "UPPER_KEY_ZONE_REJECTION" if side == "short" else "LOWER_KEY_ZONE_RECLAIM"
    interaction = "rejected_below" if side == "short" else "reclaimed_above"
    latest = {
        "open": 10010.0 if side == "short" else 9990.0,
        "high": 10020.0,
        "low": 9980.0,
        "close": 9995.0 if side == "short" else 10005.0,
        "atr": 20.0,
    }
    invalid = 10040.0 if side == "short" else 9980.0
    return assess_trial_candidate(
        side,
        alert,
        (9990.0, 10010.0),
        invalid,
        latest,
        10000.0,
        zone_source,
        interaction,
        trial,
        current_bar=20,
    )


class RarAdversePenaltyTests(unittest.TestCase):
    def test_counterexample_short_positive_slope_narrow_does_not_formal(self):
        """2026-10-28 14:00 试空反例：above_trigger + 斜率+0.81 + 窄带 → 大额扣分不达 formal，非 hard_block。"""
        aux = _base_aux(
            rar_slope=0.81,
            rar_above_trigger=True,
            rar_spread=5.0,
            rar_trend_strong=False,
            rar_spread_rising=False,
            momentum_desc="短线动能偏强",
        )
        self.assertLessEqual(_rar_adverse_penalty(aux, "short"), -4.0)
        trial = _ctx("short", aux)
        short_blob = " ".join(trial["evidence"]["short"])
        self.assertIn("rar_adverse_bull_regime", short_blob)
        result = _assess_from_ctx("short", trial)
        self.assertFalse(result["allow_formal"])
        self.assertNotIn("rar_regime_blocks_short", result["hard_blocks"])
        self.assertNotIn("rar_regime_blocks_long", result["hard_blocks"])
        self.assertLess(result["score"], result["minimum_score"])

    def test_symmetric_long_negative_slope_narrow_does_not_formal(self):
        aux = _base_aux(
            rar_slope=-0.81,
            rar_above_trigger=False,
            rar_spread=5.0,
            rar_trend_strong=False,
            rar_spread_rising=False,
            momentum_desc="短线动能偏弱",
        )
        self.assertLessEqual(_rar_adverse_penalty(aux, "long"), -4.0)
        trial = _ctx("long", aux)
        result = _assess_from_ctx("long", trial)
        self.assertFalse(result["allow_formal"])
        self.assertNotIn("rar_regime_blocks_long", result["hard_blocks"])
        self.assertLess(result["score"], result["minimum_score"])

    def test_ifvg_reaction_alone_cannot_rescue_counterexample_short(self):
        """反例场景即便有 IFVG 反应分，仍因反向 RAR 大额扣分不达 formal；无 rar_regime hard_block。"""
        aux = _base_aux(
            rar_slope=0.81,
            rar_above_trigger=True,
            rar_spread=5.0,
            rar_trend_strong=False,
            momentum_desc="短线动能偏强",
        )
        trial = _ctx("short", aux, with_ifvg=True)
        result = _assess_from_ctx("short", trial, zone_source="ifvg_zone")
        self.assertGreaterEqual(result["reaction_score"], 3.5)
        self.assertFalse(result["allow_formal"])
        self.assertNotIn("rar_regime_blocks_short", result["hard_blocks"])

    def test_ifvg_rar_aligned_resonance_bonus(self):
        """IFVG + 同向 RAR 互通共振加分（非互斥）。"""
        aux = _base_aux(
            rar_slope=-0.40,
            rar_above_trigger=False,
            rar_spread=12.0,
            rar_trend_strong=True,
            rar_spread_rising=True,
            rar_vs_trigger_weakening=True,
            momentum_desc="短线动能转弱",
        )
        trial = _ctx("short", aux, with_ifvg=True)
        blob = " ".join(trial["evidence"]["short"])
        self.assertIn("imbalance_inverted_resistance", blob)
        self.assertIn("rar_ifvg_short_resonance", blob)
        self.assertNotIn("rar_adverse_bull_regime", blob)
        result = _assess_from_ctx("short", trial)
        self.assertNotIn("rar_regime_blocks_short", result["hard_blocks"])

    def test_mild_reverse_rar_with_strong_ifvg_can_still_compete(self):
        """略反向 RAR（小正斜率）+ 强 IFVG：互通可争，不因 hard_block 否决。"""
        aux = _base_aux(
            rar_slope=0.15,  # not turn_up threshold
            rar_above_trigger=True,
            rar_spread=8.0,
            rar_trend_strong=True,  # not narrow
            rar_spread_rising=False,
            momentum_desc="短线动能一般",
        )
        # Adverse still applies (above + slope>0) but milder without steep/narrow extras
        penalty = _rar_adverse_penalty(aux, "short")
        self.assertEqual(penalty, -2.5)
        trial = _ctx("short", aux, with_ifvg=True)
        # Boost with structure-like sweep so score can fight the drag (互通)
        trial["scores"]["short"] += 4.0
        trial["evidence"]["short"].append("sweep_buy_side_reject:+2.00")
        trial["evidence"]["short"].append("evidence_confluence:+0.75")
        trial["scores"]["short"] += 2.75
        result = _assess_from_ctx("short", trial)
        self.assertNotIn("rar_regime_blocks_short", result["hard_blocks"])
        # May or may not formal depending on totals — only assert no hard veto
        self.assertIsInstance(result["allow_formal"], bool)

    def test_short_turn_down_no_adverse(self):
        aux = _base_aux(
            rar_slope=-0.40,
            rar_above_trigger=False,
            rar_spread=12.0,
            rar_trend_strong=True,
            rar_spread_rising=True,
            rar_vs_trigger_weakening=True,
            momentum_desc="短线动能转弱",
        )
        self.assertEqual(_rar_adverse_penalty(aux, "short"), 0.0)
        self.assertTrue(_rar_bandwidth_expansion(aux, "short"))

    def test_long_turn_up_no_adverse(self):
        aux = _base_aux(
            rar_slope=0.40,
            rar_above_trigger=True,
            rar_spread=12.0,
            rar_trend_strong=True,
            rar_spread_rising=True,
            rar_vs_trigger_strengthening=True,
            momentum_desc="短线动能偏强",
        )
        self.assertEqual(_rar_adverse_penalty(aux, "long"), 0.0)

    def test_neutral_htf_raises_formal_min_only(self):
        aux = _base_aux(
            rar_slope=0.40,
            rar_above_trigger=True,
            rar_spread=12.0,
            rar_trend_strong=True,
            rar_spread_rising=True,
            rar_vs_trigger_strengthening=True,
            momentum_desc="短线动能偏强",
        )
        trial = _ctx("long", aux, h4_neutral=True)
        result = _assess_from_ctx("long", trial)
        self.assertGreaterEqual(result["minimum_score"], 8.5)
        self.assertNotIn("neutral_htf_without_directional_catalyst", result["hard_blocks"])


class AuxFiltersRarRegimeFieldsTests(unittest.TestCase):
    def test_aux_exposes_spread_and_trend_strong(self):
        bars = []
        for i in range(40):
            c = 10000 + i * 5
            bars.append(
                _bar(
                    c - 2,
                    c + 5,
                    c - 5,
                    c,
                    ts=i * 3600000,
                    rar_value=55 + i * 0.1,
                    rar_trigger=50.0,
                    rar_spread=5 + i * 0.1,
                    rar_trend_strong=(5 + i * 0.1) >= 6.0,
                )
            )
        aux = build_aux_filters_proxy(bars, bars[-10:])
        for key in (
            "rar_spread",
            "rar_trend_strong",
            "rar_spread_rising",
            "rar_vs_trigger_weakening",
            "rar_vs_trigger_strengthening",
            "rar_above_trigger",
            "rar_slope",
        ):
            self.assertIn(key, aux)


class BandwidthEntersDecisionTests(unittest.TestCase):
    def test_bullish_bandwidth_scored_in_context(self):
        aux = _base_aux(
            rar_slope=0.1,
            rar_above_trigger=True,
            rar_trend_strong=True,
            rar_spread_rising=True,
            rar_vs_trigger_strengthening=True,
            rar_spread=14.0,
        )
        ctx = build_trial_context(
            _flat_bars(),
            {"h4_direction": "bull", "text": "4H 偏多"},
            {},
            {},
            {},
            aux,
            evidence_bundle={},
            range_lock={"active": False},
        )
        blob = " ".join(ctx["evidence"]["long"])
        self.assertIn("rar_bullish_bandwidth", blob)
        self.assertTrue(ctx["rar_aux"]["rar_trend_strong"])


if __name__ == "__main__":
    unittest.main()
