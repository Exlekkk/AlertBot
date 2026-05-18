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

        fetch_calls: list[str] = []

        def fake_fetch(self, interval: str):
            fetch_calls.append(interval)
            return [{"close": 100.0, "ema10": 2.0, "ema20": 1.0, "volume": 100.0, "atr": 1.0}] * 30

        liq = {
            "sweep_type": "sellside",
            "reclaim_or_reject": "reclaim",
            "sweep_level": 99.0,
            "recent_sweep_valid": True,
            "bars_since_sweep": 1,
            "prev_low": 99.0,
            "prev_high": 110.0,
        }
        msb = {
            "direction": "bull",
            "leg_type": "MID",
            "quality": 80,
            "structure_zone": (108.0, 112.0),
            "order_block_zone": (107.0, 113.0),
            "mid_observe_zone": (109.0, 111.0),
            "metrics": {"atr_move": 1.0, "range_ratio": 0.5, "body_quality": 0.7},
        }

        with patch.object(SMCTScanner, "_fetch_enriched", fake_fetch), \
             patch("engine.scanner.get_logger", return_value=Mock()), \
             patch("engine.scanner.build_liquidity_context", return_value=liq), \
             patch("engine.scanner.build_msb_ob_context", return_value=msb), \
             patch("engine.scanner.build_trend_matrix_proxy", return_value={"matrix_direction": "bull"}), \
             patch("engine.scanner.build_aux_filters_proxy", return_value={"momentum_desc": "动能 偏强", "temperature_desc": "热度 中性", "price": 111.0}), \
             patch("engine.scanner.load_trend_state", return_value={"direction": "neutral", "has_snapshot": False}), \
             patch("engine.scanner.save_trend_state"), \
             patch("engine.scanner.send_telegram_message", side_effect=TelegramSendError("fail")):
            scanner = SMCTScanner("BTCUSDT")
            scanner.state_store = Mock()
            scanner.state_store.should_send.return_value = True
            scanner.runtime_state = Mock()

            result = scanner.run_once()

        self.assertTrue(result["ok"])
        self.assertEqual(result["sent"], 0)
        self.assertEqual(sorted(fetch_calls), ["1h", "4h"])
        scanner.state_store.mark_sent.assert_not_called()
        scanner.runtime_state.mark_sent_signal.assert_not_called()


class TrendSegmentTests(unittest.TestCase):
    def _base(self, leg: str, sweep_level: float = 100.0, sweep: bool = True, trend_state: dict | None = None) -> dict:
        liq = {
            "sweep_type": "sellside" if sweep else "none",
            "reclaim_or_reject": "reclaim" if sweep else "none",
            "sweep_level": sweep_level if sweep else None,
            "recent_sweep_valid": sweep,
            "bars_since_sweep": 1 if sweep else None,
            "prev_low": 95.0,
            "prev_high": 120.0,
        }
        msb = {
            "direction": "bull",
            "leg_type": leg,
            "quality": 80,
            "structure_zone": (108.0, 112.0),
            "order_block_zone": (107.0, 113.0),
            "mid_observe_zone": (109.0, 111.0),
            "metrics": {
                "atr_move": 1.0,
                "range_ratio": 0.5,
                "body_quality": 0.6,
            },
        }

        from engine.trend_segments import decide_trend_segment

        return decide_trend_segment(
            "BTCUSDT",
            "1h",
            {"relation": "aligned", "text": "4H 偏多"},
            liq,
            msb,
            {"matrix_direction": "bull"},
            {"momentum_desc": "动能 偏强", "temperature_desc": "热度 中性", "price": 111.0},
            trend_state=trend_state,
        )

    def test_sweep_short_suppressed(self):
        decision = self._base("SHORT")
        self.assertFalse(decision["should_alert"])
        self.assertEqual(decision["suppress_reason"], "short_structure_leg")

    def test_sweep_mid_allows_shift(self):
        decision = self._base("MID")
        self.assertEqual(decision["alert_type"], "BULLISH_STRUCTURE_SHIFT")
        self.assertTrue(decision["should_alert"])

    def test_high_quality_without_sweep_does_not_shift(self):
        decision = self._base("LONG", sweep=False)
        self.assertEqual(decision["alert_type"], "NO_TRADE_RANGE")
        self.assertFalse(decision["should_alert"])
        self.assertEqual(decision["suppress_reason"], "no_sweep_no_trend_state")

    def test_continuation_requires_existing_trend_state(self):
        decision = self._base("MID", sweep=False, trend_state={"direction": "long", "has_snapshot": True})
        self.assertEqual(decision["alert_type"], "BULLISH_CONTINUATION")
        self.assertTrue(decision["should_alert"])
        self.assertEqual(decision["zone_source"], "mid_continuation_zone")

    def test_recent_sweep_uses_sweep_level_as_invalid(self):
        decision = self._base("MID", sweep_level=101.5)
        self.assertEqual(decision["invalid_level"], 101.5)

    def test_strong_counter_does_not_suppress_high_quality_1h(self):
        decision = self._base("LONG")
        from engine.trend_segments import decide_trend_segment

        decision = decide_trend_segment(
            "BTCUSDT",
            "1h",
            {"relation": "strong_counter", "text": "4H 偏空"},
            {
                "sweep_type": "sellside",
                "reclaim_or_reject": "reclaim",
                "sweep_level": 100.0,
                "recent_sweep_valid": True,
                "bars_since_sweep": 1,
                "prev_low": 95.0,
                "prev_high": 120.0,
            },
            {
                "direction": "bull",
                "leg_type": "LONG",
                "quality": 98,
                "structure_zone": (108.0, 112.0),
                "order_block_zone": (107.0, 113.0),
                "mid_observe_zone": (109.0, 111.0),
                "metrics": {"atr_move": 1.3, "range_ratio": 0.6, "body_quality": 0.8},
            },
            {"matrix_direction": "bull"},
            {"momentum_desc": "动能 偏强", "temperature_desc": "热度 中性", "price": 111.0},
        )
        self.assertTrue(decision["should_alert"])

    def test_strong_counter_suppresses_medium_quality_1h(self):
        from engine.trend_segments import decide_trend_segment

        decision = decide_trend_segment(
            "BTCUSDT",
            "1h",
            {"relation": "strong_counter", "text": "4H 偏空"},
            {
                "sweep_type": "sellside",
                "reclaim_or_reject": "reclaim",
                "sweep_level": 100.0,
                "recent_sweep_valid": True,
                "bars_since_sweep": 1,
                "prev_low": 95.0,
                "prev_high": 120.0,
            },
            {
                "direction": "bull",
                "leg_type": "MID",
                "quality": 55,
                "structure_zone": (108.0, 112.0),
                "order_block_zone": (107.0, 113.0),
                "mid_observe_zone": (109.0, 111.0),
                "metrics": {"atr_move": 0.8, "range_ratio": 0.35, "body_quality": 0.55},
            },
            {"matrix_direction": "bull"},
            {"momentum_desc": "动能 一般", "temperature_desc": "热度 中性", "price": 111.0},
        )
        self.assertFalse(decision["should_alert"])
        self.assertEqual(decision["suppress_reason"], "medium_quality_1h_against_strong_4h")


