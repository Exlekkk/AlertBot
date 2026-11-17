"""Freeze controls business outbound only; scans/shadow remain available."""
import copy
import logging
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from engine.cooldown import SignalStateStore
from engine.early_observation_state import EarlyObservationStore
from engine.scanner import SMCTScanner
from test_early_observation import STAMP, evaluate, fixture


class ScannerFreezeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.path=str(self.root/'early.sqlite3')
        self.scanner=SMCTScanner.__new__(SMCTScanner)
        self.scanner.symbol='BTCUSDT';self.scanner.logger=logging.getLogger('freeze-test')
        self.scanner.runtime_state=Mock()
        self.scanner.state_store=SignalStateStore(state_file=str(self.root/'formal.json'))
        self.scanner._fetch_enriched=Mock(return_value=fixture()[3])
        self.scanner.market_data=Mock()
        self.scanner.market_data.get_klines.side_effect=lambda symbol,interval,limit:fixture(interval)[2]
        ledger=Mock();ledger.already_observed_close.return_value=False
        self.scanner._early_store=Mock(return_value=ledger)
        self.env=patch.dict(os.environ,{'SMCT_EARLY_OBSERVATION_MODE':'live','SMCT_EARLY_OBSERVATION_STATE_FILE':self.path})
        self.env.start()
    def tearDown(self):
        self.env.stop();self.tmp.cleanup()

    def closed_scan(self, frozen, decision):
        with patch('engine.scanner.FREEZE_MODE_SEND_X_ONLY',frozen,create=True), patch('engine.scanner.load_trend_state',return_value={}), patch('engine.scanner.decide_trend_segment',return_value=copy.deepcopy(decision)), patch('engine.scanner.send_telegram_message') as send, patch('engine.scanner.save_observation_state') as save:
            result=self.scanner.run_once()
            pending=sum(c.args[2].get('pending_confirm') is True for c in save.call_args_list)
            return result,send.call_count,pending

    def test_freeze_blocks_all_formal_trial_families(self):
        for name in ('EARLY_LONG_TRIAL','LOWER_KEY_ZONE_RECLAIM','EARLY_SHORT_TRIAL','UPPER_KEY_ZONE_REJECTION','BULLISH_CONTINUATION','BEARISH_CONTINUATION'):
            with self.subTest(alert_type=name):
                d=evaluate();d.update(forming=False,alert_type=name,observation_update={'pending_confirm':True})
                if name in ('EARLY_SHORT_TRIAL','UPPER_KEY_ZONE_REJECTION','BEARISH_CONTINUATION'): d['direction']='short'
                result,sends,pending=self.closed_scan(True,d)
                self.assertTrue(result['ok'],result)
                self.assertEqual((result['sent'],sends,pending),(0,0,0))
                self.assertFalse(self.scanner.state_store.state_file.exists())
                self.scanner.runtime_state.mark_scan.assert_called()

    def test_unfreeze_allows_delivery_without_a_phantom_frozen_slot(self):
        d=evaluate();d.update(forming=False,alert_type='LOWER_KEY_ZONE_RECLAIM',observation_update={'pending_confirm':True})
        frozen,sends,pending=self.closed_scan(True,d)
        self.assertEqual((frozen['sent'],sends,pending),(0,0,0))
        live,sends,pending=self.closed_scan(False,d)
        self.assertEqual((live['sent'],sends,pending),(1,1,1))

    def early_scan(self, frozen, mode):
        # Use the actual ledger here, not the formal-scan dedupe stub.
        self.scanner._early_store=lambda selected:EarlyObservationStore(self.path+('.shadow' if selected=='shadow' else ''))
        with patch('engine.scanner.FREEZE_MODE_SEND_X_ONLY',frozen,create=True), patch('engine.scanner.time.time',return_value=(STAMP+450_000)/1000), patch('engine.scanner.load_observation_state',return_value={}), patch('engine.scanner.send_telegram_message') as send, patch('engine.scanner.save_observation_state') as save:
            result=self.scanner._run_early_observations(*fixture()[3:],mode=mode)
            save.assert_not_called()
            return result,send.call_count

    def test_freeze_early_does_not_reserve_or_send_then_unfreeze_can_send(self):
        result,sends=self.early_scan(True,'live')
        self.assertEqual((result['sent'],sends),(0,0))
        db=EarlyObservationStore(self.path)
        self.assertEqual(db.db.execute('SELECT count(*) FROM delivery').fetchone()[0],0)
        db.close()
        live,sends=self.early_scan(False,'live')
        self.assertEqual((live['sent'],sends),(1,1))

    def test_shadow_can_evaluate_candidates_while_frozen(self):
        result,sends=self.early_scan(True,'shadow')
        self.assertEqual((result['sent'],sends),(0,0))
        self.assertTrue(result['decisions'][0]['should_alert'])
        self.assertTrue(result['decisions'][0]['delivery_eligible'])
        self.assertFalse(Path(self.path).exists())


if __name__=='__main__': unittest.main()
