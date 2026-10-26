"""Plan B regression and offline Shadow coverage. No external network or sends."""
import copy
import json
import logging
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from engine.early_observation import INTERVAL_MS, early_observation_mode, evaluate_early_observation
from engine.early_observation_state import EarlyObservationStore
from engine.scanner import SMCTScanner
from engine.trend_messages import format_prealert_message, format_trend_message
from engine.trial_decision import assess_trial_candidate
from services.telegram import TelegramSendError

STAMP = 1_800_000_000_000 // 3_600_000 * 3_600_000


def fixture(tf='1h', short=False):
    duration = INTERVAL_MS[tf]
    def bar(stamp, vol=1000):
        return dict(open_time=stamp, close_time=stamp+duration-1, open=10000.,
                    high=10010., low=9990., close=10000., volume=vol, atr=100.)
    raw = [bar(STAMP-(20-i)*duration) for i in range(21)]
    raw[-1].update(volume=18000., open=10000., high=10030. if short else 10020.,
                   low=9980. if short else 9970., close=9990. if short else 10010.)
    closed = [dict(bar(STAMP-(40-i)*3_600_000), close_time=STAMP-(39-i)*3_600_000-1) for i in range(40)]
    htf = dict(h4_direction='bear' if short else 'bull', text='4H 偏空' if short else '4H 偏多')
    msb = {'fibonacci': dict(trend='bear' if short else 'bull', in_ote=True,
                            premium_discount='premium' if short else 'discount', ote_zone=(9980.,10020.))}
    aux = dict(rar_slope=-0.5 if short else 0.5, rar_above_trigger=not short,
               momentum_desc='动能 偏弱' if short else '动能 偏强')
    return ['BTCUSDT', tf, raw, closed, htf, {'prev_low':9800.,'prev_high':10200.}, msb, {}, aux, {}, {}, {}]


def evaluate(args=None, **kwargs):
    return evaluate_early_observation(*(args or fixture()), now_ms=STAMP+450_000, **kwargs)


class EarlyCandidateTests(unittest.TestCase):
    def test_both_source_timeframes_and_sides_use_existing_types(self):
        for tf in ('15m','1h'):
            for short in (False,True):
                with self.subTest(tf=tf,short=short):
                    d=evaluate(fixture(tf,short))
                    self.assertTrue(d['should_alert'], d)
                    self.assertEqual(d['direction'], 'short' if short else 'long')
                    self.assertEqual(d['alert_type'], ('PREALERT_SHORT' if short else 'PREALERT_LONG') if tf=='15m' else ('EARLY_SHORT_TRIAL' if short else 'EARLY_LONG_TRIAL'))
                    self.assertFalse(d['closed_confirmation'])
                    self.assertNotIn('observation_update',d)
                    self.assertFalse(any('confirmed_zone_reaction' in r or 'zone_accept_reject' in r for r in d['trial_evidence']))

    def test_same_timeframe_must_pass_both_volume_conditions(self):
        for tf,floor in (('15m',6000),('1h',12000)):
            args=fixture(tf)
            args[2][-1]['volume']=floor  # strict existing absolute floor
            self.assertFalse(evaluate(args)['should_alert'])
            args[2][-1]['volume']=18000
            for b in args[2][:-1]: b['volume']=11000
            self.assertEqual(evaluate(args)['suppress_reason'],'volume_not_abnormal')

    def test_baseline_excludes_forming_and_does_not_extrapolate(self):
        args=fixture();args[2][-1]['volume']=18000
        self.assertEqual(evaluate(args)['volume_ratio'],18)
        args[2][-1]['volume']=17999
        for b in args[2][:-1]: b['volume']=10000
        self.assertFalse(evaluate(args)['should_alert'])
        args[2][-1]['volume']=18000
        self.assertTrue(evaluate(args)['should_alert'])

    def test_raw_cannot_create_its_own_structure(self):
        args=fixture();args[6]={}
        self.assertEqual(evaluate(args)['suppress_reason'],'no_clear_structure_location')

    def test_no_forming_input_mutation_or_confirmed_evidence(self):
        args=fixture();before=copy.deepcopy(args)
        d=evaluate(args)
        self.assertEqual(args,before)
        self.assertEqual(d['evidence']['forming_volume']['confirmed'],False)
        self.assertEqual(d['structure_open_time'],STAMP-3_600_000)

    def test_rejects_stale_closed_and_stale_or_future_forming(self):
        args=fixture();args[3][-1]['open_time']-=3_600_000
        self.assertEqual(evaluate(args)['suppress_reason'],'stale_closed_structure')
        for offset in (-3_600_000,3_600_000):
            args=fixture();args[2][-1]['open_time']+=offset
            args[2][-1]['close_time']+=offset
            self.assertEqual(evaluate(args)['suppress_reason'],'not_current_forming_candle')

    def test_rejects_gaps_zero_baseline_and_nonfinite_data(self):
        args=fixture();args[2][-2]['open_time']-=3_600_000
        self.assertEqual(evaluate(args)['suppress_reason'],'non_contiguous_history')
        args=fixture()
        for b in args[2][:-1]: b['volume']=0
        self.assertFalse(evaluate(args)['should_alert'])
        for field in ('volume','close'):
            args=fixture();args[2][-1][field]=float('nan')
            self.assertFalse(evaluate(args)['should_alert'])

    def test_direction_risk_and_distance_remain_gated(self):
        args=fixture();args[2][-1].update(close=9990.)
        self.assertFalse(evaluate(args)['should_alert'])
        args=fixture();args[2][-1].update(low=9700.,close=10045.,high=10050.)
        self.assertIn('risk_too_wide',evaluate(args)['trial_quality_blocks'])
        args=fixture();args[2][-1].update(close=10200.,high=10210.)
        self.assertFalse(evaluate(args)['should_alert'])

    def test_closed_formal_state_is_read_only_and_15m_is_isolated(self):
        state=dict(last_formal_open_time=STAMP-3_600_000,last_formal_side='lower',pending_confirm=True)
        before=copy.deepcopy(state)
        self.assertEqual(evaluate(observation_state=state)['suppress_reason'],'recent_closed_observation')
        self.assertTrue(evaluate(fixture('15m'),observation_state=state)['should_alert'])
        self.assertEqual(state,before)

    def test_auto_range_cannot_rescue_wrong_edge_or_reward_risk(self):
        args=fixture();args[10]=dict(active=True,box_low=9800.,box_high=10015.,accepted_breakout='up')
        d=evaluate(args)
        self.assertIn('wrong_range_edge',d['trial_quality_blocks'])
        self.assertIn('poor_range_reward_risk',d['trial_quality_blocks'])
        self.assertFalse(d['should_alert'])

    def test_unchanged_templates_label_forming_without_new_family(self):
        d=evaluate();text=format_trend_message(d)
        self.assertIn('1H 试多观察',text)
        self.assertIn('未收盘',text);self.assertIn('待收盘确认',text)
        self.assertNotIn('未收盘放量弱提醒',text)
        d=evaluate(fixture('15m'));text=format_prealert_message(d)
        self.assertIn('15m 做多🟢位置提醒',text)
        self.assertIn('待收盘确认',text)
        self.assertNotIn('试多',text)

    def test_modes_fail_closed(self):
        for mode,expected in [('live','live'),('shadow','shadow'),('typo','off'),('','off')]:
            with patch.dict(os.environ,{'SMCT_EARLY_OBSERVATION_MODE':mode}):
                self.assertEqual(early_observation_mode(),expected)


class EarlyLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=str(Path(self.tmp.name)/'early.sqlite3')
        self.store=EarlyObservationStore(self.path)
    def tearDown(self):
        self.store.close();self.tmp.cleanup()

    def test_restart_repeated_bar_zone_drift_and_opposite_cooldown(self):
        d=evaluate();self.assertTrue(self.store.reserve(d,STAMP))
        self.store.close();self.store=EarlyObservationStore(self.path)
        self.assertFalse(self.store.reserve(d,STAMP+60_000))
        d['zone']=(9981,10021) # drifting anchors cannot bypass candle cooldown
        self.assertFalse(self.store.reserve(d,STAMP+60_000))
        d['direction']='short'
        self.assertFalse(self.store.reserve(d,STAMP+60_000))
        d['open_time']+=2*3_600_000
        self.assertTrue(self.store.reserve(d,STAMP+2*3_600_000))

    def test_same_side_rearms_at_four_bars(self):
        d=evaluate();self.store.reserve(d,STAMP)
        d['open_time']+=3*3_600_000
        self.assertFalse(self.store.reserve(d,d['open_time']))
        d['open_time']+=3_600_000
        self.assertTrue(self.store.reserve(d,d['open_time']))

    def test_timeframes_do_not_share_candle_ids_and_twin_sends_coalesce(self):
        h=evaluate();m=evaluate(fixture('15m'))
        self.assertTrue(self.store.reserve(h,STAMP))
        self.assertFalse(self.store.reserve(m,STAMP))
        m['open_time']+=900_000
        self.assertTrue(self.store.reserve(m,STAMP+900_000))
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM delivery').fetchone()[0],2)

    def test_early_delivery_does_not_consume_formal_signature(self):
        from engine.cooldown import SignalStateStore
        d=evaluate();self.store.reserve(d,STAMP);self.store.delivered(d)
        formal=SignalStateStore(state_file=str(Path(self.tmp.name)/'formal.json'))
        self.assertTrue(formal.should_send(d))
        self.assertFalse(formal.state_file.exists())

    def test_two_connections_cannot_reserve_same_event(self):
        other=EarlyObservationStore(self.path)
        try:
            d=evaluate();self.assertTrue(self.store.reserve(d,STAMP))
            self.assertFalse(other.reserve(d,STAMP))
        finally: other.close()