class LiquidityTests(unittest.TestCase):
    def _bar(self, o=105.0, h=110.0, l=100.0, c=105.0, atr=2.0):
        return {"open": o, "high": h, "low": l, "close": c, "atr": atr}

    def test_recent_sweep_uses_historical_bar_own_previous_range(self):
        from engine.liquidity import build_liquidity_context

        bars = [self._bar() for _ in range(26)]
        bars.append(self._bar(o=101.0, h=106.0, l=99.0, c=101.0))  # sellside sweep of 100 and reclaim
        bars.append(self._bar(o=106.0, h=109.0, l=104.0, c=108.0))
        bars.append(self._bar(o=108.0, h=112.0, l=107.0, c=111.0))

        ctx = build_liquidity_context(bars, lookback=24)

        self.assertEqual(ctx["sweep_type"], "sellside")
        self.assertEqual(ctx["reclaim_or_reject"], "reclaim")
        self.assertEqual(ctx["bars_since_sweep"], 2)
        self.assertEqual(ctx["sweep_level"], 100.0)

    def test_close_buffer_rejects_borderline_fake_sweep(self):
        from engine.liquidity import build_liquidity_context

        bars = [self._bar() for _ in range(26)]
        bars.append(self._bar(o=100.1, h=105.0, l=99.99, c=100.01))
        bars.append(self._bar(o=105.0, h=109.0, l=102.0, c=106.0))

        ctx = build_liquidity_context(bars, lookback=24)

        self.assertEqual(ctx["sweep_type"], "none")
        self.assertFalse(ctx["recent_sweep_valid"])


class MessageTests(unittest.TestCase):
    def _decision(self, direction="long", alert_type="BULLISH_STRUCTURE_SHIFT") -> dict:
        return {
            "direction": direction,
            "alert_type": alert_type,
            "zone": (100.0, 110.0),
            "htf_context": "4H 偏多" if direction == "long" else "4H 偏空",
            "momentum_desc": "动能 偏强" if direction == "long" else "动能 偏弱",
            "temperature_desc": "热度 中性",
            "invalid_level": 99.0 if direction == "long" else 111.0,
        }

    def test_bull_message_emoji(self):
        from engine.trend_messages import format_trend_message

        msg = format_trend_message(self._decision("long", "BULLISH_STRUCTURE_SHIFT"))
        self.assertTrue(msg.startswith("📈 BTC 1H 多头确认 📈"))
        self.assertIn("结构正在转多", msg)

    def test_bear_message_emoji(self):
        from engine.trend_messages import format_trend_message

        msg = format_trend_message(self._decision("short", "BEARISH_STRUCTURE_SHIFT"))
        self.assertTrue(msg.startswith("📉 BTC 1H 空头确认 📉"))
        self.assertIn("结构正在转空", msg)

    def test_continuation_message_uses_external_safe_wording(self):
        from engine.trend_messages import format_trend_message

        msg = format_trend_message(self._decision("long", "BULLISH_CONTINUATION"))
        self.assertTrue(msg.startswith("📈 BTC 1H 试多观察 📈"))
        self.assertIn("多头结构仍在延续", msg)
        self.assertIn("趋势中段关键区", msg)

    def test_banned_terms_no_leak(self):
        from engine.trend_messages import format_trend_message

        msg = format_trend_message(self._decision("long", "BULLISH_STRUCTURE_SHIFT"))
        for term in ["liquidity", "MSB", "OB", "SMC", "ICT", "RAR", "TAI", "流动性", "订单块"]:
            self.assertNotIn(term.lower(), msg.lower())

    def test_zone_note_is_short_and_without_usage_label(self):
        from engine.trend_messages import format_trend_message

        msg = format_trend_message(self._decision("long", "LOWER_KEY_ZONE_RECLAIM"))
        self.assertIn("100.00 - 110.00\n下方承接观察区，回踩不破才有确认价值。", msg)
        self.assertNotIn("用途：", msg)

    def test_upper_rejection_zone_note(self):
        from engine.trend_messages import format_trend_message

        msg = format_trend_message(self._decision("short", "UPPER_KEY_ZONE_REJECTION"))
        self.assertIn("100.00 - 110.00\n上方承压观察区，反抽不破才有确认价值。", msg)
        self.assertNotIn("用途：", msg)


