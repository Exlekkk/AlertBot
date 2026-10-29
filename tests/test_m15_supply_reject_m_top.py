"""15m 供给拒收 + 小 M 顶进正式试空（2026-10-29 ~04:00 / ~81759 反例）。

根因：多 IFVG 时 nearest-to-close 抢走上沿 wick 拒收；15m M 顶未进正式路径。
验收：该反例能出正式试空观察（至少不被「1H nearest 未触」单独否掉）；
#40 触达闸 / 禁 orphan range、#41 RAR 高权互通非 hard_blocks 仍绿。
"""
from __future__ import annotations

import unittest

from engine.key_zones import _select_zone, decide_key_zone_observation
from engine.structure import build_structure_15m_context, detect_small_m_top
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


def _klines_0400_reject():
    """Synthesize 1H path ending at Asia/Shanghai 2026-10-29 04:00 class bar.

    High ~81759 into upper inverted IFVG 81751–82061, close ~81291 inside a
    lower inverted IFVG — the nearest-to-close trap.
    """
    base_ts = 1_730_000_000_000
    klines = []
    px = 80500.0
    for i in range(40):
        o = px
        c = px + (20 if i % 2 == 0 else -10)
        klines.append(
            _bar(o, max(o, c) + 40, min(o, c) - 40, c, atr=480.0, open_time=base_ts + i * 3_600_000)
        )
        px = c
    # Prior bar climbing into the window.
    klines.append(
        _bar(80978.0, 81594.0, 80944.0, 81544.0, atr=480.0, open_time=base_ts + 40 * 3_600_000)
    )
    # 04:00 bar: wick to 81759, close 81291.7 (red rejection).
    klines.append(
        _bar(81544.6, 81759.0, 80945.0, 81291.7, atr=489.7, open_time=base_ts + 41 * 3_600_000)
    )
    return klines


def _evidence_dual_ifvg(*, with_m15: bool = True):
    upper = {
        "top": 82061.9,
        "bottom": 81751.7,
        "direction": 1,
        "inverted": True,
        "mitigated": False,
        "invalidated": False,
        "start_bar": 10,
    }
    lower = {
        "top": 81275.0,
        "bottom": 80895.3,
        "direction": -1,
        "inverted": True,
        "mitigated": False,
        "invalidated": False,
        "start_bar": 30,
    }
    # nearest-to-close is the LOWER zone (post-reject trap).
    evidence = {
        "auto_range": {"state": "none", "high": None, "low": None},
        "ifvg": {
            "nearest_active": lower,
            "zones": [upper, lower],
            "approx": True,
            "timeframe": "1h",
        },
        "sweep": {},
        "delta_profile": {},
    }
    if with_m15:
        evidence["structure_15m"] = {
            "approx": True,
            "timeframe": "15m",
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
            "reason": "m15_supply_reject_m_top",
        }
    return evidence


def _aux_0400():
    # Live replay: steep positive slope + above_trigger + wide band + weakening.
    return {
        "rar_slope": 6.36,
        "rar_above_trigger": True,
        "rar_spread": 16.8,
        "rar_trend_strong": True,
        "rar_spread_rising": False,
        "rar_vs_trigger_weakening": True,
        "rar_vs_trigger_strengthening": False,
        "momentum_desc": "短线动能修复",
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
        "prev_low": 80355.0,
        "prev_high": 81800.0,
        "sweep_type": "none",
        "reclaim_or_reject": "none",
        "sweep_level": None,
        "recent_sweep_valid": False,
    }


class MultiIfvgUpperRejectPreferenceTests(unittest.TestCase):
    def test_upper_wick_reject_beats_nearest_lower_inside(self):
        """04:00：nearest 是下沿 inside，但上沿 IFVG wick 拒收必须胜出。"""
        selected = _select_zone(
            _klines_0400_reject(),
            _liq(),
            _msb_empty(),
            evidence_bundle=_evidence_dual_ifvg(with_m15=False),
            range_lock={"active": False},
        )
        self.assertEqual(selected.get("source"), "ifvg_zone")
        self.assertEqual(selected.get("side"), "upper")
        self.assertEqual(selected.get("interaction"), "rejected_below")
        zl, zh = selected["zone"]
        self.assertAlmostEqual(zl, 81751.7, places=1)
        self.assertAlmostEqual(zh, 82061.9, places=1)

    def test_nearest_untouched_alone_still_does_not_force_poi(self):
        """#40：仅远处 nearest、本根未触 → 仍不选（不回退 orphan）。"""
        evidence = {
            "auto_range": {"state": "none", "high": None, "low": None},
            "ifvg": {
                "nearest_active": {
                    "top": 83000.0,
                    "bottom": 82800.0,
                    "direction": 1,
                    "inverted": True,
                    "invalidated": False,
                },
                "zones": [],
                "approx": True,
            },
        }
        selected = _select_zone(
            _klines_0400_reject(),
            _liq(),
            _msb_empty(),
            evidence_bundle=evidence,
            range_lock={"active": False},
        )
        self.assertEqual(selected, {})


