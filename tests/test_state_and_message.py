import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


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



    def test_x_hard_volume_gate_uses_or_between_15m_and_1h(self):
        from engine.x_signals import _passes_hard_volume_gate

        low_15m = {"volume": 5000.0}
        high_15m = {"volume": 7000.0}
        low_1h = {"volume": 11000.0}
        high_1h = {"volume": 13000.0}

        self.assertTrue(_passes_hard_volume_gate(high_15m, low_1h))
        self.assertTrue(_passes_hard_volume_gate(low_15m, high_1h))
        self.assertTrue(_passes_hard_volume_gate(high_15m, high_1h))
        self.assertFalse(_passes_hard_volume_gate(low_15m, low_1h))


class RARIndicatorTests(unittest.TestCase):
    def test_rar_trigger_matches_pine_order(self):
        from engine.indicators import ema, rar_components, rsi_series

        values = [100 + i * 0.7 + (i % 5) * 0.3 for i in range(60)]
        length = 15
        half = int(length / 2)

        result = rar_components(values, length=length, power=1.0)
        expected_trigger = ema(rsi_series(ema(values, half), length), half)

        self.assertEqual(len(result["rar_value"]), len(values))
        self.assertEqual(len(result["rar_trigger"]), len(values))
        self.assertAlmostEqual(result["rar_trigger"][-1], expected_trigger[-1], places=9)
        self.assertGreaterEqual(result["rar_value"][-1], 0.0)
        self.assertLessEqual(result["rar_value"][-1], 100.0)


class TelegramSendTests(unittest.TestCase):
    @patch("services.telegram.requests.post")
    def test_send_telegram_message_requires_ok_true(self, mock_post):
        from services.telegram import TelegramSendError, send_telegram_message

        response = Mock(status_code=200, text='{"ok": false, "description": "bad chat"}')
        response.json.return_value = {"ok": False, "description": "bad chat"}
        mock_post.return_value = response

        with self.assertRaises(TelegramSendError):
            send_telegram_message("token", "chat", "hello")

    @patch("services.telegram.requests.post")
    def test_send_telegram_message_returns_json_when_ok(self, mock_post):
        from services.telegram import send_telegram_message

        response = Mock(status_code=200, text='{"ok": true}')
        response.json.return_value = {"ok": True, "result": {"message_id": 123}}
        mock_post.return_value = response

        result = send_telegram_message("token", "chat", "hello")
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["message_id"], 123)

    def test_scanner_does_not_mark_sent_when_telegram_fails(self):
        from engine.scanner import SMCTScanner
        from services.telegram import TelegramSendError

        signal = {
            "signal": "A_LONG",
            "symbol": "BTCUSDT",
            "direction": "long",
            "priority": 1,
            "price": 100.0,
            "zone_low": 99.0,
            "zone_high": 101.0,
            "state_1h": "trend_drive_long",
            "trigger_15m_state": "confirm_long",
            "tai_budget_mode": "normal",
            "background_4h_direction": "bull",
            "tai_heat_1h": "warm",
        }
        signal_result = {
            "signals": [signal],
            "near_miss_signals": [],
            "background_4h_direction": "bull",
            "state_1h": "trend_drive_long",
            "trigger_15m_state": "confirm_long",
            "tai_budget_mode": "normal",
            "tai_heat_1h": "warm",
            "tai_heat_4h": "warm",
            "blocked_reasons": [],
        }

        with patch.object(SMCTScanner, "_fetch_enriched", return_value=[{}]), \
             patch("engine.scanner.get_logger", return_value=Mock()), \
             patch("engine.scanner.detect_signals", return_value=signal_result), \
             patch("engine.scanner.detect_x_signals", return_value=[]), \
             patch("engine.scanner.send_telegram_message", side_effect=TelegramSendError("fail")):
            scanner = SMCTScanner("BTCUSDT")
            scanner.state_store = Mock()
            scanner.state_store.should_send.return_value = True
            scanner.runtime_state = Mock()

            result = scanner.run_once()

        self.assertTrue(result["ok"])
        self.assertEqual(result["sent"], 0)
        scanner.state_store.mark_sent.assert_not_called()
        scanner.runtime_state.mark_sent_signal.assert_not_called()


class StatePersistenceTests(unittest.TestCase):
    def test_signal_state_store_writes_json_atomically(self):
        from engine.cooldown import SignalStateStore

        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "signal_state.json"
            store = SignalStateStore(state_file=str(state_file))
            store.mark_sent({"signal": "A_LONG", "symbol": "BTCUSDT", "direction": "long", "price": 100.0})

            self.assertTrue(state_file.exists())
            self.assertFalse(state_file.with_suffix(".json.tmp").exists())
            data = json.loads(state_file.read_text())
            self.assertTrue(any(key.startswith("FAMILY|ABC|") for key in data))

    def test_runtime_state_store_writes_json_atomically(self):
        from engine.runtime_state import RuntimeStateStore

        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "runtime_state.json"
            store = RuntimeStateStore(state_file=str(state_file))
            store.mark_scan(ok=True, symbol="BTCUSDT", summary={"state_1h": "trend_drive_long"})

            self.assertTrue(state_file.exists())
            self.assertFalse(state_file.with_suffix(".json.tmp").exists())
            data = json.loads(state_file.read_text())
            self.assertTrue(data["last_scan_ok"])
            self.assertEqual(data["last_symbol"], "BTCUSDT")


if __name__ == "__main__":
    unittest.main()