class ScannerPipelineTests(unittest.TestCase):
    def test_htf_context_keeps_neutral_relation(self):
        from engine.scanner import SMCTScanner

        with patch("engine.scanner.get_logger", return_value=Mock()):
            scanner = SMCTScanner("BTCUSDT")
        ctx = scanner._htf_context([{"ema10": 2.0, "ema20": 1.0, "close": 100.0, "atr": 1.0}], "neutral")
        self.assertEqual(ctx["relation"], "neutral")

    def test_scanner_only_fetches_4h_and_1h(self):
        from engine.scanner import SMCTScanner

        calls: list[str] = []

        def fake_fetch(self, interval: str):
            calls.append(interval)
            return [{"close": 100.0, "ema10": 1.0, "ema20": 1.0, "volume": 100.0, "atr": 1.0}] * 30

        with patch.object(SMCTScanner, "_fetch_enriched", fake_fetch), \
             patch("engine.scanner.get_logger", return_value=Mock()), \
             patch("engine.scanner.build_liquidity_context", return_value={"sweep_type": "none", "reclaim_or_reject": "none", "sweep_level": None, "recent_sweep_valid": False, "prev_low": 90.0, "prev_high": 110.0}), \
             patch("engine.scanner.build_msb_ob_context", return_value={"direction": "neutral", "leg_type": "SHORT", "quality": 0, "structure_zone": (99.0, 101.0), "order_block_zone": (98.0, 102.0), "mid_observe_zone": (99.5, 100.5), "metrics": {"atr_move": 0, "range_ratio": 0, "body_quality": 0}}), \
             patch("engine.scanner.build_trend_matrix_proxy", return_value={"matrix_direction": "neutral"}), \
             patch("engine.scanner.build_aux_filters_proxy", return_value={"momentum_desc": "动能 一般", "temperature_desc": "热度 中性", "price": 100.0}), \
             patch("engine.scanner.load_trend_state", return_value={"direction": "neutral", "has_snapshot": False}):
            scanner = SMCTScanner("BTCUSDT")
            scanner.state_store = Mock()
            scanner.runtime_state = Mock()
            result = scanner.run_once()

        self.assertTrue(result["ok"])
        self.assertEqual(sorted(calls), ["1h", "4h"])


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

    def test_trend_state_store_does_not_write_abc_slot(self):
        from engine.cooldown import SignalStateStore

        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "signal_state.json"
            store = SignalStateStore(state_file=str(state_file))
            store.mark_sent(
                {
                    "alert_type": "BULLISH_STRUCTURE_SHIFT",
                    "symbol": "BTCUSDT",
                    "timeframe": "1h",
                    "direction": "long",
                    "price": 100.0,
                    "signature": "BTCUSDT|1h|BULLISH_STRUCTURE_SHIFT|long|abcdef1234|MID",
                    "state_version": "MID",
                }
            )

            data = json.loads(state_file.read_text())
            self.assertTrue(any(key.startswith("TREND|") for key in data))
            self.assertFalse(any(key.startswith("SLOT|ABC|") for key in data))

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

    def test_trend_snapshot_state_roundtrip(self):
        from engine import trend_snapshot

        with tempfile.TemporaryDirectory() as tmp:
            original = trend_snapshot.STATE_FILE
            trend_snapshot.STATE_FILE = Path(tmp) / "trend_snapshot.json"
            try:
                self.assertFalse(trend_snapshot.load_trend_state("BTCUSDT", "1h")["has_snapshot"])
                trend_snapshot.save_trend_state("BTCUSDT", "1h", "long", "sig")
                loaded = trend_snapshot.load_trend_state("BTCUSDT", "1h")
                self.assertEqual(loaded["direction"], "long")
                self.assertTrue(loaded["has_snapshot"])
                self.assertFalse(trend_snapshot.STATE_FILE.with_suffix(".json.tmp").exists())
            finally:
                trend_snapshot.STATE_FILE = original


if __name__ == "__main__":
    unittest.main()

