import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class OpsCommandParseTests(unittest.TestCase):
    def test_extract_bot_command_variants(self):
        from services.ops_status import extract_bot_command

        self.assertEqual(extract_bot_command("/check"), "check")
        self.assertEqual(extract_bot_command("/check@MyBot"), "check")
        self.assertEqual(extract_bot_command("  /CHECK please "), "check")
        self.assertIsNone(extract_bot_command("check"))
        self.assertIsNone(extract_bot_command(""))
        self.assertIsNone(extract_bot_command(None))


class OpsStatusMessageTests(unittest.TestCase):
    def test_build_check_message_fields(self):
        from services.ops_status import build_check_message

        msg = build_check_message(
            {
                "ok": True,
                "stale": False,
                "seconds_since_last_scan": 12,
                "last_scan_ok": True,
                "last_scan_error": "",
            },
            freeze_mode=True,
            head_sha="08ed0e3",
        )
        self.assertIn("🛠 /check", msg)
        self.assertIn("状态: running", msg)
        self.assertIn("HEAD: 08ed0e3", msg)
        self.assertIn("freeze: 1", msg)
        self.assertIn("上次扫描: 12s (ok)", msg)
        self.assertIn("上次错误: 无", msg)

    def test_build_error_message(self):
        from services.ops_status import build_error_message

        msg = build_error_message("scanner.run_once", "boom")
        self.assertTrue(msg.startswith("⚠️ 系统异常"))
        self.assertIn("来源: scanner.run_once", msg)
        self.assertIn("错误: boom", msg)


def _load_bihourly():
    import importlib.util
    from pathlib import Path as _P

    path = _P(__file__).resolve().parents[1] / "scripts" / "run_bihourly_report.py"
    spec = importlib.util.spec_from_file_location("run_bihourly_report", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class BihourlySilentOkTests(unittest.TestCase):
    def test_run_once_silent_when_healthy(self):
        mod = _load_bihourly()
        reporter = mod.BihourlyReporter(symbol="BTCUSDT")
        with patch.object(reporter, "run_healthcheck", return_value={"ok": True, "status": "ok"}), \
             patch.object(mod, "send_telegram_message") as send_mock, \
             patch.object(mod, "notify_backend_error") as notify_mock:
            result = reporter.run_once()

        self.assertTrue(result["ok"])
        self.assertFalse(result["sent"])
        self.assertIsNone(result["message"])
        send_mock.assert_not_called()
        notify_mock.assert_not_called()

    def test_run_once_notifies_on_failure(self):
        mod = _load_bihourly()
        reporter = mod.BihourlyReporter(symbol="BTCUSDT")
        with patch.object(reporter, "run_healthcheck", return_value={"ok": False, "error": "down"}), \
             patch.object(
                 mod,
                 "notify_backend_error",
                 return_value={"ok": True, "skipped": False, "telegram_result": {"ok": True}, "message": "err"},
             ) as notify_mock:
            result = reporter.run_once()

        self.assertFalse(result["ok"])
        self.assertTrue(result["sent"])
        notify_mock.assert_called_once()
        self.assertEqual(notify_mock.call_args.args[0], "bihourly_healthcheck")


class ErrorAlertCooldownTests(unittest.TestCase):
    def test_cooldown_suppresses_duplicate(self):
        from engine.runtime_state import RuntimeStateStore
        from services.ops_status import mark_error_alert_sent, should_send_error_alert

        with tempfile.TemporaryDirectory() as tmp:
            store = RuntimeStateStore(state_file=str(Path(tmp) / "runtime.json"))
            self.assertTrue(should_send_error_alert(store, "scanner", "x", cooldown_seconds=60, now=1000.0))
            mark_error_alert_sent(store, "scanner", "x")
            # Force known timestamp for determinism
            store.state["last_error_alert"]["at"] = 1000.0
            store._save()
            self.assertFalse(should_send_error_alert(store, "scanner", "x", cooldown_seconds=60, now=1030.0))
            self.assertTrue(should_send_error_alert(store, "scanner", "x", cooldown_seconds=60, now=1070.0))
            self.assertTrue(should_send_error_alert(store, "scanner", "y", cooldown_seconds=60, now=1030.0))


class TelegramUpdateCheckTests(unittest.TestCase):
    def test_process_check_update_replies(self):
        from engine.runtime_state import RuntimeStateStore
        from services.ops_status import process_telegram_update

        with tempfile.TemporaryDirectory() as tmp:
            store = RuntimeStateStore(state_file=str(Path(tmp) / "runtime.json"))
            store.mark_scan(ok=True, symbol="BTCUSDT", summary={})
            update = {
                "update_id": 1,
                "message": {
                    "text": "/check@AlertBot",
                    "chat": {"id": -100123},
                },
            }
            with patch("services.ops_status.TELEGRAM_CHAT_ID", "-100123"), \
                 patch("services.ops_status.TELEGRAM_BOT_TOKEN", "token"), \
                 patch("services.ops_status.send_telegram_message", return_value={"ok": True}) as send_mock, \
                 patch("services.ops_status.resolve_git_head", return_value="abc1234"):
                result = process_telegram_update(update, state=store)

        self.assertTrue(result["handled"])
        self.assertEqual(result["command"], "check")
        self.assertTrue(result["ok"])
        send_mock.assert_called_once()
        sent_text = send_mock.call_args.args[2]
        self.assertIn("🛠 /check", sent_text)
        self.assertIn("HEAD: abc1234", sent_text)

    def test_foreign_chat_ignored(self):
        from services.ops_status import process_telegram_update

        update = {"message": {"text": "/check", "chat": {"id": 999}}}
        with patch("services.ops_status.TELEGRAM_CHAT_ID", "111"), \
             patch("services.ops_status.TELEGRAM_BOT_TOKEN", "token"), \
             patch("services.ops_status.send_telegram_message") as send_mock:
            result = process_telegram_update(update)

        self.assertTrue(result["handled"])
        self.assertTrue(result.get("skipped"))
        send_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
