"""Formal liquidity sweep source: weight, evidence gates, and 15m/1H map split."""
from __future__ import annotations

import unittest

from engine.sweep_hunter import attach_path_context, build_sweep_context, merge_sweep_into_liquidity
from engine.trial_decision import assess_trial_candidate, build_trial_context


_TRADE_DRAWING_KEYS = {
    "take_profit",
    "stop_loss",
    "tp",
    "sl",
    "tp_price",
    "sl_price",
    "trade_stop",
    "trade_target",
    "trade_entry",
    "trade_drawings",
    "signal_expiry",
    "risk_reward",
    "rr",
}


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


def _add_flat(bars: list[dict], n: int, price: float, *, vol: float = 120.0, bullish: bool = True, spread: float = 8.0) -> None:
    start = len(bars)
    for k in range(n):
        i = start + k
        if bullish:
            o, c = price - spread, price + spread
        else:
            o, c = price + spread, price - spread
        bars.append(
            _bar(o, max(o, c) + 6, min(o, c) - 6, c, vol=vol, ts=i * 3_600_000)
        )


def make_lower_sweep_series(
    *,
    charge: bool = True,
    only_one_level: bool = False,
    no_reclaim: bool = False,
    extra_after: int = 0,
) -> list[dict]:
    """Two sell-side lows at 9800 / 9900, optional wick-through and reclaim."""
    bars: list[dict] = []
    _add_flat(bars, 160, 10000, vol=100, bullish=True)
    i = len(bars)
    bars.append(_bar(10000, 10010, 9800, 9850, vol=200, ts=i * 3_600_000))
    _add_flat(bars, 6, 9920, vol=150, bullish=charge)
    _add_flat(bars, 16, 10020, vol=180, bullish=charge)
    if not only_one_level:
        i = len(bars)
        bars.append(_bar(10020, 10030, 9900, 9940, vol=200, ts=i * 3_600_000))
        _add_flat(bars, 6, 9970, vol=150, bullish=charge)
        _add_flat(bars, 16, 10040, vol=220, bullish=charge)
    else:
        _add_flat(bars, 22, 10040, vol=220, bullish=charge)
    i = len(bars)
    if no_reclaim:
        bars.append(_bar(10040, 10050, 9750, 9850, vol=400, ts=i * 3_600_000))
        _add_flat(bars, 3, 9840, vol=150, bullish=False, spread=8)
    else:
        bars.append(_bar(10040, 10050, 9750, 10010, vol=400, ts=i * 3_600_000))
    if extra_after:
        _add_flat(bars, extra_after, 10020, vol=120, bullish=True)
    return bars


def _neutral_trial_inputs(bars: list[dict]):
    htf = {"bias": "neutral", "text": "neutral", "relation": "neutral", "h4_direction": "neutral"}
    matrix = {"rar_slope": 0.0, "inertia_slope": 0.0, "momentum_text": "", "temperature": ""}
    aux = {"price_impulse": 0.0, "rar_slope": 0.0, "rar_above_trigger": True}
    return htf, matrix, aux


def _assert_no_trade_drawings(payload: dict) -> None:
    keys = {str(k).lower() for k in payload.keys()}
    overlap = keys & _TRADE_DRAWING_KEYS
    assert not overlap, f"trade-drawing keys leaked into payload: {overlap}"


class SweepDetectionTests(unittest.TestCase):
    def test_two_layers_strength_and_reclaim_records_evidence(self):
        ctx = build_sweep_context(make_lower_sweep_series(), timeframe="1h")
        self.assertTrue(ctx["swept"])
        self.assertTrue(ctx["recent_sweep_valid"])
        self.assertEqual(ctx["side"], "sell_side")
        self.assertEqual(ctx["reclaim_or_reject"], "reclaim")
        self.assertEqual(ctx["level"], 9900.0)
        self.assertGreaterEqual(ctx["layers_swept"], 2)
        self.assertGreaterEqual(ctx["strength"], 0.33)
        self.assertEqual(ctx["timeframe"], "1h")
        _assert_no_trade_drawings(ctx)

    def test_single_visible_band_is_not_evidence(self):
        ctx = build_sweep_context(make_lower_sweep_series(only_one_level=True), timeframe="1h")
        self.assertFalse(ctx["swept"])
        self.assertFalse(ctx["recent_sweep_valid"])
        self.assertEqual(ctx["reason"], "no_recent_sweep")

    def test_strength_below_threshold_is_not_evidence(self):
        ctx = build_sweep_context(make_lower_sweep_series(charge=False), timeframe="1h")
        self.assertFalse(ctx["swept"])
        self.assertFalse(ctx["recent_sweep_valid"])

    def test_no_reclaim_within_two_bars_is_not_evidence(self):
        ctx = build_sweep_context(make_lower_sweep_series(no_reclaim=True), timeframe="1h")
        self.assertFalse(ctx["swept"])
        self.assertFalse(ctx["recent_sweep_valid"])
        ended = {round(item["price"], 2) for item in ctx.get("ended_levels") or []}
        self.assertIn(9800.0, ended)
        self.assertIn(9900.0, ended)