class KeyZoneObservationTests(unittest.TestCase):
    @staticmethod
    def _bar(open_: float, high: float, low: float, close: float, atr: float = 100.0) -> dict:
        return {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "atr": atr,
            "ema10": close,
            "ema20": close,
                    }

    def _pullback_inputs(self):
        from engine.key_zones import decide_key_zone_observation

        klines = [self._bar(10000, 10050, 9950, 10000) for _ in range(25)]
        klines += [
            self._bar(10000, 10100, 9950, 10000),
            self._bar(10000, 10020, 9900, 9950),
            self._bar(9950, 9960, 9700, 9750),
        ]
        liq = {
            "prev_low": 9700,
            "prev_high": 10300,
            "sweep_type": "none",
            "reclaim_or_reject": "none",
            "sweep_level": None,
            "recent_sweep_valid": False,
        }
        msb = {
            "direction": "neutral",
            "leg_type": "SHORT",
            "quality": 10,
            "has_order_block_context": False,
            "structure_zone": (9800, 9900),
            "order_block_zone": (9700, 9900),
            "mid_observe_zone": (9850, 9950),
            "active_fvg_zone": (9700, 9900),
            "active_fvg_direction": "bull",
            "active_fvg_age": 1,
            "metrics": {},
        }
        htf = {"text": "4H 偏震荡", "relation": "neutral"}
        aux = {"momentum_desc": "动能 偏弱", "temperature_desc": "热度 偏冷", "price": 9750}
        return decide_key_zone_observation, klines, htf, liq, msb, {}, aux

    def test_fast_pullback_to_lower_key_zone_alerts(self):
        decide, klines, htf, liq, msb, matrix, aux = self._pullback_inputs()
        decision = decide(
            "BTCUSDT",
            "1h",
            klines,
            htf,
            liq,
            msb,
            matrix,
            aux,
            observation_state={"inside_zone": False},
        )

        self.assertTrue(decision["should_alert"])
        self.assertEqual(decision["alert_type"], "FAST_PULLBACK_OBSERVE")
        self.assertEqual(decision["direction"], "long")
        self.assertEqual(decision["zone_source"], "fvg_zone")

    def test_key_zone_cooldown_suppresses_only_unchanged_inside_zone(self):
        decide, klines, htf, liq, msb, matrix, aux = self._pullback_inputs()
        first = decide(
            "BTCUSDT",
            "1h",
            klines,
            htf,
            liq,
            msb,
            matrix,
            aux,
            observation_state={"inside_zone": False},
        )
        unchanged = decide(
            "BTCUSDT",
            "1h",
            klines,
            htf,
            liq,
            msb,
            matrix,
            aux,
            observation_state=first["observation_update"],
        )

        self.assertFalse(unchanged["should_alert"])
        self.assertEqual(unchanged["suppress_reason"], "pending_confirmation_wait")

        left_then_reentered_state = dict(first["observation_update"])
        left_then_reentered_state["inside_zone"] = False
        reentered = decide(
            "BTCUSDT",
            "1h",
            klines,
            htf,
            liq,
            msb,
            matrix,
            aux,
            observation_state=left_then_reentered_state,
        )

        self.assertFalse(reentered["should_alert"])
        self.assertEqual(reentered["suppress_reason"], "pending_confirmation_wait")


    def test_post_waterfall_same_cluster_waits_for_real_reaction(self):
        decide, klines, htf, liq, msb, matrix, aux = self._pullback_inputs()
        first = decide(
            "BTCUSDT",
            "1h",
            klines,
            htf,
            liq,
            msb,
            matrix,
            aux,
            observation_state={"inside_zone": False},
        )

        # Simulate the next hour still grinding around the same practical area.
        # The exact zone may drift, but the cluster is unchanged and there is no
        # reclaim/rejection upgrade, so this should not produce another passive
        # alert.
        next_state = dict(first["observation_update"])
        next_state["inside_zone"] = True
        next_state["last_phase"] = "lower_test"
        suppressed = decide(
            "BTCUSDT",
            "1h",
            klines,
            htf,
            liq,
            msb,
            matrix,
            aux,
            observation_state=next_state,
        )

        self.assertFalse(suppressed["should_alert"])
        self.assertIn(
            suppressed["suppress_reason"],
            {"post_impulse_waiting_for_reaction", "same_zone_no_new_reaction", "inside_zone_unchanged", "pending_confirmation_wait"},
        )

    def test_key_zone_message_does_not_leak_internal_terms(self):
        from engine.trend_messages import BANNED, format_trend_message

        decide, klines, htf, liq, msb, matrix, aux = self._pullback_inputs()
        decision = decide(
            "BTCUSDT",
            "1h",
            klines,
            htf,
            liq,
            msb,
            matrix,
            aux,
            observation_state={"inside_zone": False},
        )
        msg = format_trend_message(decision)

        self.assertTrue(msg.startswith("📍"))
        self.assertIn("BTC 1H 下方关键区观察", msg)
        for term in BANNED:
            self.assertNotIn(term, msg)



    def test_no_context_no_key_zone_alert(self):
        from engine.key_zones import decide_key_zone_observation

        klines = [self._bar(10000, 10050, 9950, 10000) for _ in range(25)]
        klines += [
            self._bar(10000, 10020, 9900, 9950),
            self._bar(9950, 9960, 9700, 9750),
        ]
        liq = {
            "prev_low": 9700,
            "prev_high": 10300,
            "sweep_type": "none",
            "reclaim_or_reject": "none",
            "sweep_level": None,
            "recent_sweep_valid": False,
        }
        msb = {
            "direction": "neutral",
            "leg_type": "SHORT",
            "quality": 10,
            "has_order_block_context": False,
            "structure_zone": (9800, 9900),
            "order_block_zone": (9700, 9900),
            "mid_observe_zone": (9850, 9950),
            "active_fvg_zone": None,
            "active_fvg_direction": "none",
            "metrics": {},
        }
        decision = decide_key_zone_observation(
            "BTCUSDT",
            "1h",
            klines,
            {"text": "4H 偏震荡", "relation": "neutral"},
            liq,
            msb,
            {},
            {"momentum_desc": "动能 偏弱", "temperature_desc": "热度 中性", "price": 9750},
            observation_state={"inside_zone": False},
        )

        self.assertFalse(decision["should_alert"])
        self.assertEqual(decision["suppress_reason"], "no_key_zone_touch")


    def test_upper_zone_rejection_message_is_not_plain_upper_test(self):
        from engine.key_zones import decide_key_zone_observation
        from engine.trend_messages import format_trend_message

        klines = [self._bar(10000, 10050, 9950, 10000) for _ in range(25)]
        klines += [
            self._bar(10100, 10200, 10080, 10150, atr=100.0),
            self._bar(10150, 10180, 10050, 10120, atr=100.0),
            # Touches the upper zone but closes below it with a fast selloff.
            self._bar(10120, 10140, 9750, 9800, atr=100.0),
        ]
        liq = {
            "prev_low": 9600,
            "prev_high": 10300,
            "sweep_type": "none",
            "reclaim_or_reject": "none",
            "sweep_level": None,
            "recent_sweep_valid": False,
        }
        msb = {
            "direction": "neutral",
            "leg_type": "SHORT",
            "quality": 10,
            "has_order_block_context": False,
            "structure_zone": (10000, 10120),
            "order_block_zone": (10000, 10120),
            "mid_observe_zone": (10000, 10120),
            "active_fvg_zone": (10000, 10120),
            "active_fvg_direction": "bear",
            "active_fvg_age": 1,
            "metrics": {},
        }
        decision = decide_key_zone_observation(
            "BTCUSDT",
            "1h",
            klines,
            {"text": "4H 偏震荡", "relation": "neutral"},
            liq,
            msb,
            {},
            {"momentum_desc": "动能 偏弱", "temperature_desc": "热度 过冷", "price": 9800},
            observation_state={"inside_zone": False},
        )

        self.assertTrue(decision["should_alert"])
        self.assertEqual(decision["alert_type"], "UPPER_KEY_ZONE_REJECTION")
        self.assertEqual(decision["direction"], "short")

        msg = format_trend_message(decision)
        self.assertTrue(msg.startswith("📉"))
        self.assertIn("BTC 1H 试空观察", msg)
        self.assertIn("试空观察条件", msg)
        self.assertIn("⚡ 动能与热度", msg)
        self.assertIn("✅ 结论", msg)

    def test_lower_zone_reclaim_message(self):
        from engine.key_zones import decide_key_zone_observation
        from engine.trend_messages import format_trend_message

        klines = [self._bar(10000, 10050, 9950, 10000) for _ in range(25)]
        klines += [
            self._bar(9900, 9950, 9800, 9850, atr=100.0),
            self._bar(9850, 9900, 9750, 9820, atr=100.0),
            # Sweeps/touches the lower zone and closes back above it.
            self._bar(9820, 10180, 9750, 10140, atr=100.0),
        ]
        liq = {
            "prev_low": 9700,
            "prev_high": 10300,
            "sweep_type": "none",
            "reclaim_or_reject": "none",
            "sweep_level": None,
            "recent_sweep_valid": False,
        }
        msb = {
            "direction": "neutral",
            "leg_type": "SHORT",
            "quality": 10,
            "has_order_block_context": False,
            "structure_zone": (9850, 10050),
            "order_block_zone": (9850, 10050),
            "mid_observe_zone": (9850, 10050),
            "active_fvg_zone": (9850, 10050),
            "active_fvg_direction": "bull",
            "active_fvg_age": 1,
            "metrics": {},
        }
        decision = decide_key_zone_observation(
            "BTCUSDT",
            "1h",
            klines,
            {"text": "4H 偏震荡", "relation": "neutral"},
            liq,
            msb,
            {},
            {"momentum_desc": "动能 偏强", "temperature_desc": "热度 中性", "price": 10140},
            observation_state={"inside_zone": False},
        )

        self.assertTrue(decision["should_alert"])
        self.assertEqual(decision["alert_type"], "LOWER_KEY_ZONE_RECLAIM")
        self.assertEqual(decision["direction"], "long")

        msg = format_trend_message(decision)
        self.assertTrue(msg.startswith("📈"))
        self.assertIn("BTC 1H 试多观察", msg)
        self.assertIn("⚡ 动能与热度", msg)

    def test_lower_zone_reclaim_uses_signal_title(self):
        from engine.key_zones import decide_key_zone_observation
        from engine.trend_messages import format_trend_message

        klines = [self._bar(10000, 10050, 9950, 10000) for _ in range(25)]
        klines += [
            self._bar(9900, 9950, 9800, 9850, atr=100.0),
            self._bar(9850, 9900, 9750, 9820, atr=100.0),
            self._bar(9820, 10180, 9750, 10140, atr=100.0),
        ]
        liq = {"prev_low": 9700, "prev_high": 10300, "sweep_type": "none", "reclaim_or_reject": "none", "sweep_level": None, "recent_sweep_valid": False}
        msb = {
            "direction": "neutral",
            "leg_type": "SHORT",
            "quality": 10,
            "has_order_block_context": False,
            "structure_zone": (9850, 10050),
            "order_block_zone": (9850, 10050),
            "mid_observe_zone": (9850, 10050),
            "active_fvg_zone": (9850, 10050),
            "active_fvg_direction": "bull",
            "active_fvg_age": 1,
            "metrics": {},
        }
        decision = decide_key_zone_observation(
            "BTCUSDT",
            "1h",
            klines,
            {"text": "4H 偏震荡", "relation": "neutral"},
            liq,
            msb,
            {},
            {"momentum_desc": "动能 偏强", "temperature_desc": "热度 中性", "price": 10140},
            observation_state={"inside_zone": False},
        )
        msg = format_trend_message(decision)
        first_line = msg.splitlines()[0]
        self.assertEqual(first_line, "📈 BTC 1H 试多观察 📈")

    def test_pending_confirmation_silences_middle_and_alerts_confirmation(self):
        from engine.key_zones import decide_key_zone_observation

        decide, klines, htf, liq, msb, matrix, aux = self._pullback_inputs()
        first = decide(
            "BTCUSDT",
            "1h",
            klines,
            htf,
            liq,
            msb,
            matrix,
            aux,
            observation_state={"inside_zone": False},
        )
        self.assertTrue(first["should_alert"])
        self.assertTrue(first["observation_update"].get("pending_confirm"))

        # Same closed candle: no "pending" Telegram message, just silent tracking.
        middle = decide(
            "BTCUSDT",
            "1h",
            klines,
            htf,
            liq,
            msb,
            matrix,
            aux,
            observation_state=first["observation_update"],
        )
        self.assertFalse(middle["should_alert"])
        self.assertEqual(middle["suppress_reason"], "pending_confirmation_wait")

        # Next bar: retests the first zone and closes back above its midpoint.
        confirm_klines = list(klines)
        confirm_klines.append(self._bar(9760, 9920, 9760, 9895, atr=100.0))
        confirmed = decide(
            "BTCUSDT",
            "1h",
            confirm_klines,
            htf,
            liq,
            msb,
            matrix,
            {"momentum_desc": "短线动能修复", "temperature_desc": "热度 中性", "price": 9895},
            observation_state=first["observation_update"],
        )

        self.assertTrue(confirmed["should_alert"])
        self.assertEqual(confirmed["alert_type"], "SECONDARY_CONFIRM_LOWER")

    def test_secondary_confirmation_message(self):
        from engine.trend_messages import format_trend_message

        msg = format_trend_message(
            {
                "direction": "long",
                "alert_type": "SECONDARY_CONFIRM_LOWER",
                "zone": (9700.0, 9900.0),
                "htf_context": "4H 偏震荡",
                "momentum_desc": "短线动能修复",
                "temperature_desc": "热度 中性",
                "invalid_level": 9690.0,
            }
        )
        self.assertTrue(msg.startswith("✅ BTC 1H 二次确认：承接成立 ✅"))
        self.assertIn("⚠️ 风险位", msg)
        self.assertIn("承接确认失效", msg)
        self.assertNotIn("📌 状态", msg)
        self.assertNotIn("✅ 结论", msg)


    def test_scanner_health_compatibility_methods_exist(self):
        from engine.scanner import SMCTScanner

        with patch("engine.scanner.get_logger", return_value=Mock()):
            scanner = SMCTScanner("BTCUSDT")

        self.assertTrue(scanner.health_check()["ok"])
        self.assertTrue(scanner.healthcheck()["ok"])



