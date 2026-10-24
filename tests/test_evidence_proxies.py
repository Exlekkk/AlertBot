"""Smoke tests for sweep / delta-profile / imbalance-zone proxies (not stubs)."""
from __future__ import annotations

import unittest

from engine.delta_profile import build_delta_profile_context, merge_delta_into_vp
from engine.ifvg import build_ifvg_context
from engine.sweep_hunter import build_sweep_context, merge_sweep_into_liquidity


def _bar(o, h, l, c, vol=100.0, ts=0):
    return {
        "open": float(o),
        "high": float(h),
        "low": float(l),
        "close": float(c),
        "volume": float(vol),
        "open_time": ts,
        "atr": 50.0,
    }


def _series(n=120, base=10000.0):
    bars = []
    for i in range(n):
        # mild oscillation with occasional volume spikes
        wave = (i % 11 - 5) * 15.0
        o = base + wave
        c = base + wave + (8 if i % 2 == 0 else -8)
        h = max(o, c) + 20
        l = min(o, c) - 20
        vol = 200.0 if i % 17 == 0 else 80.0
        # clear pivot + sweep: pierce prior low then reclaim
        if i == n - 5:
            l = base - 180
            c = base - 20
            o = base - 40
            h = base
            vol = 400.0
        if i == n - 4:
            o = base - 30
            c = base + 10
            h = base + 30
            l = base - 50
            vol = 250.0
        bars.append(_bar(o, h, l, c, vol=vol, ts=i * 3_600_000))
    return bars


class SweepHunterTests(unittest.TestCase):
    def test_not_stub(self):
        ctx = build_sweep_context(_series())
        self.assertNotEqual(ctx.get("reason"), "stub_pending_algorithm")
        self.assertTrue(ctx.get("approx"))
        self.assertTrue(ctx.get("candle_proxy"))
        for key in ("side", "level", "swept", "reclaim_or_reject", "strength"):
            self.assertIn(key, ctx)

    def test_merge_into_liquidity(self):
        sweep = build_sweep_context(_series())
        liq = {"sweep_type": "none", "bars_since_sweep": 99}
        out = merge_sweep_into_liquidity(liq, sweep)
        self.assertIn("sweep_hunter", out)
        if sweep.get("swept") and sweep.get("recent_sweep_valid"):
            self.assertEqual(out.get("sweep_source"), "sweep_hunter_approx")


class DeltaProfileTests(unittest.TestCase):
    def test_contract_fields_not_stub(self):
        ctx = build_delta_profile_context(_series(200))
        self.assertNotEqual(ctx.get("reason"), "stub_pending_algorithm")
        self.assertEqual(ctx.get("label"), "candle_delta_proxy")
        self.assertTrue(ctx.get("approx"))
        for key in ("poc", "vah", "val", "value_area_pos", "node_bias"):
            self.assertIn(key, ctx)
        self.assertIsNotNone(ctx["poc"])
        self.assertLessEqual(ctx["val"], ctx["poc"])
        self.assertLessEqual(ctx["poc"], ctx["vah"])
        self.assertIn(ctx["value_area_pos"], {"above", "inside", "below"})
        self.assertIn(ctx["node_bias"], {"bull", "bear", "neutral"})

    def test_merge_into_vp(self):
        delta = build_delta_profile_context(_series(200))
        out = merge_delta_into_vp({}, delta)
        self.assertEqual(out.get("poc"), delta.get("poc"))
        self.assertEqual(out.get("delta_label"), "candle_delta_proxy")


class IFVGTests(unittest.TestCase):
    def test_not_stub_and_contract_shape(self):
        # build a clear bullish gap then invert through it
        bars = []
        base = 10000.0
        for i in range(40):
            bars.append(_bar(base, base + 10, base - 10, base, vol=100, ts=i * 3600000))
        # bars 40..42 create an upside gap
        bars.append(_bar(10000, 10020, 9990, 10010, ts=40 * 3600000))   # i-2
        bars.append(_bar(10010, 10030, 10000, 10020, ts=41 * 3600000))  # mid
        bars.append(_bar(10100, 10140, 10090, 10120, ts=42 * 3600000))  # gap: low 10090 > high 10020
        # later bars invert through the gap
        for j in range(5):
            px = 10050 - j * 40
            bars.append(_bar(px + 10, px + 20, px - 30, px - 20, ts=(43 + j) * 3600000))

        ctx = build_ifvg_context(bars, timeframe="1h")
        self.assertNotEqual(ctx.get("reason"), "stub_pending_algorithm")
        self.assertTrue(ctx.get("approx"))
        self.assertIn("zones", ctx)
        self.assertIn("nearest_active", ctx)
        # at least one zone should be detected
        self.assertTrue(len(ctx["zones"]) >= 1 or ctx["nearest_active"] is not None)
        if ctx["zones"]:
            z = ctx["zones"][0]
            for key in ("top", "bottom", "direction", "inverted", "mitigated", "start_bar"):
                self.assertIn(key, z)



