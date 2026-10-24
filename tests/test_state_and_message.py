import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


def _ifvg_evidence(zone, *, bull: bool = True) -> dict:
    """Build evidence.ifvg for tests after MSB/ICT hard-delete."""
    low, high = min(zone), max(zone)
    return {
        "ifvg": {
            "nearest_active": {
                "top": high,
                "bottom": low,
                "direction": 1 if bull else -1,
                "inverted": False,
                "invalidated": False,
            },
            "zones": [],
            "approx": True,
        }
    }



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
        self.assertIn("🧭 4H 偏多", msg)
        self.assertNotIn("🗺 框架", msg)
        self.assertIn("📍 开单建议 📍", msg)
        self.assertIn("区间 100.00 - 110.00。", msg)
        self.assertIn("止盈目标 120.00 - 130.00。", msg)
        self.assertNotIn("不追价。", msg)
        self.assertNotIn("1H 定方向与区位", msg)
        self.assertIn("📌 关注点", msg)
        self.assertIn("跌破 99.00 → 本观察作废，等新结构。", msg)
        self.assertIn("严格按关注点管理。", msg)
        self.assertNotIn("动能与热度", msg)
        self.assertNotIn("守住风险位", msg)

    def test_banned_terms_no_leak(self):
        from engine.trend_messages import format_trend_message

        msg = format_trend_message(self._decision("long", "BULLISH_STRUCTURE_SHIFT"))
        for term in ["liquidity", "MSB", "OB", "SMC", "ICT", "RAR", "TAI", "FVG", "IFVG", "Heatmap", "热力图", "流动性", "订单块"]:
            self.assertNotIn(term.lower(), msg.lower())

    def test_zone_note_is_short_and_without_usage_label(self):
        from engine.trend_messages import format_trend_message

        msg = format_trend_message(self._decision("long", "LOWER_KEY_ZONE_RECLAIM"))
        self.assertIn("区间 100.00 - 110.00。", msg)
        self.assertIn("止盈目标 120.00 - 130.00。", msg)
        self.assertIn("📍 开单建议 📍", msg)
        self.assertIn("📌 关注点", msg)
        self.assertNotIn("用途：", msg)
        self.assertNotIn("下方承接观察区", msg)

    def test_upper_rejection_zone_note(self):
        from engine.trend_messages import format_trend_message

        msg = format_trend_message(self._decision("short", "UPPER_KEY_ZONE_REJECTION"))
        self.assertIn("区间 100.00 - 110.00。", msg)
        self.assertIn("止盈目标 80.00 - 90.00。", msg)
        self.assertIn("🧭 4H 偏空", msg)
        self.assertNotIn("不追空。", msg)
        self.assertNotIn("1H 定方向与区位", msg)
        self.assertIn("站回 111.00 → 本观察作废，等新结构。", msg)
        self.assertNotIn("用途：", msg)
        self.assertNotIn("上方承压观察区", msg)


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
        self.assertEqual(decision["zone_source"], "ifvg_zone")

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
        self.assertEqual(unchanged["suppress_reason"], "inside_zone_unchanged")

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
        self.assertEqual(reentered["suppress_reason"], "post_impulse_waiting_for_reaction")


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
            # Touches the upper zone and rejects while price is still close
            # enough to the risk area to be actionable.
            self._bar(10080, 10140, 9950, 9990, atr=100.0),
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
            {"momentum_desc": "动能 偏弱", "temperature_desc": "热度 中性", "price": 9990, "rar_slope": -1.0},
            evidence_bundle=_ifvg_evidence((10000, 10120), bull=False),
            observation_state={"inside_zone": False},
        )

        self.assertTrue(decision["should_alert"])
        self.assertEqual(decision["alert_type"], "UPPER_KEY_ZONE_REJECTION")
        self.assertEqual(decision["direction"], "short")

        msg = format_trend_message(decision)
        self.assertTrue(msg.startswith("📉"))
        self.assertIn("BTC 1H 试空观察", msg)
        self.assertIn("试空观察条件", msg)
        self.assertIn("📍 开单建议 📍", msg)
        self.assertIn("止盈目标", msg)
        self.assertIn("🧭 4H", msg)
        self.assertIn("📌 关注点", msg)
        self.assertIn("✅ 结论", msg)
        self.assertNotIn("动能与热度", msg)
        self.assertNotIn("不追空", msg)
        self.assertIn("take_profit_zone", decision)

    def test_lower_zone_reclaim_message(self):
        from engine.key_zones import decide_key_zone_observation
        from engine.trend_messages import format_trend_message

        klines = [self._bar(10000, 10050, 9950, 10000) for _ in range(25)]
        klines += [
            self._bar(9900, 9970, 9900, 9950, atr=100.0),
            self._bar(9850, 9970, 9900, 9950, atr=100.0),
            # Sweeps/touches the lower zone and closes back above it.
            self._bar(9990, 10090, 9940, 10045, atr=100.0),
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
            "active_fvg_zone": (9950, 10020),
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
            evidence_bundle=_ifvg_evidence((9950, 10020), bull=True),
            observation_state={"inside_zone": False},
        )

        self.assertTrue(decision["should_alert"])
        self.assertEqual(decision["alert_type"], "LOWER_KEY_ZONE_RECLAIM")
        self.assertEqual(decision["direction"], "long")

        msg = format_trend_message(decision)
        self.assertTrue(msg.startswith("📈"))
        self.assertIn("BTC 1H 试多观察", msg)
        self.assertIn("📍 开单建议 📍", msg)
        self.assertIn("📌 关注点", msg)
        self.assertNotIn("动能与热度", msg)

    def test_formal_lower_reclaim_creates_pending_confirmation(self):
        from engine.key_zones import decide_key_zone_observation

        klines = [self._bar(10000, 10050, 9950, 10000) for _ in range(25)]
        klines += [
            self._bar(9900, 9970, 9900, 9950, atr=100.0),
            self._bar(9850, 9970, 9900, 9950, atr=100.0),
            self._bar(9990, 10090, 9940, 10045, atr=100.0),
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
            "active_fvg_zone": (9950, 10020),
            "active_fvg_direction": "bull",
            "active_fvg_age": 1,
            "metrics": {},
        }
        decision = decide_key_zone_observation(
            "BTCUSDT",
            "1h",
            klines,
            {"text": "4H 震荡", "relation": "neutral"},
            liq,
            msb,
            {},
            {"momentum_desc": "动能 偏强", "temperature_desc": "热度 中性", "price": 10140},
            observation_state={"inside_zone": False},
        )

        self.assertTrue(decision["should_alert"])
        self.assertEqual(decision["alert_type"], "LOWER_KEY_ZONE_RECLAIM")
        self.assertTrue(decision["observation_update"].get("pending_confirm"))


    def test_lower_zone_reclaim_uses_signal_title(self):
        from engine.key_zones import decide_key_zone_observation
        from engine.trend_messages import format_trend_message

        klines = [self._bar(10000, 10050, 9950, 10000) for _ in range(25)]
        klines += [
            self._bar(9900, 9970, 9900, 9950, atr=100.0),
            self._bar(9850, 9970, 9900, 9950, atr=100.0),
            self._bar(9990, 10090, 9940, 10045, atr=100.0),
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
            "active_fvg_zone": (9950, 10020),
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

    def test_range_lock_suppresses_same_box_passive_noise(self):
        decide, klines, htf, liq, msb, matrix, aux = self._pullback_inputs()
        current_bar = len(klines)
        decision = decide(
            "BTCUSDT",
            "1h",
            klines,
            htf,
            liq,
            msb,
            matrix,
            aux,
            observation_state={
                "inside_zone": False,
                "range_lock_cluster": "box-a",
                "range_lock_last_alert_open_time": current_bar - 2,
            },
            range_lock={"active": True, "cluster": "box-a", "box_low": 9600.0, "box_high": 10200.0},
        )

        self.assertFalse(decision["should_alert"])
        self.assertEqual(decision["suppress_reason"], "range_lock_same_box_cooldown")
        self.assertTrue(decision["range_lock_active"])

    def test_range_box_allows_weighted_long_without_breakout(self):
        from engine.key_zones import decide_key_zone_observation

        klines = [self._bar(10000, 10050, 9950, 10000) for _ in range(25)]
        klines += [
            self._bar(10000, 10040, 9950, 10020, atr=100.0),
            self._bar(10020, 10030, 9850, 9900, atr=100.0),
            self._bar(9800, 9860, 9720, 9820, atr=100.0),
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
            "active_fvg_zone": (9700.0, 9850.0),
            "active_fvg_direction": "bull",
            "active_fvg_age": 1,
            "metrics": {},
            "fibonacci": {},
        }
        decision = decide_key_zone_observation(
            "BTCUSDT",
            "1h",
            klines,
            {"text": "4H 震荡", "relation": "neutral"},
            liq,
            msb,
            {},
            {
                "momentum_desc": "短线动能修复",
                "temperature_desc": "热度 中性",
                "price": 9820,
                "rar_slope": 2.0,
                "inertia_slope": 2.0,
                "inertia_turn_up": True,
                "rar_above_trigger": True,
                "volume_ratio": 1.0,
            },
            observation_state={"inside_zone": False},
            range_lock={"active": True, "cluster": "box-b", "box_low": 9700.0, "box_high": 10200.0},
            evidence_bundle=_ifvg_evidence((9700.0, 9850.0), bull=True),
        )

        self.assertTrue(decision["should_alert"])
        self.assertIn(decision["alert_type"], {"EARLY_LONG_TRIAL", "LOWER_KEY_ZONE_RECLAIM"})
        self.assertTrue(decision["observation_update"].get("pending_confirm"))
        self.assertEqual(decision["market_phase"], "range_bullish")
        self.assertTrue(decision["range_lock_active"])


    def test_pending_confirmation_silences_middle_and_alerts_confirmation(self):
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
        # Single-emoji passive observations must not create a formal second-confirmation state.
        self.assertFalse(first["observation_update"].get("pending_confirm"))

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
        self.assertEqual(middle["suppress_reason"], "inside_zone_unchanged")

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

    def test_1h_aux_peels_formation_temperature_and_exposes_core_levels(self):
        from engine.aux_filters import build_aux_filters_proxy

        klines = [self._bar(10000 + i, rar=45 + (i % 5), tai=19.8) for i in range(71)]
        klines.append(self._bar(10080, rar=48, tai=19.86))
        aux = build_aux_filters_proxy(klines, klines[-4:])

        # Formation/participation shadow is 15m-only; 1H aux stays neutral heat.
        self.assertEqual(aux["temperature_desc"], "热度 中性")
        self.assertIsNone(aux["tai_percentile"])
        self.assertFalse(aux.get("formation_shadow_1h"))
        self.assertIn("core_levels_filter", aux)
        self.assertTrue(aux["core_levels_filter"].get("filter_only"))
        self.assertFalse(aux["core_levels_filter"].get("should_alert"))

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
        self.assertEqual(aux["temperature_desc"], "热度 中性")
        self.assertEqual(aux["inertia_source"], "peeled")

    def test_formation_shadow_uses_dollar_volume_percentile_bands_on_15m(self):
        from engine.formation_shadow import build_formation_shadow

        klines = [self._tai_bar(10000.0, 1000.0 + i * 10.0) for i in range(300)]
        shadow = build_formation_shadow(klines, timeframe="15m")

        self.assertEqual(shadow["reason"], "ok")
        self.assertTrue(shadow["shadow_only"])
        self.assertFalse(shadow["should_alert"])
        self.assertGreater(shadow["value"], shadow["p80"])
        self.assertEqual(shadow["regime"], "very_warm")

        blocked = build_formation_shadow(klines, timeframe="1h")
        self.assertFalse(blocked["allowed"])
        self.assertEqual(blocked["reason"], "timeframe_not_allowed")

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
        self.assertEqual(decision["title"], "📍 BTC 15m 做空🔴位置提醒")

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
                "title": "📍 BTC 15m 做空🔴位置提醒",
                "direction": "short",
                "zone": (100.0, 110.0),
                "htf_context": "4H 震荡",
                "momentum_desc": "短线买盘衰减",
                "temperature_desc": "热度 偏热",
                "invalid_level": 111.0,
            }
        )

        self.assertTrue(msg.startswith("📍 BTC 15m 做空🔴位置提醒"))
        self.assertIn("15m 出现可能的做空🔴位置。", msg)
        self.assertIn("这不是 1H 正式单", msg)
        self.assertIn("仅作为入场位置提醒", msg)
        self.assertNotIn("预警", msg)
        self.assertNotIn("做多📈", msg)
        self.assertNotIn("做空📉", msg)
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


