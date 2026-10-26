"""Closed-candle semantic regressions; no vendor Pine source is included."""
import unittest

from engine.chart_indicators import build_fibonacci_ote_context
from engine.ifvg import build_ifvg_context
from engine.sweep_hunter import build_sweep_context


def bars(n, price=100.):
    return [dict(open=price,high=price+2,low=price-2,close=price,volume=100.,open_time=i*3_600_000) for i in range(n)]


class OteEventOrderTests(unittest.TestCase):
    def test_both_swings_update_before_direction_shift(self):
        b=bars(75)
        b[10].update(high=110.,low=95.)
        b[25].update(high=101.,low=90.)
        b[50].update(high=120.,low=94.)
        before=build_fibonacci_ote_context(b[:60])
        self.assertEqual(before['trend'],'bear')
        self.assertEqual(before['anchor_low'],90.)
        confirmed=build_fibonacci_ote_context(b[:61])
        self.assertEqual(confirmed['trend'],'bull')
        self.assertEqual(confirmed['anchor_low'],94.)
        self.assertEqual(confirmed['anchor_high'],120.)
        self.assertEqual(confirmed['ote_zone'],(99.56,103.93))
        self.assertEqual(confirmed['shift_age_bars'],0)


    def test_bearish_shift_uses_same_bar_updated_high(self):
        b=bars(75)
        b[10].update(high=110.,low=95.)
        b[25].update(high=101.,low=90.)
        b[50].update(high=120.,low=94.)
        for k in b:
            k['open'],k['close']=200.-k['open'],200.-k['close']
            k['high'],k['low']=200.-k['low'],200.-k['high']
        ctx=build_fibonacci_ote_context(b[:61])
        self.assertEqual(ctx['trend'],'bear')
        self.assertEqual((ctx['anchor_high'],ctx['anchor_low']),(106.,80.))
        self.assertEqual(ctx['ote_zone'],(96.07,100.44))


class IfvgLifecycleTests(unittest.TestCase):
    def test_replaced_overlap_cannot_become_nearest_again(self):
        b=bars(45)
        for k in b: k.update(high=100.5,low=99.5)
        values={30:(100,104,100,103),31:(104,111,104,110),32:(110,112,110,111),33:(110,111,109,110),34:(108,108.5,107,108)}
        for i,v in values.items(): b[i].update(zip(('open','high','low','close'),v))
        ctx=build_ifvg_context(b)
        nearest=ctx['nearest_active']
        self.assertEqual((nearest['bottom'],nearest['top'],nearest['start_bar']),(100.5,107.,36))
        old=next(z for z in ctx['zones'] if z['start_bar']==31)
        self.assertTrue(old['mitigated'])
        self.assertTrue(old['invalidated'])

    def test_classic_wick_touch_keeps_zone_active(self):
        b=bars(35)
        for k in b: k.update(high=100.5,low=99.5)
        b[30].update(open=102.,high=104.,low=102.,close=103.)
        b[31].update(open=106.,high=107.,low=106.,close=106.5)
        b[32].update(open=106.,high=107.,low=105.,close=106.5)
        for i in (33,34): b[i].update(open=106.,high=107.,low=104.5,close=106.5)
        zone=next(z for z in build_ifvg_context(b)['zones'] if z['start_bar']==32)
        self.assertFalse(zone['mitigated'])
        self.assertFalse(zone['invalidated'])

    def test_gap_threshold_uses_previous_close_not_gap_midpoint(self):
        b=bars(31,9995.)
        for k in b: k.update(high=10000.,low=9990.)
        b[29].update(open=10000.,high=11010.,low=9995.,close=11000.)
        b[30].update(open=10025.,high=10040.,low=10021.,close=10030.)
        # Gap 21 is below 0.2% of prior close (22), even though it exceeds
        # 0.2% of the gap midpoint. Neither direction should create a zone.
        self.assertEqual(build_ifvg_context(b)['zones'],[])

    def test_bullish_gap_cannot_be_created_on_equal_threshold(self):
        b=bars(31,9995.)
        for k in b: k.update(high=10000.,low=9990.)
        b[29].update(open=9995.,high=10010.,low=9990.,close=10000.)
        b[30].update(open=10025.,high=10040.,low=10020.,close=10030.)
        self.assertEqual(build_ifvg_context(b)['zones'],[])


class SweepPivotSelectionTests(unittest.TestCase):
    def test_dual_pivot_creates_support_only(self):
        b=bars(30)
        b[10].update(high=120.,low=80.,volume=200.)
        b[25].update(open=110.,high=121.,low=100.,close=110.)
        ctx=build_sweep_context(b)
        self.assertFalse(ctx['swept'])
        self.assertEqual([z['price'] for z in ctx['active_levels']],[80.])

    def test_high_only_pivot_can_still_reject(self):
        b=bars(30)
        b[10].update(high=120.,low=99.,volume=200.)
        b[25].update(open=110.,high=121.,low=100.,close=110.)
        ctx=build_sweep_context(b)
        self.assertTrue(ctx['swept'])
        self.assertEqual((ctx['side'],ctx['level']),('buy_side',120.))

    def test_low_only_pivot_can_still_reclaim(self):
        b=bars(30)
        b[10].update(high=101.,low=80.,volume=200.)
        b[25].update(open=90.,high=100.,low=79.,close=90.)
        ctx=build_sweep_context(b)
        self.assertTrue(ctx['swept'])
        self.assertEqual((ctx['side'],ctx['level']),('sell_side',80.))


if __name__=='__main__': unittest.main()