class M15SupplyRejectMTopFormalTests(unittest.TestCase):
    def test_counterexample_0400_formal_short_not_blocked_by_nearest_miss(self):
        """2026-10-29 ~04:00 / ~81759：15m 供给拒收+小M顶 → 正式试空可达。"""
        klines = _klines_0400_reject()
        evidence = _evidence_dual_ifvg(with_m15=True)
        aux = _aux_0400()
        htf = {"text": "4H 震荡", "relation": "neutral", "h4_direction": "neutral", "bias": "neutral"}

        selected = _select_zone(klines, _liq(), _msb_empty(), evidence_bundle=evidence, range_lock={"active": False})
        self.assertEqual(selected.get("side"), "upper")
        self.assertEqual(selected.get("interaction"), "rejected_below")

        trial = build_trial_context(
            klines,
            htf,
            _liq(),
            _msb_empty(),
            {},
            aux,
            evidence_bundle=evidence,
            range_lock={"active": False},
        )
        short_blob = " ".join(trial["evidence"]["short"])
        self.assertIn("m15_supply_reject_m_top", short_blob)
        self.assertIn("imbalance_inverted_resistance", short_blob)
        # RAR still present (capped path or raw) — never a rar_regime hard block.
        self.assertTrue(
            "rar_adverse_bull_regime" in short_blob or "rar_adverse_bull_regime_capped" in short_blob
        )

        latest = klines[-1]
        assessment = assess_trial_candidate(
            "short",
            "UPPER_KEY_ZONE_REJECTION",
            tuple(selected["zone"]),
            float(selected["zone"][1]),
            latest,
            float(klines[-3]["close"]),
            "ifvg_zone",
            "rejected_below",
            trial,
            current_bar=len(klines) - 1,
        )
        self.assertNotIn("rar_regime_blocks_short", assessment["hard_blocks"])
        self.assertTrue(assessment["allow_formal"], msg=assessment)
        self.assertTrue(assessment["directional_catalyst"])

        decision = decide_key_zone_observation(
            "BTCUSDT",
            "1h",
            klines,
            htf,
            _liq(),
            _msb_empty(),
            {},
            aux,
            evidence_bundle=evidence,
            observation_state={"inside_zone": False, "reentry_count": 0},
            range_lock={"active": False},
        )
        self.assertEqual(decision.get("direction"), "short")
        self.assertEqual(decision.get("zone_source"), "ifvg_zone")
        self.assertEqual(decision.get("alert_type"), "UPPER_KEY_ZONE_REJECTION")
        self.assertTrue(decision.get("should_alert"))

    def test_without_m15_structure_rar_adverse_still_can_block(self):
        """无 15m M 顶时，仅靠 IFVG 上沿拒收不足以压过强反向 RAR（#41 互通边界）。"""
        klines = _klines_0400_reject()
        evidence = _evidence_dual_ifvg(with_m15=False)
        aux = _aux_0400()
        htf = {"text": "4H 震荡", "relation": "neutral", "h4_direction": "neutral"}
        trial = build_trial_context(
            klines, htf, _liq(), _msb_empty(), {}, aux, evidence_bundle=evidence, range_lock={"active": False}
        )
        selected = _select_zone(klines, _liq(), _msb_empty(), evidence_bundle=evidence, range_lock={"active": False})
        assessment = assess_trial_candidate(
            "short",
            "UPPER_KEY_ZONE_REJECTION",
            tuple(selected["zone"]),
            float(selected["zone"][1]),
            klines[-1],
            float(klines[-3]["close"]),
            "ifvg_zone",
            "rejected_below",
            trial,
            current_bar=len(klines) - 1,
        )
        self.assertFalse(assessment["allow_formal"])
        self.assertNotIn("rar_regime_blocks_short", assessment["hard_blocks"])


class SmallMTopDetectorTests(unittest.TestCase):
    def test_detect_small_m_top_with_supply_tap(self):
        bars = []
        ts = 1_730_100_000_000
        px = 81000.0
        for i in range(20):
            bars.append(_bar(px, px + 30, px - 30, px + 10, atr=80.0, open_time=ts + i * 900_000))
            px += 10
        # Left peak near supply, trough, right peak into supply then reject.
        bars.append(_bar(81200, 81590, 81150, 81400, atr=80.0, open_time=ts + 20 * 900_000))
        bars.append(_bar(81400, 81450, 81280, 81320, atr=80.0, open_time=ts + 21 * 900_000))
        bars.append(_bar(81320, 81759, 81240, 81246, atr=80.0, open_time=ts + 22 * 900_000))
        # Confirming bars after right peak.
        bars.append(_bar(81246, 81260, 81027, 81096, atr=80.0, open_time=ts + 23 * 900_000))
        bars.append(_bar(81096, 81215, 81024, 81065, atr=80.0, open_time=ts + 24 * 900_000))
        m = detect_small_m_top(bars, supply_zone=(81751.7, 82061.9), max_bars_ago=6)
        self.assertIsNotNone(m)
        self.assertTrue(m["active"])
        ctx = build_structure_15m_context(bars, supply_zones=[(81751.7, 82061.9)])
        self.assertTrue(ctx["supply_reject"])
        self.assertTrue(ctx["active"])


if __name__ == "__main__":
    unittest.main()