class AutoRangePermissionsTests(unittest.TestCase):
    def test_accepted_flag_cannot_bypass_middle_threshold_and_cooldown(self):
        ctx=dict(scores={'long':5.,'short':0.},evidence={'long':['rar_turn_up:+1.00'],'short':[]},
                 evidence_bundle_keys=['ifvg'],chart_framework_active=True,
                 range_active=True,box_low=9900.,box_high=10100.,box_position='middle',accepted_breakout='up')
        state=dict(last_formal_side='lower',last_formal_open_time=STAMP-3_600_000,
                   last_formal_box_low=9900.,last_formal_box_high=10100.)
        r=assess_trial_candidate('long','LOWER_KEY_ZONE_RECLAIM',(9990,10010),9980,
                                dict(open=10000,high=10020,low=9990,close=10005,atr=100),
                                10000,'fibonacci_ote','reclaimed_above',ctx,state,STAMP)
        self.assertEqual(r['minimum_score'],10.)
        self.assertIn('same_box_same_side_cooldown_without_new_information',r['hard_blocks'])


class ScannerEarlyShadowTests(unittest.TestCase):
    def test_actual_delivery_path_shadow_live_error_and_restart(self):
        args=fixture();closed,htf,liq,msb,matrix,aux,vp,rl,ev=args[3:]
        scanner=SMCTScanner.__new__(SMCTScanner)
        scanner.symbol='BTCUSDT';scanner.logger=logging.getLogger('early-test')
        scanner.market_data=Mock()
        scanner.market_data.get_klines.side_effect=lambda symbol,interval,limit:fixture(interval)[2]
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ,{'SMCT_EARLY_OBSERVATION_STATE_FILE':str(Path(td)/'ledger.sqlite3')}), patch('engine.scanner.time.time',return_value=(STAMP+450_000)/1000), patch('engine.scanner.load_observation_state',return_value={}), patch('engine.scanner.send_telegram_message') as send, patch('engine.scanner.save_observation_state') as save:
            payload=(closed,htf,liq,msb,matrix,aux,vp,rl,ev)
            shadow=scanner._run_early_observations(*payload,mode='shadow')
            self.assertEqual(shadow['sent'],0);send.assert_not_called();save.assert_not_called()
            self.assertTrue(shadow['decisions'][0]['delivery_eligible'])
            live=scanner._run_early_observations(*payload,mode='live')
            self.assertEqual(live['sent'],1);self.assertEqual(send.call_count,1)
            again=scanner._run_early_observations(*payload,mode='live')
            self.assertEqual(again['sent'],0);self.assertEqual(send.call_count,1)
            save.assert_not_called()

    def test_full_scanner_shadow_cannot_send_or_write_formal_state(self):
        scanner=SMCTScanner.__new__(SMCTScanner)
        scanner.symbol='BTCUSDT';scanner.logger=logging.getLogger('early-test')
        scanner.runtime_state=Mock();scanner.state_store=Mock();scanner.market_data=Mock()
        scanner._fetch_enriched=Mock(return_value=fixture()[3])
        scanner.market_data.get_klines.side_effect=lambda symbol,interval,limit:fixture(interval)[2]
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ,{'SMCT_EARLY_OBSERVATION_MODE':'live','SMCT_EARLY_OBSERVATION_STATE_FILE':str(Path(td)/'ledger.sqlite3')}), patch('engine.scanner.time.time',return_value=(STAMP+450_000)/1000), patch('engine.scanner.load_observation_state',return_value={}), patch('engine.scanner.load_trend_state',return_value={}), patch('engine.scanner.send_telegram_message') as send, patch('engine.scanner.save_observation_state') as save, patch('engine.scanner.save_trend_state') as trend:
            result=scanner.run_once(shadow=True)
            self.assertTrue(result['ok'],result)
            self.assertNotIn('error',result['summary']['early_observation'])
            send.assert_not_called();save.assert_not_called();trend.assert_not_called()
            scanner.state_store.mark_sent.assert_not_called()
            scanner.runtime_state.mark_scan.assert_not_called()
            scanner.runtime_state.mark_sent_signal.assert_not_called()
            self.assertFalse(Path(td,'ledger.sqlite3').exists())

    def test_uncertain_telegram_outcome_does_not_retry_or_create_pending(self):
        scanner=SMCTScanner.__new__(SMCTScanner)
        scanner.symbol='BTCUSDT';scanner.logger=logging.getLogger('early-test');scanner.market_data=Mock()
        scanner.market_data.get_klines.side_effect=lambda symbol,interval,limit:fixture(interval)[2]
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ,{'SMCT_EARLY_OBSERVATION_STATE_FILE':str(Path(td)/'ledger.sqlite3')}), patch('engine.scanner.time.time',return_value=(STAMP+450_000)/1000), patch('engine.scanner.load_observation_state',return_value={}), patch('engine.scanner.send_telegram_message',side_effect=TelegramSendError('timeout')) as send, patch('engine.scanner.save_observation_state') as save:
            for _ in range(2):
                r=scanner._run_early_observations(*fixture()[3:],mode='live')
                self.assertEqual(r['sent'],0)
            self.assertEqual(send.call_count,1);save.assert_not_called()


if __name__=='__main__': unittest.main()
