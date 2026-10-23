import math
import unittest
from unittest.mock import patch


def _wave_bars(count: int = 520, interval_ms: int = 3_600_000) -> list[dict]:
    bars = []
    for i in range(count):
        center = 30_000 + i * 8 + 600 * math.sin(i / 12)
        open_ = center - 40 * math.sin(i)
        close = center + 40 * math.sin(i / 2)
        bars.append(
            {
                "open_time": i * interval_ms,
                "close_time": (i + 1) * interval_ms - 1,
                "open": open_,
                "high": max(open_, close) + 120 + (i % 7) * 3,
                "low": min(open_, close) - 120 - (i % 5) * 3,
                "close": close,
                "volume": 1000 + (i % 31) * 80 + (500 if i % 41 == 0 else 0),
            }
        )
    return bars


class SuppliedChartConfigTests(unittest.TestCase):
    def test_htf_relation_is_recomputed_for_actual_candidate_direction(self):
        from engine.framework import relation_to_htf

        htf = {
            "h4_direction": "bull",
            "h4_strength": 0.9,
            "text": "4H 偏多",
            "relation": "strong_counter",
        }
        self.assertEqual(relation_to_htf(htf, "long"), "aligned")
        self.assertEqual(relation_to_htf(htf, "short"), "strong_counter")
        self.assertEqual(relation_to_htf(htf, "neutral"), "neutral")

    def test_replay_end_boundary_includes_binance_close_millisecond(self):
        from zoneinfo import ZoneInfo

        from scripts.replay_1h_decisions import _parse_time

        start = _parse_time("2026-06-12T23:59:59", ZoneInfo("Asia/Singapore"))
        end = _parse_time("2026-06-12T23:59:59", ZoneInfo("Asia/Singapore"), end_boundary=True)
        self.assertEqual(end - start, 999)

    def test_custom_chart_parameters_are_transcribed(self):
        from engine.trend_config import TREND_ENGINE_CONFIG

        chart = TREND_ENGINE_CONFIG["chart_framework"]
        self.assertEqual(chart["ict"]["structure_length"], 6)
        self.assertEqual(chart["ict"]["ob_swing_lookback"], 14)
        self.assertFalse(chart["ict"]["use_candle_body"])
        self.assertEqual(chart["ict"]["liquidity_margin"], 5.0)
        self.assertEqual(chart["fvg_volume_profile"]["lower_timeframe_input"], "13")
        self.assertEqual(chart["fvg_volume_profile"]["bins"], 20)
        self.assertEqual(chart["fvg_volume_profile"]["gap_filter"], 0.6)
        self.assertEqual(chart["tai"], {"formation_length": 30, "history_length": 350})

    def test_fibonacci_includes_requested_705_79_and_extensions(self):
        from engine.chart_indicators import build_fibonacci_ote_context
        from engine.indicators import enrich_klines

        context = build_fibonacci_ote_context(enrich_klines(_wave_bars()))
        self.assertTrue(context["available"])
        self.assertIn("0.705", context["levels"])
        self.assertIn("0.79", context["levels"])
        self.assertIn("1.272", context["extension_targets"])
        self.assertIn("1.618", context["extension_targets"])
        self.assertLess(context["ote_zone"][0], context["ote_zone"][1])


