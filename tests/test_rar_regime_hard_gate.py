"""RAR regime hard gate (L 2026-10-28): reverse RAR blocks formal trial."""
from __future__ import annotations

import unittest

from engine.aux_filters import build_aux_filters_proxy
from engine.trial_decision import (
    assess_trial_candidate,
    build_trial_context,
    _rar_regime_blocks,
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


def _assess(side: str, aux: dict, *, zone_source: str = "ifvg_zone", h4_neutral: bool = False):
    htf = {
        "h4_direction": "neutral" if h4_neutral else ("bull" if side == "long" else "bear"),
        "text": "4H 震荡" if h4_neutral else ("4H 偏多" if side == "long" else "4H 偏空"),
        "bias": "neutral" if h4_neutral else side,
    }
    matrix = {}
    trial = build_trial_context(
        _flat_bars(),
        htf,
        {},
        {"fibonacci": {}},
        matrix,
        aux,
        evidence_bundle={
            "ifvg": {
                "nearest_active": {
                    "top": 10020.0,
                    "bottom": 9990.0,
                    "direction": 1 if side == "short" else -1,
                    "inverted": True,
                    "invalidated": False,
                }
            }
        },
        range_lock={"active": False},
    )
    # Force a high score path so only the RAR hard gate decides.
    trial["scores"] = {"long": 12.0, "short": 12.0}
    trial["scores"]["long" if side == "long" else "short"] = 12.0
    trial["scores"]["short" if side == "long" else "long"] = 1.0
    trial["evidence"][side] = [
        "rar_turn_up:+1.00" if side == "long" else "rar_turn_down:+1.00",
        "imbalance_inverted_support:+1.25" if side == "long" else "imbalance_inverted_resistance:+1.25",
    ]
    trial["chart_framework_active"] = True
    trial["evidence_bundle_keys"] = ["ifvg"]
    # Ensure rar_aux reflects the aux under test (build already did; overwrite for clarity).
    trial["rar_aux"] = {
        "rar_slope": float(aux.get("rar_slope", 0.0)),
        "rar_above_trigger": bool(aux.get("rar_above_trigger")),
        "rar_spread": float(aux.get("rar_spread", 0.0)),
        "rar_trend_strong": bool(aux.get("rar_trend_strong")),
        "rar_spread_rising": bool(aux.get("rar_spread_rising")),
        "rar_vs_trigger_weakening": bool(aux.get("rar_vs_trigger_weakening")),
        "rar_vs_trigger_strengthening": bool(aux.get("rar_vs_trigger_strengthening")),
        "momentum_desc": str(aux.get("momentum_desc", "")),
    }
    if h4_neutral:
        trial["h4_neutral"] = True

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


class RarRegimeHelperTests(unittest.TestCase):
    def test_counterexample_short_positive_slope_narrow_spread_blocks(self):
        """2026-10-28 14:00 试空反例：窄带~5、斜率+0.81、above_trigger → hard_block。"""
        aux = _base_aux(
            rar_slope=0.81,
            rar_above_trigger=True,
            rar_spread=5.0,
            rar_trend_strong=False,
            rar_spread_rising=False,
            momentum_desc="短线动能偏强",
        )
        self.assertTrue(_rar_regime_blocks(aux, "short"))
        result = _assess("short", aux)
        self.assertIn("rar_regime_blocks_short", result["hard_blocks"])
        self.assertFalse(result["allow_formal"])

    def test_symmetric_long_negative_slope_below_trigger_blocks(self):
        aux = _base_aux(
            rar_slope=-0.81,
            rar_above_trigger=False,
            rar_spread=5.0,
            rar_trend_strong=False,
            rar_spread_rising=False,
            momentum_desc="短线动能偏弱",
        )
        self.assertTrue(_rar_regime_blocks(aux, "long"))
        result = _assess("long", aux)
        self.assertIn("rar_regime_blocks_long", result["hard_blocks"])
        self.assertFalse(result["allow_formal"])

    def test_short_turn_down_allows(self):
        aux = _base_aux(
            rar_slope=-0.40,
            rar_above_trigger=False,
            rar_spread=12.0,
            rar_trend_strong=True,
            rar_spread_rising=True,
            rar_vs_trigger_weakening=True,
            momentum_desc="短线动能转弱",
        )
        self.assertFalse(_rar_regime_blocks(aux, "short"))
        result = _assess("short", aux)
        self.assertNotIn("rar_regime_blocks_short", result["hard_blocks"])

    def test_long_turn_up_allows(self):
        aux = _base_aux(
            rar_slope=0.40,
            rar_above_trigger=True,
            rar_spread=12.0,
            rar_trend_strong=True,
            rar_spread_rising=True,
            rar_vs_trigger_strengthening=True,
            momentum_desc="短线动能偏强",
        )
        self.assertFalse(_rar_regime_blocks(aux, "long"))
        result = _assess("long", aux)
        self.assertNotIn("rar_regime_blocks_long", result["hard_blocks"])

    def test_ifvg_poi_cannot_override_reverse_rar(self):
        """IFVG 定边+反应分不能压过反向 RAR 硬闸。"""
        aux = _base_aux(
            rar_slope=0.81,
            rar_above_trigger=True,
            rar_spread=5.0,
            rar_trend_strong=False,
            momentum_desc="短线动能偏强",
        )
        result = _assess("short", aux, zone_source="ifvg_zone")
        self.assertGreaterEqual(result["reaction_score"], 3.5)  # confirmed reaction present
        self.assertIn("rar_regime_blocks_short", result["hard_blocks"])
        self.assertFalse(result["allow_formal"])

    def test_bearish_bandwidth_expansion_permits_short_without_steep_turn(self):
        aux = _base_aux(
            rar_slope=-0.10,  # not yet turn_down
            rar_above_trigger=False,
            rar_spread=15.0,
            rar_trend_strong=True,
            rar_spread_rising=True,
            rar_vs_trigger_weakening=True,
            momentum_desc="短线动能一般",
        )
        self.assertFalse(_rar_regime_blocks(aux, "short"))

    def test_neutral_htf_raises_formal_min(self):
        aux = _base_aux(
            rar_slope=0.40,
            rar_above_trigger=True,
            rar_spread=12.0,
            rar_trend_strong=True,
            rar_spread_rising=True,
            rar_vs_trigger_strengthening=True,
            momentum_desc="短线动能偏强",
        )
        result = _assess("long", aux, h4_neutral=True)
        self.assertGreaterEqual(result["minimum_score"], 8.5)


class AuxFiltersRarRegimeFieldsTests(unittest.TestCase):
    def test_aux_exposes_spread_and_trend_strong(self):
        bars = []
        for i in range(40):
            # mild uptrend so RAR components exist
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
        self.assertIn("rar_spread", aux)
        self.assertIn("rar_trend_strong", aux)
        self.assertIn("rar_spread_rising", aux)
        self.assertIn("rar_vs_trigger_weakening", aux)
        self.assertIn("rar_vs_trigger_strengthening", aux)
        self.assertIn("rar_above_trigger", aux)
        self.assertIn("rar_slope", aux)


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
        self.assertIn("rar_spread", ctx["rar_aux"])
        self.assertTrue(ctx["rar_aux"]["rar_trend_strong"])


if __name__ == "__main__":
    unittest.main()