class SweepMapPathSplitTests(unittest.TestCase):
    def test_path_cannot_revive_ended_map_level(self):
        map_ctx = build_sweep_context(make_lower_sweep_series(no_reclaim=True), timeframe="1h")
        self.assertFalse(map_ctx["swept"])
        self.assertFalse(map_ctx["recent_sweep_valid"])
        ended_prices = {round(item["price"], 2) for item in map_ctx.get("ended_levels") or []}
        self.assertIn(9800.0, ended_prices)

        # Pretend a 15m path printed a bullish reclaim at the dead 1H line,
        # and even try to push that price back onto the 1H active map.
        map_ctx["active_levels"] = list(map_ctx.get("active_levels") or []) + [
            {"price": 9800.0, "side": "sell_side", "strength": 0.9}
        ]
        path_ctx = {
            "timeframe": "15m",
            "side": "sell_side",
            "level": 9800.0,
            "swept": True,
            "reclaim_or_reject": "reclaim",
            "recent_sweep_valid": True,
            "bars_since": 0,
            "layers_swept": 2,
            "strength": 0.9,
            "reason": "multi_level_sweep_reclaim",
            "active_levels": [{"price": 9800.0, "side": "sell_side", "strength": 0.9}],
        }
        out = attach_path_context(map_ctx, path_ctx)
        self.assertFalse(out["swept"])
        self.assertFalse(out["recent_sweep_valid"])
        self.assertEqual(out["timeframe"], "1h")
        self.assertIsNotNone(out.get("path"))
        self.assertEqual(out["path"]["timeframe"], "15m")
        self.assertTrue(out["path"]["recent_sweep_valid"])
        active_prices = {round(float(lv["price"]), 2) for lv in out.get("active_levels") or []}
        self.assertNotIn(9800.0, active_prices)
        _assert_no_trade_drawings(out)
        _assert_no_trade_drawings(out["path"])

    def test_independent_timeframe_contexts(self):
        bars_1h = make_lower_sweep_series()
        ctx_1h = build_sweep_context(bars_1h, timeframe="1h")
        ctx_15m = build_sweep_context(bars_1h, timeframe="15m")
        self.assertEqual(ctx_1h["timeframe"], "1h")
        self.assertEqual(ctx_15m["timeframe"], "15m")
        # Same bars, independent memory — attaching must not rewrite 15m onto the map flags.
        attached = attach_path_context(ctx_1h, ctx_15m)
        self.assertEqual(attached["swept"], ctx_1h["swept"])
        self.assertEqual(attached["recent_sweep_valid"], ctx_1h["recent_sweep_valid"])
        self.assertEqual(attached["path"]["timeframe"], "15m")


class SweepTrialWeightAndFormalTests(unittest.TestCase):
    def test_weight_unchanged_at_two(self):
        bars = make_lower_sweep_series()
        sweep = build_sweep_context(bars, timeframe="1h")
        self.assertTrue(sweep["recent_sweep_valid"])
        htf, matrix, aux = _neutral_trial_inputs(bars)
        trial = build_trial_context(
            bars,
            htf,
            merge_sweep_into_liquidity({}, sweep),
            {},
            matrix,
            aux,
            evidence_bundle={"sweep": sweep},
            range_lock={"active": False},
        )
        long_blob = " ".join(trial["evidence"]["long"])
        self.assertIn("sweep_sell_side_reclaim:+2.00", long_blob)
        self.assertNotIn("sweep_sell_side_reclaim:+3.50", long_blob)

    def test_sweep_alone_cannot_raise_formal(self):
        bars = make_lower_sweep_series()
        sweep = build_sweep_context(bars, timeframe="1h")
        self.assertTrue(sweep["recent_sweep_valid"])
        htf, matrix, aux = _neutral_trial_inputs(bars)
        trial = build_trial_context(
            bars,
            htf,
            merge_sweep_into_liquidity({}, sweep),
            {},
            matrix,
            aux,
            evidence_bundle={"sweep": sweep, "auto_range": {"state": "none", "approx": True}},
            range_lock={"active": False},
        )
        long_blob = " ".join(trial["evidence"]["long"])
        self.assertIn("sweep_sell_side_reclaim:+2.00", long_blob)
        self.assertNotIn("rar_turn_up", long_blob)
        self.assertNotIn("imbalance_inverted_support", long_blob)
        # Inflate the raw score so the only gate under test is the catalyst block.
        trial["scores"]["long"] = 10.0
        assessment = assess_trial_candidate(
            "long",
            "LOWER_KEY_ZONE_RECLAIM",
            (9790.0, 9810.0),
            9780.0,
            bars[-1],
            float(bars[-3]["close"]),
            "key_level",
            "reclaimed_above",
            trial,
            current_bar=len(bars) - 1,
        )
        self.assertFalse(assessment["directional_catalyst"], msg=assessment)
        self.assertIn("formal_without_directional_catalyst", assessment["hard_blocks"])
        self.assertFalse(assessment["allow_formal"], msg=assessment)
        _assert_no_trade_drawings(assessment)

    def test_merge_and_context_have_no_trade_drawings(self):
        sweep = build_sweep_context(make_lower_sweep_series(), timeframe="1h")
        merged = merge_sweep_into_liquidity({"sweep_type": "none"}, sweep)
        _assert_no_trade_drawings(sweep)
        _assert_no_trade_drawings(merged)
        hunter = merged["sweep_hunter"]
        _assert_no_trade_drawings(hunter)
        self.assertEqual(merged.get("sweep_source"), "sweep_hunter")
        self.assertNotIn("take_profit_zone", hunter)
        self.assertNotIn("stop_price", hunter)


if __name__ == "__main__":
    unittest.main()