class SuppliedPineTranslationTests(unittest.TestCase):
    def test_ict_structure_uses_latest_opposite_pivot_reference(self):
        from engine.ict_ob import _zigzag_points

        bars = [
            {"open": 95, "high": 120, "low": 80, "close": close, "volume": 1000}
            for close in (95, 95, 95, 95, 95, 99, 105, 111)
        ]
        pivot_events = [
            [(3, 3, 100.0), (5, 5, 110.0)],
            [(2, 2, 90.0), (4, 4, 95.0), (6, 6, 100.0)],
        ]
        with patch("engine.ict_ob._pivot_indices", side_effect=pivot_events):
            _, events = _zigzag_points(bars, 6)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "bullish_mss")
        self.assertEqual(events[0]["level"], 110.0)
        self.assertEqual(events[0]["index"], 7)

    def test_inertial_selects_length_closest_to_prior_value(self):
        from engine.indicators import inertial_stochastic_components

        closes = [100, 99, 98, 97, 96, 95, 96, 98, 101, 104, 106, 108]
        bars = [
            {"open": close - 0.5, "high": close + 1, "low": close - 1, "close": close, "volume": 1000}
            for close in closes
        ]
        result = inertial_stochastic_components(bars, min_length=10, max_length=40, smooth_k=3, smooth_d=3)
        self.assertAlmostEqual(result["raw"][9], 90.9090909091, places=7)
        self.assertTrue(result["turn_up"][9])

    def test_chartprime_fvg_profile_uses_supplied_filter_and_stays_active(self):
        from engine.chart_indicators import build_fvg_volume_profile_context

        bars = []
        for i in range(202):
            bars.append(
                {"open_time": i * 3_600_000, "close_time": (i + 1) * 3_600_000 - 1, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000}
            )
        bars.append({"open_time": 202 * 3_600_000, "close_time": 203 * 3_600_000 - 1, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000})
        bars.append({"open_time": 203 * 3_600_000, "close_time": 204 * 3_600_000 - 1, "open": 101, "high": 106, "low": 100, "close": 105, "volume": 5000})
        bars.append({"open_time": 204 * 3_600_000, "close_time": 205 * 3_600_000 - 1, "open": 104, "high": 107, "low": 103, "close": 105, "volume": 2500})

        context = build_fvg_volume_profile_context(bars)
        self.assertTrue(context["available"])
        self.assertEqual(context["bullish"][-1]["zone"], (101.0, 103.0))
        self.assertEqual(context["profile_source"], "parent_candle_proxy")

    def test_high_volume_pivot_builds_atr_padded_resistance(self):
        from engine.chart_indicators import build_high_volume_pivot_context

        bars = []
        for i in range(260):
            high = 150 if i == 210 else 101
            volume = 10_000 if i == 210 else 100
            bars.append({"open": 100, "high": high, "low": 99, "close": 100, "volume": volume})
        context = build_high_volume_pivot_context(bars)
        self.assertIsNotNone(context["resistance"])
        self.assertEqual(context["resistance"]["pivot_index"], 210)
        self.assertEqual(context["orderflow_source"], "candle_direction_volume_proxy")

    def test_orderflow_is_explicitly_a_candle_volume_proxy(self):
        from engine.chart_indicators import build_volume_orderflow_proxy

        bars = _wave_bars(30)
        context = build_volume_orderflow_proxy(bars)
        self.assertFalse(context["is_true_orderflow"])
        self.assertEqual(context["source"], "candle_direction_volume_proxy")

    def test_ict_reimplementation_uses_custom_settings_and_one_visible_ob(self):
        from engine.ict_ob import build_ict_ob_context
        from engine.indicators import enrich_klines

        context = build_ict_ob_context(enrich_klines(_wave_bars()))
        self.assertEqual(context["source"], "luxalgo_pine_reimplementation")
        self.assertTrue(context["settings_match_chart"])
        self.assertLessEqual(len(context["bullish_zones"]), 1)
        self.assertLessEqual(len(context["bearish_zones"]), 1)
        self.assertIn(context["premium_discount"], {"premium", "discount", "equilibrium", "unknown"})

    def test_htf_bias_does_not_depend_on_ema_crosses(self):
        from engine.framework import build_htf_bias_context
        from engine.indicators import enrich_klines

        bars = enrich_klines(_wave_bars())
        for bar in bars:
            bar["ema10"] = 0.0
            bar["ema20"] = 1_000_000.0
        context = build_htf_bias_context(bars)
        self.assertEqual(context["source"], "smc_ict_structure")
        self.assertFalse(any("ema" in reason for reason in context["bias_evidence"]))


