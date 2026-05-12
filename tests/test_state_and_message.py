import unittest
from unittest.mock import Mock, patch


class ConfigWiringTests(unittest.TestCase):
    def test_trend_config_has_required_keys(self):
        from engine.trend_config import TREND_ENGINE_CONFIG
        self.assertIn("liquidity", TREND_ENGINE_CONFIG)
        self.assertIn("msb", TREND_ENGINE_CONFIG)
        self.assertIn("score", TREND_ENGINE_CONFIG)
        self.assertIn("zone", TREND_ENGINE_CONFIG)


class LiquidityTests(unittest.TestCase):
    def test_sellside_sweep_requires_sweep_and_reclaim(self):
        from engine.liquidity import build_liquidity_context
        bars = [{"high":110,"low":100,"close":105}] * 10 + [{"high":108,"low":98,"close":101}]
        ctx = build_liquidity_context(bars)
        self.assertTrue(ctx["sellside_sweep"])
        self.assertEqual(ctx["reclaim_or_reject"], "reclaim")

    def test_buyside_sweep_requires_sweep_and_reject(self):
        from engine.liquidity import build_liquidity_context
        bars = [{"high":110,"low":100,"close":105}] * 10 + [{"high":112,"low":101,"close":109}]
        ctx = build_liquidity_context(bars)
        self.assertTrue(ctx["buyside_sweep"])
        self.assertEqual(ctx["reclaim_or_reject"], "reject")


class TrendDecisionTests(unittest.TestCase):
    def _ctx(self, quality=88, relation="counter", leg="LONG"):
        from engine.trend_segments import decide_trend_segment
        return decide_trend_segment("BTCUSDT","1h",{"relation":relation,"text":"4H 偏空"},{"prev_low":100,"prev_high":120,"sweep_type":"sellside","sweep_level":100,"reclaim_or_reject":"reclaim"},{"direction":"bull","leg_type":leg,"quality":quality,"structure_zone":(108,112),"order_block_zone":(107,113),"mid_observe_zone":(109,111),"metrics":{"atr_move":1.1,"range_ratio":0.5,"body_quality":0.7}},{"matrix_direction":"bull"}, {"momentum_desc":"动能 偏强","temperature_desc":"热度 中性"})

    def test_debug_fields_complete(self):
        d = self._ctx()
        for k in ["symbol","timeframe","alert_type","direction","score","score_breakdown","htf_context","htf_relation","sweep_type","sweep_level","reclaim_or_reject","msb_direction","msb_quality","msb_atr_ratio","msb_range_ratio","msb_body_quality","zone_source","zone_low","zone_high","invalid_level","should_alert","suppress_reason"]:
            self.assertIn(k, d)

    def test_strong_counter_high_quality_allows(self):
        d = self._ctx(quality=96, relation="strong_counter", leg="LONG")
        self.assertTrue(d["should_alert"])

    def test_strong_counter_medium_quality_suppressed(self):
        d = self._ctx(quality=60, relation="strong_counter", leg="MID")
        self.assertFalse(d["should_alert"])
        self.assertEqual(d["suppress_reason"], "medium_quality_1h_against_strong_4h")

    def test_continuation_has_zone_source_and_invalid_level(self):
        d = self._ctx(quality=70, relation="aligned", leg="MID")
        self.assertIn(d["alert_type"], ["BULLISH_CONTINUATION", "BEARISH_CONTINUATION"])
        self.assertTrue(d["zone_source"])
        self.assertTrue(d["invalid_level"])


class ScannerAndMessageTests(unittest.TestCase):
    def test_scanner_no_15m(self):
        from engine.scanner import SMCTScanner
        scanner = SMCTScanner("BTCUSDT")
        scanner.market_data = Mock(); scanner.market_data.get_klines.return_value = [{"open":1,"high":2,"low":1,"close":2,"volume":1} for _ in range(60)]
        scanner.state_store = Mock(); scanner.state_store.should_send.return_value=False
        scanner.runtime_state = Mock()
        with patch("engine.scanner.enrich_klines", side_effect=lambda x: x):
            scanner.run_once()
        intervals = [x.kwargs["interval"] for x in scanner.market_data.get_klines.call_args_list]
        self.assertEqual(sorted(set(intervals)), ["1h","4h"])

    def test_message_has_required_fields_without_banned_terms(self):
        from engine.trend_messages import format_trend_message, BANNED
        msg = format_trend_message({"direction":"short","zone":(100,110),"htf_context":"4H 偏空","momentum_desc":"动能 偏弱","temperature_desc":"热度 中性","invalid_level":111})
        for key in ["结构转空","关注区间","大周期","动能与热度","风险位","结论"]:
            self.assertIn(key, msg)
        lower = msg.lower()
        banned_cn = ["流动性","订单块","msb","choch","smc","ict","rar","tai"]
        for banned in BANNED + banned_cn:
            self.assertNotIn(banned.lower(), lower)


if __name__ == '__main__':
    unittest.main()
