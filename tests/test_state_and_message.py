import unittest


class TrendSegmentTests(unittest.TestCase):
    def _base(self, leg: str, sweep_level: float = 100.0) -> dict:
        liq = {
            "sweep_type": "sellside",
            "reclaim_or_reject": "reclaim",
            "sweep_level": sweep_level,
            "recent_sweep_valid": True,
            "bars_since_sweep": 1,
            "prev_low": 95,
            "prev_high": 120,
        }
        msb = {
            "direction": "bull",
            "leg_type": leg,
            "quality": 80,
            "structure_zone": (108, 112),
            "order_block_zone": (107, 113),
            "mid_observe_zone": (109, 111),
            "metrics": {
                "atr_move": 1,
                "range_ratio": 0.5,
                "body_quality": 0.6,
            },
        }

        from engine.trend_segments import decide_trend_segment

        return decide_trend_segment(
            "BTCUSDT",
            "1h",
            {"relation": "aligned", "text": "4H 偏多"},
            liq,
            msb,
            {"matrix_direction": "bull"},
            {"momentum_desc": "动能 偏强", "temperature_desc": "热度 中性"},
        )

    def test_sweep_short_suppressed(self):
        decision = self._base("SHORT")
        self.assertFalse(decision["should_alert"])
        self.assertEqual(decision["suppress_reason"], "short_structure_leg")

    def test_sweep_mid_allows_shift(self):
        decision = self._base("MID")
        self.assertEqual(decision["alert_type"], "BULLISH_STRUCTURE_SHIFT")

    def test_recent_sweep_uses_sweep_level_as_invalid(self):
        decision = self._base("MID", sweep_level=101.5)
        self.assertEqual(decision["invalid_level"], 101.5)


class MessageTests(unittest.TestCase):
    def test_bull_message_emoji(self):
        from engine.trend_messages import format_trend_message

        msg = format_trend_message(
            {
                "direction": "long",
                "zone": (100, 110),
                "htf_context": "4H 偏多",
                "momentum_desc": "动能 偏强",
                "temperature_desc": "热度 中性",
                "invalid_level": 99,
            }
        )
        self.assertTrue(msg.startswith("📈"))

    def test_bear_message_emoji(self):
        from engine.trend_messages import format_trend_message

        msg = format_trend_message(
            {
                "direction": "short",
                "zone": (100, 110),
                "htf_context": "4H 偏空",
                "momentum_desc": "动能 偏弱",
                "temperature_desc": "热度 中性",
                "invalid_level": 111,
            }
        )
        self.assertTrue(msg.startswith("📉"))

    def test_banned_terms_no_leak(self):
        from engine.trend_messages import format_trend_message

        msg = format_trend_message(
            {
                "direction": "long",
                "zone": (100, 110),
                "htf_context": "4H 偏多",
                "momentum_desc": "动能 偏强",
                "temperature_desc": "热度 中性",
                "invalid_level": 99,
            }
        )
        for term in ["liquidity", "MSB", "OB", "SMC", "ICT", "RAR", "TAI", "流动性", "订单块"]:
            self.assertNotIn(term.lower(), msg.lower())


if __name__ == "__main__":
    unittest.main()
