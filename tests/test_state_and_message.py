import unittest
from unittest.mock import Mock, patch


class TrendLogicTests(unittest.TestCase):
    def _decide(self, liq, msb, trend_state=None):
        from engine.trend_segments import decide_trend_segment
        return decide_trend_segment("BTCUSDT","1h",{"relation":"aligned","text":"4H 偏多"},liq,msb,{"matrix_direction":"bull"},{"momentum_desc":"动能 偏强","temperature_desc":"热度 中性"}, trend_state)

    def test_no_sweep_high_quality_no_structure_shift(self):
        liq = {"sweep_type":"none","reclaim_or_reject":"none","sweep_level":None,"prev_low":100,"prev_high":120}
        msb = {"direction":"bull","leg_type":"LONG","quality":95,"structure_zone":(108,112),"order_block_zone":(107,113),"mid_observe_zone":(109,111),"metrics":{"atr_move":1.2,"range_ratio":0.7,"body_quality":0.8}}
        d = self._decide(liq, msb)
        self.assertFalse(d["should_alert"])

    def test_sweep_mid_triggers_structure_shift(self):
        liq = {"sweep_type":"sellside","reclaim_or_reject":"reclaim","sweep_level":100,"prev_low":100,"prev_high":120}
        msb = {"direction":"bull","leg_type":"MID","quality":80,"structure_zone":(108,112),"order_block_zone":(107,113),"mid_observe_zone":(109,111),"metrics":{"atr_move":1.0,"range_ratio":0.5,"body_quality":0.6}}
        d = self._decide(liq, msb)
        self.assertEqual(d["alert_type"], "BULLISH_STRUCTURE_SHIFT")

    def test_continuation_requires_trend_state(self):
        liq = {"sweep_type":"none","reclaim_or_reject":"none","sweep_level":None,"prev_low":100,"prev_high":120}
        msb = {"direction":"bull","leg_type":"MID","quality":70,"structure_zone":(108,112),"order_block_zone":(107,113),"mid_observe_zone":(109,111),"metrics":{"atr_move":0.9,"range_ratio":0.4,"body_quality":0.6}}
        no_state = self._decide(liq, msb)
        with_state = self._decide(liq, msb, {"direction":"long","has_snapshot":True})
        self.assertFalse(no_state["should_alert"])
        self.assertEqual(with_state["alert_type"], "BULLISH_CONTINUATION")


class MsbLiquidityScannerCooldownTests(unittest.TestCase):
    def test_mid_observe_zone_reasonable(self):
        from engine.msb_ob import build_msb_ob_context
        liq = {"prev_high":120,"prev_low":100}
        bars=[{"open":110,"close":111,"high":112,"low":109,"atr":2},{"open":111,"close":116,"high":117,"low":110,"atr":2}]
        ctx = build_msb_ob_context(bars, liq)
        zl, zh = ctx["structure_zone"]; ml,mh = ctx["mid_observe_zone"]
        self.assertGreaterEqual(ml, zl-5)
        self.assertLessEqual(mh, zh+5)

    def test_close_buffer_blocks_touchline_sweep(self):
        from engine.liquidity import build_liquidity_context
        bars = [{"high":110,"low":100,"close":105,"atr":2}]*8 + [{"high":110.01,"low":100.0,"close":109.99,"atr":2}]
        ctx = build_liquidity_context(bars)
        self.assertEqual(ctx["sweep_type"], "none")

    def test_cooldown_trend_key_and_no_slotabc(self):
        from engine.cooldown import SignalStateStore
        s = SignalStateStore(state_file='/tmp/test_state.json')
        sig = {"alert_type":"BULLISH_STRUCTURE_SHIFT","symbol":"BTCUSDT","timeframe":"1h","direction":"long","signature":"BTCUSDT|1h|BULLISH_STRUCTURE_SHIFT|long|abc123|MID","state_version":"MID","price":100}
        s.mark_sent(sig)
        keys = list(s.last_sent.keys())
        self.assertTrue(any(k.startswith("TREND|BTCUSDT|1h|BULLISH_STRUCTURE_SHIFT|long|abc123|MID") for k in keys))
        self.assertFalse(any(k.startswith("SLOT|ABC") for k in keys))

    def test_scanner_neutral_not_short(self):
        from engine.scanner import SMCTScanner
        sc=SMCTScanner("BTCUSDT")
        data=[{"open":1,"high":2,"low":1,"close":2,"volume":1,"ema10":1,"ema20":1,"macd":0} for _ in range(60)]
        htf=sc._htf_context(data,"neutral")
        self.assertEqual(htf["relation"], "neutral")


class MessageAndIntervalsTests(unittest.TestCase):
    def test_message_banned_terms(self):
        from engine.trend_messages import format_trend_message
        msg=format_trend_message({"direction":"long","zone":(100,110),"htf_context":"4H 偏多","momentum_desc":"动能 偏强","temperature_desc":"热度 中性","invalid_level":99})
        for t in ["liquidity","MSB","OB","SMC","流动性","订单块","ICT","RAR","TAI"]:
            self.assertNotIn(t.lower(), msg.lower())

    def test_scanner_no_15m(self):
        from engine.scanner import SMCTScanner
        scanner=SMCTScanner("BTCUSDT")
        scanner.market_data=Mock(); scanner.market_data.get_klines.return_value=[{"open":1,"high":2,"low":1,"close":2,"volume":1} for _ in range(60)]
        scanner.state_store=Mock(); scanner.state_store.should_send.return_value=False
        scanner.runtime_state=Mock()
        with patch("engine.scanner.enrich_klines", side_effect=lambda x: x): scanner.run_once()
        intervals=[c.kwargs['interval'] for c in scanner.market_data.get_klines.call_args_list]
        self.assertEqual(sorted(set(intervals)), ["1h","4h"])

if __name__=='__main__':
    unittest.main()