class AuxFilterCalibrationTests(unittest.TestCase):
    @staticmethod
    def _bar(close: float, rar: float, tai: float, atr: float = 100.0, volume: float = 10000.0) -> dict:
        return {
            "open": close,
            "high": close + 50,
            "low": close - 50,
            "close": close,
            "volume": volume,
            "ema10": close + 1,
            "ema20": close,
            "rar_value": rar,
            "tai_value": tai,
            "tai_p20": 19.5,
            "tai_p40": 19.7,
            "tai_p60": 19.9,
            "tai_p80": 20.1,
            "inertia": 50.0,
            "atr": atr,
        }

    def test_tai_uses_visible_p20_p40_p60_p80_bands(self):
        from engine.aux_filters import build_aux_filters_proxy

        klines = [self._bar(10000 + i, rar=45 + (i % 5), tai=19.8) for i in range(71)]

        # 19.86 is between P40=19.7 and P60=19.9, so it is neutral,
        # not cold/over-cold.  Below P20 is the only over-cold region.
        klines.append(self._bar(10080, rar=48, tai=19.86))
        aux = build_aux_filters_proxy(klines, klines[-4:])

        self.assertEqual(aux["temperature_desc"], "热度 中性")
        self.assertEqual(aux["tai_percentile"], 0.50)

        klines[-1] = self._bar(10080, rar=48, tai=19.49)
        aux_cold = build_aux_filters_proxy(klines, klines[-4:])
        self.assertEqual(aux_cold["temperature_desc"], "热度 过冷")

    def test_momentum_detects_sell_pressure_release_from_price_and_rar_slope(self):
        from engine.aux_filters import build_aux_filters_proxy

        klines = [
            self._bar(10300, rar=50, tai=19.8),
            self._bar(10250, rar=49, tai=19.8),
            self._bar(10100, rar=47, tai=19.8),
            self._bar(9900, rar=44, tai=19.8, volume=15000.0),
        ]
        # Add enough TAI history for the percentile path.
        klines = [self._bar(10000 + i, rar=50, tai=19.5 + (i % 6) * 0.05) for i in range(68)] + klines

        aux = build_aux_filters_proxy(klines, klines[-4:])
        self.assertEqual(aux["momentum_desc"], "短线卖压释放")
        self.assertLess(aux["rar_slope"], 0)
        self.assertLess(aux["price_impulse"], 0)