class LayeredDecisionSafetyTests(unittest.TestCase):
    @staticmethod
    def _trial_context(evidence: list[str]) -> dict:
        return {
            "scores": {"long": 10.0, "short": 2.0},
            "evidence": {"long": evidence, "short": []},
            "atr": 1.0,
            "range_active": False,
            "box_low": None,
            "box_high": None,
            "box_position": "unknown",
            "accepted_breakout": "none",
            "long_extension_atr": 0.5,
            "short_extension_atr": 0.5,
            "ict_bullish_active": True,
            "ict_bearish_active": False,
            "ict_bullish_distance_atr": 0.1,
            "ict_bearish_distance_atr": None,
            "ict_ob_coexist": False,
            "chart_framework_active": True,
            "liquidity_bars_since": None,
        }

    def test_formal_zone_reaction_needs_directional_catalyst(self):
        from engine.trial_decision import assess_trial_candidate

        result = assess_trial_candidate(
            "long",
            "LOWER_KEY_ZONE_RECLAIM",
            (98.5, 99.2),
            98.0,
            {"open": 99.0, "high": 100.0, "low": 98.7, "close": 99.5, "atr": 1.0},
            99.0,
            "fvg_zone",
            "reclaimed_above",
            self._trial_context(["ict_plus_ob_active:+1.50"]),
            current_bar=20,
        )
        self.assertFalse(result["allow_formal"])
        self.assertIn("formal_without_directional_catalyst", result["hard_blocks"])

    def test_near_ict_ob_with_rar_can_be_early_catalyst(self):
        from engine.trial_decision import assess_trial_candidate

        result = assess_trial_candidate(
            "long",
            "LOWER_KEY_ZONE_RECLAIM",
            (98.5, 99.2),
            98.0,
            {"open": 99.0, "high": 100.0, "low": 98.7, "close": 99.5, "atr": 1.0},
            99.0,
            "ict_plus_ob",
            "reclaimed_above",
            self._trial_context(["rar_turn_up:+1.00"]),
            current_bar=20,
        )
        self.assertTrue(result["directional_catalyst"])
        self.assertTrue(result["allow_formal"])

    def test_secondary_push_does_not_require_another_same_candle_mss(self):
        from engine.trial_decision import assess_trial_candidate

        context = self._trial_context([])
        context.update(
            {
                "chart_framework_active": True,
                "box_low": 97.0,
                "box_high": 103.0,
                "range_cluster": "same-box",
            }
        )
        state = {
            "last_formal_side": "lower",
            "last_formal_open_time": 19,
            "last_formal_box_low": 97.0,
            "last_formal_box_high": 103.0,
        }
        result = assess_trial_candidate(
            "long",
            "SECONDARY_CONFIRM_LOWER",
            (98.5, 99.2),
            98.5,
            {"open": 99.2, "high": 100.2, "low": 99.0, "close": 100.0, "atr": 1.0},
            99.0,
            "pending_confirmation",
            "reclaimed_above",
            context,
            observation_state=state,
            current_bar=20,
        )
        self.assertTrue(result["directional_catalyst"])
        self.assertTrue(result["allow_formal"])
        self.assertNotIn("same_box_same_side_cooldown_without_new_information", result["hard_blocks"])

    def test_same_box_same_side_requires_new_information_during_cooldown(self):
        from engine.trial_decision import assess_trial_candidate

        context = self._trial_context(["sellside_sweep_reclaim:+3.50"])
        context.update(
            {
                "range_active": True,
                "box_low": 97.0,
                "box_high": 103.0,
                "box_position": "lower_edge",
                "range_cluster": "same-box",
                "liquidity_bars_since": 1,
            }
        )
        state = {
            "last_formal_side": "lower",
            "last_formal_open_time": 10,
            "last_formal_box_low": 97.0,
            "last_formal_box_high": 103.0,
        }
        result = assess_trial_candidate(
            "long",
            "LOWER_KEY_ZONE_RECLAIM",
            (98.5, 99.2),
            98.0,
            {"open": 99.0, "high": 100.0, "low": 98.7, "close": 99.5, "atr": 1.0},
            99.0,
            "fvg_zone",
            "reclaimed_above",
            context,
            observation_state=state,
            current_bar=11,
        )
        self.assertFalse(result["allow_formal"])
        self.assertIn("same_box_same_side_cooldown_without_new_information", result["hard_blocks"])


if __name__ == "__main__":
    unittest.main()
