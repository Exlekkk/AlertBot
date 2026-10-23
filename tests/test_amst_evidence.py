"""Sweep / 3D Delta / IFVG 契约冒烟（非 stub）。"""
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
        # 轻微上下波动 + 偶发放量刺破
        wave = (i % 11 - 5) * 15.0
        o = base + wave
        c = base + wave + (8 if i % 2 == 0 else -8)
        h = max(o, c) + 20
        l = min(o, c) - 20
        vol = 200.0 if i % 17 == 0 else 80.0
        # 制造清晰 pivot + sweep：每隔一段刺破前低后收回
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
        # 构造明确 bullish FVG 再下破倒置
        bars = []
        base = 10000.0
        for i in range(40):
            bars.append(_bar(base, base + 10, base - 10, base, vol=100, ts=i * 3600000))
        # i=40,41,42 造 gap up FVG
        bars.append(_bar(10000, 10020, 9990, 10010, ts=40 * 3600000))   # i-2
        bars.append(_bar(10010, 10030, 10000, 10020, ts=41 * 3600000))  # mid
        bars.append(_bar(10100, 10140, 10090, 10120, ts=42 * 3600000))  # gap: low 10090 > high 10020
        # 后续下破倒置
        for j in range(5):
            px = 10050 - j * 40
            bars.append(_bar(px + 10, px + 20, px - 30, px - 20, ts=(43 + j) * 3600000))

        ctx = build_ifvg_context(bars, timeframe="1h")
        self.assertNotEqual(ctx.get("reason"), "stub_pending_algorithm")
        self.assertTrue(ctx.get("approx"))
        self.assertIn("zones", ctx)
        self.assertIn("nearest_active", ctx)
        # 应至少检出一个 zone
        self.assertTrue(len(ctx["zones"]) >= 1 or ctx["nearest_active"] is not None)
        if ctx["zones"]:
            z = ctx["zones"][0]
            for key in ("top", "bottom", "direction", "inverted", "mitigated", "start_bar"):
                self.assertIn(key, z)


if __name__ == "__main__":
    unittest.main()