class IFVGInvertedActiveTests(unittest.TestCase):
    def test_inverted_zone_stays_nearest_after_touch(self):
        """Touch after invert must not drop the zone from nearest_active."""
        bars = []
        base = 10000.0
        for i in range(40):
            bars.append(_bar(base, base + 10, base - 10, base, vol=100, ts=i * 3600000))
        # bullish gap
        bars.append(_bar(10000, 10020, 9990, 10010, ts=40 * 3600000))
        bars.append(_bar(10010, 10030, 10000, 10020, ts=41 * 3600000))
        bars.append(_bar(10100, 10140, 10090, 10120, ts=42 * 3600000))  # gap
        # invert through underside
        bars.append(_bar(10050, 10060, 10000, 10010, ts=43 * 3600000))
        bars.append(_bar(10010, 10020, 9950, 9980, ts=44 * 3600000))
        # touch the inverted zone (reaction) without cancelling
        bars.append(_bar(10040, 10100, 10030, 10070, ts=45 * 3600000))

        ctx = build_ifvg_context(bars, timeframe="1h")
        nearest = ctx.get("nearest_active")
        self.assertIsNotNone(nearest)
        self.assertTrue(nearest.get("inverted"))
        self.assertFalse(nearest.get("invalidated", False))
        # classic mitigated may be true/false; must not exclude inverted nearest
        inverted = [z for z in ctx["zones"] if z.get("inverted") and not z.get("invalidated")]
        self.assertTrue(inverted)



class TrialEvidenceIfvgTests(unittest.TestCase):
    def test_inverted_weight_reads_evidence_ifvg_not_only_range_lock(self):
        """Trial must score inverted imbalance from evidence.ifvg alone."""
        from engine.trial_decision import build_trial_context

        bars = []
        base = 10000.0
        for i in range(50):
            bars.append(_bar(base, base + 10, base - 10, base, vol=100, ts=i * 3600000))
        # minimal stubs for required contexts
        empty = {}
        htf = {"bias": "neutral", "text": "neutral", "relation": "neutral"}
        matrix = {"rar_slope": 0.0, "inertia_slope": 0.0, "momentum_text": "", "temperature": ""}
        aux = {"price_impulse": 0.0}
        ifvg = {
            "nearest_active": {
                "inverted": True,
                "invalidated": False,
                "direction": 1,
                "top": 10120.0,
                "bottom": 10090.0,
            },
            "zones": [],
            "approx": True,
        }
        # range_lock has NO imbalance side-channel — only evidence_bundle.ifvg
        ctx = build_trial_context(
            bars,
            htf,
            empty,
            empty,
            matrix,
            aux,
            vp={},
            range_lock={"active": False},
            ict={},
            evidence_bundle={"ifvg": ifvg},
        )
        reasons = " ".join(ctx.get("evidence", {}).get("short", []))
        self.assertIn("imbalance_inverted_resistance", reasons)


if __name__ == "__main__":
    unittest.main()