class NoMacdAndTrueTaiTests(unittest.TestCase):
    @staticmethod
    def _tai_bar(close: float, volume: float, rar: float = 50.0, inertia: float = 50.0) -> dict:
        return {
            "open": close,
            "high": close + 10,
            "low": close - 10,
            "close": close,
            "volume": volume,
            "ema10": close + 1,
            "ema20": close,
            "rar_value": rar,
            "inertia": inertia,
            "atr": 100.0,
        }

    def test_aux_filter_outputs_no_macd_field(self):
        from engine.aux_filters import build_aux_filters_proxy

        klines = [self._tai_bar(10000.0, 1000.0 + i * 10.0) for i in range(300)]
        aux = build_aux_filters_proxy(klines, klines[-4:])

        self.assertNotIn("macd", aux)
        self.assertIn("tai_value", aux)
        self.assertIn("tai_p20", aux)
        self.assertEqual(aux["temperature_desc"], "热度 过热")

    def test_tai_uses_dollar_volume_percentile_bands_when_tv_fields_absent(self):
        from engine.aux_filters import build_aux_filters_proxy

        klines = [self._tai_bar(10000.0, 1000.0 + i * 10.0) for i in range(300)]
        aux = build_aux_filters_proxy(klines, klines[-4:])

        self.assertGreater(aux["tai_value"], aux["tai_p80"])
        self.assertEqual(aux["temperature_desc"], "热度 过热")

    def test_sweep_alone_without_fvg_or_structure_context_does_not_observe_range_edge(self):
        from engine.key_zones import decide_key_zone_observation

        klines = [
            {"open": 10000.0, "high": 10050.0, "low": 9950.0, "close": 10000.0, "volume": 1000.0, "atr": 100.0}
            for _ in range(30)
        ]
        klines[-1] = {"open": 10000.0, "high": 10020.0, "low": 9700.0, "close": 9750.0, "volume": 2000.0, "atr": 100.0}
        liq = {
            "prev_low": 9700.0,
            "prev_high": 10300.0,
            "sweep_type": "sellside",
            "reclaim_or_reject": "reclaim",
            "sweep_level": 9700.0,
            "recent_sweep_valid": True,
        }
        msb = {
            "direction": "neutral",
            "leg_type": "SHORT",
            "quality": 10,
            "has_order_block_context": False,
            "structure_zone": (9800.0, 9900.0),
            "order_block_zone": (9700.0, 9900.0),
            "mid_observe_zone": (9850.0, 9950.0),
            "active_fvg_zone": None,
            "active_fvg_direction": "none",
            "metrics": {},
        }

        decision = decide_key_zone_observation(
            "BTCUSDT",
            "1h",
            klines,
            {"text": "4H 偏震荡", "relation": "neutral"},
            liq,
            msb,
            {},
            {"momentum_desc": "短线卖压释放", "temperature_desc": "热度 中性", "price": 9750.0},
            observation_state={"inside_zone": False},
        )

        self.assertFalse(decision["should_alert"])
        self.assertEqual(decision["suppress_reason"], "no_key_zone_touch")