class V139LayeredDecisionTests(unittest.TestCase):
    @staticmethod
    def _bar(open_: float, high: float, low: float, close: float, atr: float = 100.0, open_time: int | None = None) -> dict:
        bar = {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": 1000.0,
            "atr": atr,
            "ema10": close,
            "ema20": close,
            "rar_value": 50.0,
            "rar_trigger": 50.0,
            "inertia": 50.0,
        }
        if open_time is not None:
            bar["open_time"] = open_time
        return bar

    @staticmethod
    def _neutral_liq() -> dict:
        return {
            "prev_low": 9700.0,
            "prev_high": 10300.0,
            "sweep_type": "none",
            "reclaim_or_reject": "none",
            "sweep_level": None,
            "recent_sweep_valid": False,
        }

    @staticmethod
    def _bull_fvg_msb() -> dict:
        return {
            "direction": "neutral",
            "leg_type": "SHORT",
            "quality": 10,
            "has_order_block_context": False,
            "structure_zone": (9950.0, 10020.0),
            "order_block_zone": (9950.0, 10020.0),
            "mid_observe_zone": (9950.0, 10020.0),
            "active_fvg_zone": (9950.0, 10020.0),
            "active_fvg_direction": "bull",
            "active_fvg_age": 1,
            "metrics": {},
        }




    def test_late_long_at_reference_box_upper_edge_is_blocked(self):
        from engine.trial_decision import assess_trial_candidate, build_trial_context

        bars = [self._bar(10000, 10050, 9950, 10000) for _ in range(24)]
        latest = self._bar(10150, 10210, 10120, 10180)
        bars.append(latest)
        context = build_trial_context(
            bars,
            {"text": "4H 偏多", "h4_direction": "bull", "relation": "aligned"},
            self._neutral_liq(),
            self._bull_fvg_msb(),
            {"matrix_direction": "bull"},
            {"momentum_desc": "短线动能偏强", "rar_slope": 1.0, "inertia_slope": 1.0},
            range_lock={"active": False, "box_low": 9700.0, "box_high": 10200.0, "accepted_breakout": "none"},
            ict={"bullish_active": True, "bearish_active": False, "bullish_distance_atr": 1.5},
        )
        assessment = assess_trial_candidate(
            "long",
            "LOWER_KEY_ZONE_RECLAIM",
            (10000.0, 10150.0),
            9950.0,
            latest,
            10000.0,
            "ifvg_zone",
            "reclaimed_above",
            context,
        )

        self.assertFalse(assessment["allow_formal"])
        self.assertIn("wrong_range_edge", assessment["hard_blocks"])

    def test_same_box_opposite_trial_needs_new_structure_information(self):
        from engine.trial_decision import assess_trial_candidate, build_trial_context

        bars = [self._bar(10000, 10180, 9820, 10000) for _ in range(24)]
        latest = self._bar(10180, 10210, 10120, 10150)
        bars.append(latest)
        context = build_trial_context(
            bars,
            {"text": "4H 震荡", "relation": "neutral"},
            self._neutral_liq(),
            {**self._bull_fvg_msb(), "active_fvg_direction": "bear"},
            {"matrix_direction": "bear"},
            {
                "momentum_desc": "短线动能转弱",
                "rar_slope": -2.0,
                "inertia_slope": -2.0,
                "inertia_turn_down": True,
                "rar_above_trigger": False,
            },
            range_lock={"active": True, "cluster": "box-current", "box_low": 9700.0, "box_high": 10200.0},
            ict={
                "bullish_active": True,
                "bearish_active": True,
                "coexist": True,
                "bullish_distance_atr": 4.0,
                "bearish_distance_atr": 0.0,
            },
        )
        assessment = assess_trial_candidate(
            "short",
            "UPPER_KEY_ZONE_REJECTION",
            (10100.0, 10200.0),
            10220.0,
            latest,
            10000.0,
            "ict_minus_ob",
            "rejected_below",
            context,
            observation_state={
                "last_formal_side": "lower",
                "last_formal_open_time": 100,
                "last_formal_box_low": 9720.0,
                "last_formal_box_high": 10220.0,
            },
            current_bar=104,
        )

        self.assertFalse(assessment["allow_formal"])
        self.assertIn("same_box_opposite_flip_without_new_information", assessment["hard_blocks"])

    def test_secondary_confirmation_requires_a_real_push(self):
        from engine.key_zones import decide_key_zone_observation

        bars = [self._bar(10000, 10050, 9950, 10000, open_time=i) for i in range(28)]
        bars.append(self._bar(10045, 10065, 10020, 10050, open_time=28))
        state = {
            "pending_confirm": True,
            "pending_side": "lower",
            "pending_zone_low": 9950.0,
            "pending_zone_high": 10020.0,
            "pending_invalid_level": 9940.0,
            "pending_created_open_time": 27,
            "pending_source_alert_type": "LOWER_KEY_ZONE_RECLAIM",
            "pending_phase": "lower_reclaim",
            "pending_zone_cluster": "lower|structural|50",
            "pending_source_price": 10045.0,
            "pending_source_score": 9.0,
        }
        decision = decide_key_zone_observation(
            "BTCUSDT",
            "1h",
            bars,
            {"text": "4H 震荡", "relation": "neutral"},
            self._neutral_liq(),
            self._bull_fvg_msb(),
            {"matrix_direction": "bull"},
            {"momentum_desc": "短线动能偏强", "rar_slope": 1.0, "inertia_slope": 1.0},
            observation_state=state,
        )

        self.assertFalse(decision["should_alert"])
        self.assertEqual(decision["suppress_reason"], "secondary_no_valid_push")
        self.assertTrue(decision["observation_update"]["pending_confirm"])

    def test_secondary_confirmation_revalidates_and_can_pass(self):
        from engine.key_zones import decide_key_zone_observation

        bars = [self._bar(10000, 10050, 9950, 10000, open_time=i) for i in range(28)]
        bars.append(self._bar(10050, 10095, 10030, 10080, open_time=28))
        state = {
            "pending_confirm": True,
            "pending_side": "lower",
            "pending_zone_low": 9950.0,
            "pending_zone_high": 10020.0,
            "pending_invalid_level": 9940.0,
            "pending_created_open_time": 27,
            "pending_source_alert_type": "LOWER_KEY_ZONE_RECLAIM",
            "pending_phase": "lower_reclaim",
            "pending_zone_cluster": "lower|structural|50",
            "pending_source_price": 10045.0,
            "pending_source_score": 9.0,
        }
        decision = decide_key_zone_observation(
            "BTCUSDT",
            "1h",
            bars,
            {"text": "4H 偏多", "h4_direction": "bull", "relation": "aligned"},
            self._neutral_liq(),
            self._bull_fvg_msb(),
            {"matrix_direction": "bull"},
            {
                "momentum_desc": "短线动能偏强",
                "rar_slope": 1.0,
                "inertia_slope": 1.0,
                "rar_above_trigger": True,
            },
            observation_state=state,
        )

        self.assertTrue(decision["should_alert"])
        self.assertEqual(decision["alert_type"], "SECONDARY_CONFIRM_LOWER")
        self.assertGreaterEqual(decision["secondary_progress_atr"], 0.22)
        self.assertFalse(decision["observation_update"]["pending_confirm"])

    def test_enrich_klines_does_not_write_inertia_fields(self):
        from engine.indicators import enrich_klines

        bars = []
        for i, close in enumerate([100, 99, 98, 97, 96, 95, 96, 98, 101, 104, 106, 108, 109, 110, 111, 112, 113, 114, 115, 116]):
            bars.append({"open": close - 0.5, "high": close + 1, "low": close - 1, "close": close, "volume": 1000 + i})
        enriched = enrich_klines(bars)
        for key in ("inertia", "inertia_signal", "inertia_green", "inertia_turn_up", "inertia_source"):
            self.assertNotIn(key, enriched[-1])

        # Even explicit inbound inertia is stripped — enrich must not re-emit it.
        bars[-1].update({"inertia": 12.0, "inertia_signal": 15.0, "inertia_turn_up": True})
        stripped = enrich_klines(bars)
        for key in ("inertia", "inertia_signal", "inertia_turn_up", "inertia_source"):
            self.assertNotIn(key, stripped[-1])

    def test_trend_message_removes_duplicate_major_sections(self):
        from engine.trend_messages import _dedupe_major_sections, format_trend_message

        malformed = "标题\n\n⚠️ 风险位：\nA\n\n✅ 结论：\nB\n\n⚠️ 风险位：\nA\n\n✅ 结论：\nB"
        fixed = _dedupe_major_sections(malformed)
        self.assertEqual(fixed.count("⚠️ 风险位："), 1)
        self.assertEqual(fixed.count("✅ 结论："), 1)

        message = format_trend_message(
            {
                "direction": "long",
                "alert_type": "EARLY_LONG_TRIAL",
                "zone": (9950.0, 10020.0),
                "htf_context": "4H 震荡",
                "momentum_desc": "短线动能修复",
                "temperature_desc": "热度 中性",
                "invalid_level": 9940.0,
            }
        )
        self.assertEqual(message.count("📌 关注点"), 1)
        self.assertEqual(message.count("✅ 结论"), 1)
        self.assertEqual(message.count("📍 开单建议 📍"), 1)
        self.assertNotIn("⚠️ 风险位", message)
        self.assertNotIn("动能与热度", message)
        self.assertIn("严格按关注点管理。", message)

    def test_failed_observation_delivery_does_not_open_pending_state(self):
        from engine.scanner import SMCTScanner
        from services.telegram import TelegramSendError

        bars = [self._bar(10000, 10050, 9950, 10000) for _ in range(30)]
        observation = {
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "alert_type": "EARLY_LONG_TRIAL",
            "direction": "long",
            "price": 10000.0,
            "score": 60,
            "should_alert": True,
            "state_version": "EARLY_LONG_TRIAL_R1",
            "zone": (9950.0, 10020.0),
            "invalid_level": 9940.0,
            "htf_context": "4H 震荡",
            "momentum_desc": "短线动能修复",
            "temperature_desc": "热度 中性",
            "observation_update": {"pending_confirm": True, "pending_side": "lower"},
        }
        no_trend = {
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "alert_type": "NO_TRADE_RANGE",
            "direction": "neutral",
            "price": 10000.0,
            "score": 0,
            "should_alert": False,
            "zone": (10000.0, 10000.0),
            "invalid_level": 10000.0,
        }

        with patch.object(SMCTScanner, "_fetch_enriched", return_value=bars), \
             patch("engine.scanner.get_logger", return_value=Mock()), \
             patch("engine.scanner.build_liquidity_context", return_value=self._neutral_liq()), \
             patch("engine.scanner.build_trend_matrix_proxy", return_value={"matrix_direction": "neutral"}), \
             patch("engine.scanner.build_volume_profile_context", return_value={}), \
             patch("engine.scanner.build_aux_filters_proxy", return_value={"price": 10000.0}), \
             patch("engine.scanner.build_range_lock_context", return_value={"active": False}), \
             patch("engine.scanner.load_trend_state", return_value={}), \
             patch("engine.scanner.load_observation_state", return_value={}), \
             patch("engine.scanner.decide_trend_segment", return_value=no_trend), \
             patch("engine.scanner.decide_key_zone_observation", return_value=observation), \
             patch("engine.scanner.save_observation_state") as save_observation, \
             patch("engine.scanner.apply_late_filter", side_effect=lambda decision, _: decision), \
             patch("engine.scanner.format_trend_message", return_value="message"), \
             patch("engine.scanner.send_telegram_message", side_effect=TelegramSendError("fail")):
            scanner = SMCTScanner("BTCUSDT")
            scanner.state_store = Mock()
            scanner.state_store.should_send.return_value = True
            scanner.runtime_state = Mock()
            result = scanner.run_once()

        self.assertTrue(result["ok"])
        self.assertEqual(result["sent"], 0)
        save_observation.assert_not_called()
