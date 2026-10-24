import unittest

from engine.trend_messages import (
    KEY_ZONE_OBSERVATION_SUPPRESS_ALERT_TYPES,
    CONFIRM_SUPPRESS_ALERT_TYPES,
    TRIAL_PROBE_SEND_ALERT_TYPES,
    should_send_alert_copy,
)


class AlertSendPolicyTests(unittest.TestCase):
    def test_allow_trial_probe_types(self):
        for alert_type in (
            "EARLY_LONG_TRIAL",
            "LOWER_KEY_ZONE_RECLAIM",
            "EARLY_SHORT_TRIAL",
            "UPPER_KEY_ZONE_REJECTION",
            "BULLISH_CONTINUATION",
            "BEARISH_CONTINUATION",
        ):
            self.assertTrue(should_send_alert_copy({"alert_type": alert_type}), alert_type)
            self.assertIn(alert_type, TRIAL_PROBE_SEND_ALERT_TYPES)

    def test_suppress_key_zone_observation_family(self):
        for alert_type in (
            "LOWER_KEY_ZONE_TEST",
            "FAST_PULLBACK_OBSERVE",
            "RANGE_LOWER_PROBE",
            "UPPER_KEY_ZONE_TEST",
            "FAST_REBOUND_OBSERVE",
            "RANGE_UPPER_PROBE",
        ):
            self.assertFalse(should_send_alert_copy({"alert_type": alert_type}), alert_type)
            self.assertIn(alert_type, KEY_ZONE_OBSERVATION_SUPPRESS_ALERT_TYPES)

    def test_suppress_confirm_and_secondary(self):
        for alert_type in (
            "BULLISH_STRUCTURE_SHIFT",
            "BEARISH_STRUCTURE_SHIFT",
            "SECONDARY_CONFIRM_LOWER",
            "SECONDARY_CONFIRM_UPPER",
        ):
            self.assertFalse(should_send_alert_copy({"alert_type": alert_type}), alert_type)
            self.assertIn(alert_type, CONFIRM_SUPPRESS_ALERT_TYPES)

    def test_unknown_type_not_sent(self):
        self.assertFalse(should_send_alert_copy({"alert_type": "NO_TRADE_RANGE"}))
        self.assertFalse(should_send_alert_copy({}))


if __name__ == "__main__":
    unittest.main()