class FifteenMinutePrealertTests(unittest.TestCase):
    @staticmethod
    def _bar(close: float, open_: float | None = None, high: float | None = None, low: float | None = None, t: int = 0) -> dict:
        open_ = close if open_ is None else open_
        high = max(open_, close) + 20.0 if high is None else high
        low = min(open_, close) - 20.0 if low is None else low
        return {
            "open_time": t,
            "close_time": t + 899999,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": 1000.0,
            "atr": 100.0,
            "ema10": close,
            "ema20": close,
            "rar_value": 45.0,
            "rar_trigger": 50.0,
            "tai_value": 20.5,
            "tai_p20": 19.5,
            "tai_p40": 20.0,
            "tai_p60": 20.3,
            "tai_p80": 20.7,
        }

    def test_15m_short_prealert_title_and_direction(self):
        from engine.prealert_15m import PrealertConfig, evaluate_15m_prealert

        k15 = [self._bar(10000.0, t=i * 900000) for i in range(97)]
        k15.append(self._bar(10080.0, open_=10020.0, high=10120.0, low=10010.0, t=97 * 900000))
        k15.append(self._bar(10030.0, open_=10090.0, high=10110.0, low=10020.0, t=98 * 900000))
        k1h = [self._bar(10000.0, t=i * 3600000) for i in range(100)]
        k4h = [self._bar(10000.0, t=i * 14400000) for i in range(30)]

        with patch("engine.prealert_15m._candidate_zones", return_value=[{"zone": (10000.0, 10100.0), "source": "test_zone", "priority": 3}]):
            decision = evaluate_15m_prealert("BTCUSDT", k15, k1h, k4h, cfg=PrealertConfig(max_risk_pct=0.02, min_risk_reward_room=0.001))

        self.assertTrue(decision["should_alert"])
        self.assertEqual(decision["alert_type"], "PREALERT_SHORT")
        self.assertEqual(decision["title"], "📍 BTC 15m 做空预警")

    def test_15m_prealert_silent_without_nearby_zone_reaction(self):
        from engine.prealert_15m import evaluate_15m_prealert

        k15 = [self._bar(10000.0, t=i * 900000) for i in range(100)]
        k1h = [self._bar(10000.0, t=i * 3600000) for i in range(100)]
        k4h = [self._bar(10000.0, t=i * 14400000) for i in range(30)]

        with patch("engine.prealert_15m._candidate_zones", return_value=[{"zone": (10500.0, 10600.0), "source": "test_zone", "priority": 3}]):
            decision = evaluate_15m_prealert("BTCUSDT", k15, k1h, k4h)

        self.assertFalse(decision["should_alert"])
        self.assertEqual(decision["alert_type"], "NO_15M_PREALERT")


    def test_15m_prealert_suppresses_late_15m_bar(self):
        from engine.prealert_15m import evaluate_15m_prealert

        k15 = [self._bar(10000.0, t=i * 900000) for i in range(98)]
        k15.append(self._bar(10080.0, open_=10020.0, high=10120.0, low=10010.0, t=98 * 900000))
        k15.append(self._bar(10030.0, open_=10090.0, high=10110.0, low=10020.0, t=99 * 900000))
        k1h = [self._bar(10000.0, t=i * 3600000) for i in range(100)]
        k4h = [self._bar(10000.0, t=i * 14400000) for i in range(30)]

        with patch("engine.prealert_15m._candidate_zones", return_value=[{"zone": (10000.0, 10100.0), "source": "test_zone", "priority": 3}]):
            decision = evaluate_15m_prealert("BTCUSDT", k15, k1h, k4h)

        self.assertFalse(decision["should_alert"])
        self.assertEqual(decision["suppress_reason"], "too_close_to_1h_close")


