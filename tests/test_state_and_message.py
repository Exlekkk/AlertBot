import unittest


def _heat_profile(budget: str = "normal") -> dict:
    return {
        "tai_heat_15m": "warm",
        "tai_heat_1h": "warm",
        "tai_heat_4h": "warm",
        "tai_budget_mode": budget,
        "freeze_mode": budget == "frozen",
        "icepoint_1h": False,
        "tai_rising_15m": True,
        "tai_rising_1h": True,
    }


class SignalConfidenceTests(unittest.TestCase):
    def test_a_confidence_only_high_when_clean(self):
        from engine.signals import _signal_confidence

        clean = _signal_confidence(
            "A_LONG",
            "trend_drive_long",
            6,
            "confirm_long",
            ["structure", "decision_zone", "ema_supportive", "momo_1h"],
            _heat_profile("normal"),
            "bull",
        )
        weak = _signal_confidence(
            "A_LONG",
            "trend_drive_long",
            3,
            "repairing_long",
            ["decision_zone"],
            _heat_profile("restricted"),
            "lean_bull",
        )

        self.assertGreaterEqual(clean, 80)
        self.assertLess(weak, clean)
        self.assertLessEqual(clean, 88)

    def test_b_confidence_not_artificially_high(self):
        from engine.signals import _signal_confidence

        b_value = _signal_confidence(
            "B_PULLBACK_SHORT",
            "repair_short",
            4,
            "repairing_short",
            ["decision_zone", "trigger_repair"],
            _heat_profile("normal"),
            "bear",
        )

        self.assertGreaterEqual(b_value, 58)
        self.assertLessEqual(b_value, 82)

    def test_c_confidence_stays_low_to_mid(self):
        from engine.signals import _signal_confidence

        c_value = _signal_confidence(
            "C_LEFT_LONG",
            "probe_long",
            3,
            "probing_long",
            ["decision_zone", "early_warning"],
            _heat_profile("normal"),
            "neutral",
        )

        self.assertGreaterEqual(c_value, 50)
        self.assertLessEqual(c_value, 70)

    def test_counter_trend_a_gets_pulled_down(self):
        from engine.signals import _signal_confidence

        normal = _signal_confidence(
            "A_SHORT",
            "trend_drive_short",
            4,
            "confirm_short",
            ["structure", "decision_zone"],
            _heat_profile("normal"),
            "bear",
        )
        counter = _signal_confidence(
            "A_SHORT",
            "trend_drive_short",
            4,
            "confirm_short",
            ["structure", "decision_zone"],
            _heat_profile("normal"),
            "lean_bull",
        )

        self.assertLess(counter, normal)

    def test_low_heat_budget_reduces_confidence(self):
        from engine.signals import _signal_confidence

        normal = _signal_confidence(
            "B_PULLBACK_LONG",
            "repair_long",
            5,
            "repairing_long",
            ["decision_zone", "trigger_repair", "momo_15m"],
            _heat_profile("normal"),
            "bull",
        )
        restricted = _signal_confidence(
            "B_PULLBACK_LONG",
            "repair_long",
            5,
            "repairing_long",
            ["decision_zone", "trigger_repair", "momo_15m"],
            _heat_profile("restricted"),
            "bull",
        )
        frozen = _signal_confidence(
            "B_PULLBACK_LONG",
            "repair_long",
            5,
            "repairing_long",
            ["decision_zone", "trigger_repair", "momo_15m"],
            _heat_profile("frozen"),
            "bull",
        )

        self.assertLess(restricted, normal)
        self.assertLess(frozen, restricted)


class XSignalCompatibilityTests(unittest.TestCase):
    @staticmethod
    def _tai_bar(value: float) -> dict:
        return {
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 10000.0,
            "vol_sma20": 5000.0,
            "atr": 1.0,
            "tai_value": value,
            "tai_p20": 20.0,
            "tai_p40": 40.0,
            "tai_p60": 60.0,
            "tai_p80": 80.0,
        }

    def test_x_signal_uses_real_4h_tai_heat(self):
        from engine.x_signals import _base_signal

        signal = _base_signal(
            signal="X_BREAKOUT_LONG",
            symbol="BTCUSDT",
            price=100.0,
            abnormal_type="异动上破",
            basis=["impulse_breakout_up"],
            k_15m=self._tai_bar(10.0),
            k_1h=self._tai_bar(50.0),
            k_4h=self._tai_bar(90.0),
            zone_low=99.0,
            zone_high=101.0,
            trigger_level=100.5,
        )

        self.assertEqual(signal["tai_heat_15m"], "cold")
        self.assertEqual(signal["tai_heat_1h"], "neutral")
        self.assertEqual(signal["tai_heat_4h"], "hot")

    def test_abnormal_entrypoint_still_imports(self):
        from engine.abnormal import detect_abnormal_signals

        self.assertTrue(callable(detect_abnormal_signals))


if __name__ == "__main__":
    unittest.main()
