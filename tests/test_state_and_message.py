import unittest
from unittest.mock import Mock, patch


class TrendSegmentTests(unittest.TestCase):
    def _base(self, leg):
        liq={"sweep_type":"sellside","reclaim_or_reject":"reclaim","sweep_level":100,"recent_sweep_valid":True,"bars_since_sweep":1,"prev_low":100,"prev_high":120}
        msb={"direction":"bull","leg_type":leg,"quality":80,"structure_zone":(108,112),"order_block_zone":(107,113),"mid_observe_zone":(109,111),"metrics":{"atr_move":1,"range_ratio":0.5,"body_quality":0.6}}
        from engine.trend_segments import decide_trend_segment
        return decide_trend_segment("BTCUSDT","1h",{"relation":"aligned","text":"4H 偏多"},liq,msb,{"matrix_direction":"bull"},{"momentum_desc":"动能 偏强","temperature_desc":"热度 中性"})

    def test_sweep_short_suppressed(self):
        d=self._base("SHORT")
        self.assertFalse(d["should_alert"])
        self.assertEqual(d["suppress_reason"], "short_structure_leg")

    def test_sweep_mid_allows_shift(self):
        d=self._base("MID")
        self.assertEqual(d["alert_type"], "BULLISH_STRUCTURE_SHIFT")


class LiquidityHistoryTests(unittest.TestCase):
    def test_recent_sweep_uses_historical_prev_levels(self):
        from engine.liquidity import build_liquidity_context
        bars=[{"high":100,"low":90,"close":95,"atr":1} for _ in range(10)]
        bars += [{"high":101,"low":89,"close":92,"atr":1}]  # historical sweep candidate
        bars += [{"high":140,"low":130,"close":135,"atr":1}] * 2  # distort latest levels
        ctx=build_liquidity_context(bars)
        self.assertIn("recent_sweep_valid", ctx)


class SnapshotPathTests(unittest.TestCase):
    def test_snapshot_not_tmp_default(self):
        from engine.trend_snapshot import STATE_FILE
        self.assertNotIn("/tmp/alertbot_trend_snapshot.json", str(STATE_FILE))


class MessageTests(unittest.TestCase):
    def test_bull_message_emoji(self):
        from engine.trend_messages import format_trend_message
        msg = format_trend_message({"direction":"long","zone":(100,110),"htf_context":"4H 偏多","momentum_desc":"动能 偏强","temperature_desc":"热度 中性","invalid_level":99})
        self.assertTrue(msg.startswith("📈"))

    def test_bear_message_emoji(self):
        from engine.trend_messages import format_trend_message
        msg = format_trend_message({"direction":"short","zone":(100,110),"htf_context":"4H 偏空","momentum_desc":"动能 偏弱","temperature_desc":"热度 中性","invalid_level":111})
        self.assertTrue(msg.startswith("📉"))


if __name__=='__main__':
    unittest.main()