class AlertNatureCleanupTests(unittest.TestCase):
    def test_prealert_message_is_separate_from_1h_confirmation(self):
        from engine.trend_messages import format_prealert_message

        msg = format_prealert_message(
            {
                "title": "📍 BTC 15m 做空预警",
                "direction": "short",
                "zone": (100.0, 110.0),
                "htf_context": "4H 震荡",
                "momentum_desc": "短线买盘衰减",
                "temperature_desc": "热度 偏热",
                "invalid_level": 111.0,
            }
        )

        self.assertTrue(msg.startswith("📍 BTC 15m 做空预警"))
        self.assertIn("这不是 1H 正式单", msg)
        self.assertIn("仅作为入场位置提醒", msg)
        self.assertNotIn("空头确认", msg)
        self.assertNotIn("✅ 结论", msg)

    def test_late_filter_suppresses_rebounding_short_confirmation(self):
        from engine.late_filter import apply_late_filter

        decision = {
            "alert_type": "SECONDARY_CONFIRM_UPPER",
            "direction": "short",
            "should_alert": True,
            "zone": (100.0, 110.0),
            "score_breakdown": {},
        }
        klines = [
            {"open": 108.0, "high": 109.0, "low": 101.0, "close": 102.0, "atr": 2.0},
            {"open": 101.0, "high": 104.0, "low": 99.0, "close": 103.0, "atr": 2.0},
        ]

        filtered = apply_late_filter(decision, klines)

        self.assertFalse(filtered["should_alert"])
        self.assertEqual(filtered["suppress_reason"], "late_confirm_rebound_against_short")

    def test_hot_long_prealert_is_suppressed_after_shadow_backtest(self):
        from engine.prealert_15m import PrealertConfig, evaluate_15m_prealert

        def bar(close, open_=None, high=None, low=None, t=0, tai=20.8, rar=55.0, trigger=50.0):
            open_ = close if open_ is None else open_
            high = max(open_, close) + 20.0 if high is None else high
            low = min(open_, close) - 20.0 if low is None else low
            return {
                "open_time": t,
                "close_time": t + 899999,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": 1000.0,
                "atr": 100.0,
                "ema10": close,
                "ema20": close,
                "rar_value": rar,
                "rar_trigger": trigger,
                "tai_value": tai,
                "tai_p20": 19.5,
                "tai_p40": 20.0,
                "tai_p60": 20.3,
                "tai_p80": 20.7,
            }

        k15 = [bar(10000.0, t=i * 900000) for i in range(98)]
        k15.append(bar(10020.0, open_=10080.0, high=10090.0, low=9950.0, t=98 * 900000, tai=20.8, rar=48.0))
        k15.append(bar(10070.0, open_=10010.0, high=10090.0, low=9960.0, t=99 * 900000, tai=20.8, rar=56.0))
        k1h = [bar(10000.0, t=i * 3600000) for i in range(100)]
        k4h = [bar(10000.0, t=i * 14400000) for i in range(30)]

        with patch("engine.prealert_15m._candidate_zones", return_value=[{"zone": (9960.0, 10100.0), "source": "test_zone", "priority": 3}]):
            decision = evaluate_15m_prealert("BTCUSDT", k15, k1h, k4h, cfg=PrealertConfig(max_risk_pct=0.02))

        self.assertFalse(decision["should_alert"])

class PrealertCadenceTests(unittest.TestCase):
    def test_high_quality_new_information_uses_fast_cooldown(self):
        from engine.prealert_15m import PrealertConfig, cooldown_bars_for_decision, is_high_quality_new_information

        cfg = PrealertConfig(cooldown_bars=16, fast_cooldown_bars=8, high_quality_score=13)
        decision = {
            "trigger_score": 13,
            "liquidity_event": "sweep_high_reject",
            "reaction_type": "sweep_high_reject",
            "key_level_context": "整数位 81000.0 distance=0.050% reaction=key_reject",
        }

        self.assertTrue(is_high_quality_new_information(decision, cfg))
        self.assertEqual(cooldown_bars_for_decision(decision, cfg), 8)

    def test_ordinary_zone_reaction_uses_normal_cooldown(self):
        from engine.prealert_15m import PrealertConfig, cooldown_bars_for_decision, is_high_quality_new_information

        cfg = PrealertConfig(cooldown_bars=16, fast_cooldown_bars=8, high_quality_score=13)
        decision = {
            "trigger_score": 10,
            "liquidity_event": "zone_reaction_without_local_sweep",
            "reaction_type": "upper_reject",
            "key_level_context": "none",
        }

        self.assertFalse(is_high_quality_new_information(decision, cfg))
        self.assertEqual(cooldown_bars_for_decision(decision, cfg), 16)
