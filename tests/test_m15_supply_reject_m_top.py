"""15m 供给拒收 + 小 M 顶 → 正式试空催化剂（#35 基线最小切片）。

范围：detect_small_m_top / build_structure_15m_context、evidence.structure_15m、
trial_decision 的 m15_supply_reject_m_top 正式空向催化剂。

不含：#36–#41、#42 key_zones 多 IFVG / 上沿 rejected_below 优先。
04:00/~81759 双 IFVG nearest 抢区是选区债，不在本切片；本测在**已选上沿区**
前提下验证小M顶能否单独撑起 formal short。
"""
from __future__ import annotations

import unittest

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
    """Synthesize 1H path ending at Asia/Shanghai 2026-10-29 04:00 class bar."""
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
    klines.append(
        _bar(80978.0, 81594.0, 80944.0, 81544.0, atr=480.0, open_time=base_ts + 40 * 3_600_000)
    )
    klines.append(
        _bar(81544.6, 81759.0, 80945.0, 81291.7, atr=489.7, open_time=base_ts + 41 * 3_600_000)
    )
    return klines


def _evidence_upper_ifvg(*, with_m15: bool = True):
    """Single upper inverted IFVG as nearest — no dual-IFVG select rewrite."""
    upper = {
        "top": 82061.9,
        "bottom": 81751.7,
        "direction": 1,
        "inverted": True,
        "mitigated": False,
        "invalidated": False,
        "start_bar": 10,
    }
    evidence = {
        "auto_range": {"state": "none", "high": None, "low": None},
        "ifvg": {
            "nearest_active": upper,
            "zones": [upper],
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
        "prev_low": 80355.0,
        "prev_high": 81800.0,
        "sweep_type": "none",
        "reclaim_or_reject": "none",
        "sweep_level": None,
        "recent_sweep_valid": False,
    }


class M15SupplyRejectMTopFormalTests(unittest.TestCase):
    def test_m15_enables_formal_short_when_upper_zone_selected(self):
        """已选上沿 IFVG 拒收时：小M顶催化剂可单独撑 formal short（#35 基线）。"""
        klines = _klines_0400_reject()
        evidence = _evidence_upper_ifvg(with_m15=True)
        aux = _aux_neutral()
        htf = {"text": "4H 震荡", "relation": "neutral", "h4_direction": "neutral", "bias": "neutral"}
        zone = (81751.7, 82061.9)

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

        assessment = assess_trial_candidate(
            "short",
            "UPPER_KEY_ZONE_REJECTION",
            zone,
            zone[1],
            klines[-1],
            float(klines[-3]["close"]),
            "ifvg_zone",
            "rejected_below",
            trial,
            current_bar=len(klines) - 1,
        )
        self.assertTrue(assessment["directional_catalyst"], msg=assessment)
        self.assertTrue(assessment["allow_formal"], msg=assessment)

    def test_without_m15_upper_reject_may_lack_catalyst_or_score(self):
        """无 15m M 顶时，同区拒收不保证 formal（对照：催化剂/分数路径依赖 m15）。"""
        klines = _klines_0400_reject()
        evidence = _evidence_upper_ifvg(with_m15=False)
        aux = _aux_neutral()
        htf = {"text": "4H 震荡", "relation": "neutral", "h4_direction": "neutral"}
        zone = (81751.7, 82061.9)
        trial = build_trial_context(
            klines, htf, _liq(), _msb_empty(), {}, aux, evidence_bundle=evidence, range_lock={"active": False}
        )
        short_blob = " ".join(trial["evidence"]["short"])
        self.assertNotIn("m15_supply_reject_m_top", short_blob)


class SmallMTopDetectorTests(unittest.TestCase):
    def test_detect_small_m_top_with_supply_tap(self):
        bars = []
        ts = 1_730_100_000_000
        px = 81000.0
        for i in range(20):
            bars.append(_bar(px, px + 30, px - 30, px + 10, atr=80.0, open_time=ts + i * 900_000))
            px += 10
        bars.append(_bar(81200, 81590, 81150, 81400, atr=80.0, open_time=ts + 20 * 900_000))
        bars.append(_bar(81400, 81450, 81280, 81320, atr=80.0, open_time=ts + 21 * 900_000))
        bars.append(_bar(81320, 81759, 81240, 81246, atr=80.0, open_time=ts + 22 * 900_000))
        bars.append(_bar(81246, 81260, 81027, 81096, atr=80.0, open_time=ts + 23 * 900_000))
        bars.append(_bar(81096, 81215, 81024, 81065, atr=80.0, open_time=ts + 24 * 900_000))
        m = detect_small_m_top(bars, supply_zone=(81751.7, 82061.9), max_bars_ago=6)
        self.assertIsNotNone(m)
        self.assertTrue(m["active"])
        ctx = build_structure_15m_context(bars, supply_zones=[(81751.7, 82061.9)])
        self.assertTrue(ctx["supply_reject"])
        self.assertTrue(ctx["active"])
        self.assertEqual(ctx["reason"], "m15_supply_reject_m_top")


if __name__ == "__main__":
    unittest.main()