class TrialEvidenceBundlePreferenceTests(unittest.TestCase):
    def _base(self):
        bars = []
        base = 10000.0
        for i in range(50):
            bars.append(_bar(base, base + 10, base - 10, base, vol=100, ts=i * 3600000))
        htf = {"bias": "neutral", "text": "neutral", "relation": "neutral"}
        matrix = {"rar_slope": 0.0, "inertia_slope": 0.0, "momentum_text": "", "temperature": ""}
        aux = {"price_impulse": 0.0}
        return bars, htf, matrix, aux

    def test_prefers_evidence_bundle_over_side_channels(self):
        """auto_range / sweep / delta / ifvg / core_levels read from evidence_bundle first."""
        from engine.trial_decision import build_trial_context

        bars, htf, matrix, aux = self._base()
        evidence_bundle = {
            "auto_range": {"last_event": "deviation_down", "pending_break": None},
            "sweep": {
                "swept": True,
                "recent_sweep_valid": True,
                "side": "sell_side",
                "reclaim_or_reject": "reclaim",
            },
            "delta_profile": {"node_bias": "bull", "value_area_pos": "inside", "approx": True},
            "ifvg": {
                "nearest_active": {
                    "inverted": True,
                    "invalidated": False,
                    "direction": -1,
                    "top": 10020.0,
                    "bottom": 9990.0,
                },
                "zones": [],
                "approx": True,
            },
            "core_levels_filter": {
                "allowed": True,
                "filter_only": True,
                "midline_event": "reclaim_above_50",
                "lean": "bull",
                "squeeze": False,
            },
        }
        # Conflicting / empty side-channels must not win over evidence_bundle.
        ctx = build_trial_context(
            bars,
            htf,
            {"sweep_hunter": {"swept": False}},
            {},
            matrix,
            aux,
            vp={"delta_profile": {"node_bias": "bear", "value_area_pos": "below"}},
            range_lock={"active": False, "auto_range": {"last_event": "deviation_up"}},
            ict={},
            evidence_bundle=evidence_bundle,
        )
        long_reasons = " ".join(ctx.get("evidence", {}).get("long", []))
        self.assertIn("range_reclaim_after_break_down", long_reasons)
        self.assertIn("sweep_sell_side_reclaim", long_reasons)
        self.assertIn("profile_node_bull", long_reasons)
        self.assertIn("imbalance_inverted_support", long_reasons)
        self.assertIn("core_levels_reclaim_50", long_reasons)
        # Confluence from structure tags (range/sweep/profile/ifvg), not core_levels.
        self.assertIn("evidence_confluence", long_reasons)
        self.assertIn("auto_range", ctx.get("evidence_bundle_keys", []))
        self.assertIn("sweep", ctx.get("evidence_bundle_keys", []))
        self.assertIn("ifvg", ctx.get("evidence_bundle_keys", []))

    def test_core_levels_does_not_count_toward_evidence_confluence(self):
        """Soft core_levels filter + one structure tag must not trigger confluence."""
        from engine.trial_decision import build_trial_context

        bars, htf, matrix, aux = self._base()
        evidence_bundle = {
            "sweep": {
                "swept": True,
                "recent_sweep_valid": True,
                "side": "sell_side",
                "reclaim_or_reject": "reclaim",
            },
            "core_levels_filter": {
                "allowed": True,
                "filter_only": True,
                "midline_event": "reclaim_above_50",
                "lean": "bull",
                "squeeze": False,
            },
        }
        ctx = build_trial_context(
            bars,
            htf,
            {},
            {},
            matrix,
            aux,
            vp={},
            range_lock={"active": False},
            ict={},
            evidence_bundle=evidence_bundle,
        )
        long_reasons = " ".join(ctx.get("evidence", {}).get("long", []))
        self.assertIn("sweep_sell_side_reclaim", long_reasons)
        self.assertIn("core_levels_reclaim_50", long_reasons)
        self.assertNotIn("evidence_confluence", long_reasons)

class CoreLevelsFilterTests(unittest.TestCase):
    def test_1h_filter_only_never_alerts(self):
        from engine.core_levels_filter import build_core_levels_filter

        bars = [_bar(10000 + (i % 7 - 3) * 20, 10040, 9960, 10000 + (i % 5 - 2) * 15, ts=i * 3600000) for i in range(80)]
        ctx = build_core_levels_filter(bars, timeframe="1h")
        self.assertTrue(ctx["allowed"])
        self.assertTrue(ctx["filter_only"])
        self.assertFalse(ctx["should_alert"])
        self.assertIn(ctx["lean"], {"bull", "bear", "neutral"})
        self.assertIsNotNone(ctx["rsi"])

    def test_15m_not_allowed(self):
        from engine.core_levels_filter import build_core_levels_filter

        bars = [_bar(10000, 10010, 9990, 10000, ts=i * 900000) for i in range(40)]
        ctx = build_core_levels_filter(bars, timeframe="15m")
        self.assertFalse(ctx["allowed"])
        self.assertEqual(ctx["reason"], "timeframe_not_allowed")
