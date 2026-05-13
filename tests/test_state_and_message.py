import tempfile
import unittest
from unittest.mock import Mock, patch


class TrendSweepWindowTests(unittest.TestCase):
    def test_recent_sweep_then_shift_allowed(self):
        from engine.trend_segments import decide_trend_segment
        liq={"sweep_type":"sellside","reclaim_or_reject":"reclaim","sweep_level":100,"recent_sweep_valid":True,"bars_since_sweep":2,"prev_low":100,"prev_high":120}
        msb={"direction":"bull","leg_type":"MID","quality":78,"structure_zone":(108,112),"order_block_zone":(107,113),"mid_observe_zone":(109,111),"metrics":{"atr_move":1,"range_ratio":0.4,"body_quality":0.6}}
        d=decide_trend_segment("BTCUSDT","1h",{"relation":"aligned","text":"4H 偏多"},liq,msb,{"matrix_direction":"bull"},{"momentum_desc":"动能 偏强","temperature_desc":"热度 中性"})
        self.assertEqual(d["alert_type"], "BULLISH_STRUCTURE_SHIFT")

    def test_sweep_expired_no_shift(self):
        from engine.trend_segments import decide_trend_segment
        liq={"sweep_type":"sellside","reclaim_or_reject":"reclaim","sweep_level":100,"recent_sweep_valid":False,"bars_since_sweep":6,"prev_low":100,"prev_high":120}
        msb={"direction":"bull","leg_type":"LONG","quality":90,"structure_zone":(108,112),"order_block_zone":(107,113),"mid_observe_zone":(109,111),"metrics":{"atr_move":1.2,"range_ratio":0.6,"body_quality":0.7}}
        d=decide_trend_segment("BTCUSDT","1h",{"relation":"aligned","text":"4H 偏多"},liq,msb,{"matrix_direction":"bull"},{"momentum_desc":"动能 偏强","temperature_desc":"热度 中性"})
        self.assertFalse(d["should_alert"])


class ContinuationStateTests(unittest.TestCase):
    def test_no_trend_state_no_continuation(self):
        from engine.trend_segments import decide_trend_segment
        liq={"sweep_type":"none","reclaim_or_reject":"none","sweep_level":None,"recent_sweep_valid":False,"bars_since_sweep":None,"prev_low":100,"prev_high":120}
        msb={"direction":"bull","leg_type":"MID","quality":70,"structure_zone":(108,112),"order_block_zone":(107,113),"mid_observe_zone":(109,111),"metrics":{"atr_move":0.9,"range_ratio":0.4,"body_quality":0.6}}
        d=decide_trend_segment("BTCUSDT","1h",{"relation":"aligned","text":"4H 偏多"},liq,msb,{"matrix_direction":"bull"},{"momentum_desc":"动能 偏强","temperature_desc":"热度 中性"})
        self.assertFalse(d["should_alert"])

    def test_with_trend_state_can_continuation(self):
        from engine.trend_segments import decide_trend_segment
        liq={"sweep_type":"none","reclaim_or_reject":"none","sweep_level":None,"recent_sweep_valid":False,"bars_since_sweep":None,"prev_low":100,"prev_high":120}
        msb={"direction":"bull","leg_type":"LONG","quality":76,"structure_zone":(108,112),"order_block_zone":(107,113),"mid_observe_zone":(109,111),"metrics":{"atr_move":1.1,"range_ratio":0.5,"body_quality":0.65}}
        d=decide_trend_segment("BTCUSDT","1h",{"relation":"aligned","text":"4H 偏多"},liq,msb,{"matrix_direction":"bull"},{"momentum_desc":"动能 偏强","temperature_desc":"热度 中性"}, trend_state={"direction":"long","has_snapshot":True})
        self.assertEqual(d["alert_type"], "BULLISH_CONTINUATION")


class ScannerSnapshotTests(unittest.TestCase):
    def test_scanner_passes_trend_state(self):
        from engine.scanner import SMCTScanner
        scanner=SMCTScanner("BTCUSDT")
        scanner.market_data=Mock(); scanner.market_data.get_klines.return_value=[{"open":1,"high":2,"low":1,"close":2,"volume":1,"ema10":1,"ema20":1,"macd":0} for _ in range(60)]
        scanner.state_store=Mock(); scanner.state_store.should_send.return_value=False
        scanner.runtime_state=Mock()
        with patch("engine.scanner.enrich_klines", side_effect=lambda x: x), patch("engine.scanner.load_trend_state", return_value={"direction":"long","has_snapshot":True}) as mload, patch("engine.scanner.decide_trend_segment", return_value={"direction":"long","zone":(1,2),"state_version":"MID","should_alert":False,"alert_type":"NO_TRADE_RANGE"}) as mdec:
            scanner.run_once()
        self.assertTrue(mload.called)
        self.assertIn("trend_state", mdec.call_args.kwargs)


class OtherTests(unittest.TestCase):
    def test_liquidity_recent_field(self):
        from engine.liquidity import build_liquidity_context
        bars=[{"high":110,"low":100,"close":105,"atr":2} for _ in range(10)]
        ctx=build_liquidity_context(bars)
        self.assertIn("recent_sweep_valid", ctx)

    def test_message_has_emoji(self):
        from engine.trend_messages import format_trend_message
        msg=format_trend_message({"direction":"long","zone":(100,110),"htf_context":"4H 偏多","momentum_desc":"动能 偏强","temperature_desc":"热度 中性","invalid_level":99})
        self.assertTrue(msg.startswith("📈"))

if __name__=='__main__':
    unittest.main()
