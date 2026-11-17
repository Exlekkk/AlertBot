"""A qualified closed trial remains independent of the early delivery ledger."""
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
from services.telegram import TelegramSendError
from test_early_observation import STAMP, evaluate, fixture


class FormalUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.path=str(self.root/'early.sqlite3')
        self.early=evaluate();self.early['open_time']=fixture()[3][-1]['open_time']
        ledger=EarlyObservationStore(self.path)
        ledger.reserve(self.early,STAMP-1000);ledger.delivered(self.early);ledger.close()
        self.scanner=SMCTScanner.__new__(SMCTScanner)
        self.scanner.symbol='BTCUSDT';self.scanner.logger=logging.getLogger('formal-upgrade-test')
        self.scanner.runtime_state=Mock()
        self.scanner.state_store=SignalStateStore(state_file=str(self.root/'formal.json'))
        self.scanner._fetch_enriched=Mock(return_value=fixture()[3])
        self.scanner._run_early_observations=Mock(return_value={'sent':0,'decisions':[]})
        self.closed=copy.deepcopy(self.early)
        self.closed.update(forming=False,closed_confirmation=True,alert_type='LOWER_KEY_ZONE_RECLAIM',
                           state_version='LOWER_RECLAIM_R1',observation_update={'pending_confirm':True})
        self.env=patch.dict(os.environ,{'SMCT_EARLY_OBSERVATION_MODE':'live','SMCT_EARLY_OBSERVATION_STATE_FILE':self.path})
        self.env.start()
    def tearDown(self):
        self.env.stop();self.tmp.cleanup()

    def run_decision(self, send_error=None):
        with patch('engine.scanner.FREEZE_MODE_SEND_X_ONLY',False), patch('engine.scanner.load_trend_state',return_value={}), patch('engine.scanner.decide_trend_segment',return_value=copy.deepcopy(self.closed)), patch('engine.scanner.send_telegram_message',side_effect=send_error) as send, patch('engine.scanner.save_observation_state') as save:
            result=self.scanner.run_once()
            return result,send.call_count,sum(c.args[2].get("pending_confirm") is True for c in save.call_args_list)

    def test_confirmed_reclaim_can_upgrade_early_observation_once(self):
        first,sends,pending=self.run_decision()
        self.assertTrue(first['ok'],first)
        self.assertEqual((first['sent'],sends,pending),(1,1,1))
        repeated,sends,pending=self.run_decision()
        self.assertEqual((repeated['sent'],sends,pending),(0,0,0))

    def test_qualified_closed_early_trial_uses_its_own_signature(self):
        self.closed.update(alert_type='EARLY_LONG_TRIAL',state_version='EARLY_LONG_TRIAL_R1')
        first,sends,pending=self.run_decision()
        self.assertEqual((first['sent'],sends,pending),(1,1,1))
        repeated,sends,pending=self.run_decision()
        self.assertEqual((repeated['sent'],sends,pending),(0,0,0))

    def test_failed_formal_delivery_creates_no_pending_and_can_retry(self):
        failed,sends,pending=self.run_decision(TelegramSendError('failure'))
        self.assertEqual((failed['sent'],sends,pending),(0,1,0))
        self.assertFalse((self.root/'formal.json').exists())
        success,sends,pending=self.run_decision()
        self.assertEqual((success['sent'],sends,pending),(1,1,1))

    def test_unqualified_closed_decision_does_not_upgrade(self):
        self.closed.update(should_alert=False,observation_update=None)
        result,sends,pending=self.run_decision()
        self.assertEqual((result['sent'],sends,pending),(0,0,0))


if __name__=='__main__': unittest.main()
