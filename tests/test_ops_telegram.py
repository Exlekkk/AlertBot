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
        self.assertEqual(extract_bot_command("/test"), "test")
        self.assertEqual(extract_bot_command("/test@AlertBot"), "test")
        self.assertEqual(extract_bot_command("/test 15"), "test")
        self.assertEqual(extract_bot_command("/test@AlertBot 15m"), "test")
        self.assertIsNone(extract_bot_command("check"))
        self.assertIsNone(extract_bot_command(""))
        self.assertIsNone(extract_bot_command(None))

    def test_extract_bot_command_arg(self):
        from services.ops_status import extract_bot_command_arg

        self.assertIsNone(extract_bot_command_arg("/test"))
        self.assertIsNone(extract_bot_command_arg("/test@AlertBot"))
        self.assertEqual(extract_bot_command_arg("/test 15"), "15")
        self.assertEqual(extract_bot_command_arg("/test@AlertBot 15m"), "15m")
        self.assertEqual(extract_bot_command_arg("/test 1"), "1")
        self.assertEqual(extract_bot_command_arg("  /TEST 15 extra "), "15")
        self.assertIsNone(extract_bot_command_arg(""))
        self.assertIsNone(extract_bot_command_arg(None))


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




class FormatTestMessageTests(unittest.TestCase):
    def test_build_format_test_message_shape(self):
        from engine.trend_messages import BANNED, TEST_FORMAT_PREFIX, build_format_test_message

        msg = build_format_test_message()
        self.assertTrue(msg.startswith(TEST_FORMAT_PREFIX))
        self.assertIn("📈 BTC 1H 试多观察【测试】📈", msg)
        self.assertIn("📉 BTC 1H 试空观察【测试】📉", msg)
        # L lock: one line ──────────────── between 试多 and 试空, blank line before and after.
        from engine.trend_messages import TEST_FORMAT_SIDE_SEPARATOR
        self.assertEqual(TEST_FORMAT_SIDE_SEPARATOR, "────────────────")
        self.assertIn(f"\n\n{TEST_FORMAT_SIDE_SEPARATOR}\n\n", msg)
        long_idx = msg.index("📈 BTC 1H 试多观察【测试】📈")
        sep_idx = msg.index(f"\n\n{TEST_FORMAT_SIDE_SEPARATOR}\n\n")
        short_idx = msg.index("📉 BTC 1H 试空观察【测试】📉")
        self.assertLess(long_idx, sep_idx)
        self.assertLess(sep_idx, short_idx)
        self.assertIn("🧭 4H 偏多", msg)
        self.assertIn("🧭 4H 偏空", msg)
        self.assertIn("触发时间 2026-10-25 14:00", msg)
        self.assertIn("🧭 4H 偏多丨触发时间 2026-10-25 14:00\n\n📍 开单建议 📍", msg)
        self.assertIn("🧭 4H 偏空丨触发时间 2026-10-25 14:00\n\n📍 开单建议 📍", msg)
        self.assertIn("📍 开单建议 📍", msg)
        self.assertIn("止盈目标", msg)
        self.assertIn("📌 关注点", msg)
        self.assertIn("✅ 结论", msg)
        self.assertIn("跌破", msg)
        self.assertIn("站回", msg)
        self.assertIn("具备试多观察条件", msg)
        self.assertIn("具备试空观察条件", msg)
        # Titles without 【测试】 must not appear as the live title form alone
        self.assertNotIn("📈 BTC 1H 试多观察 📈", msg)
        self.assertNotIn("📉 BTC 1H 试空观察 📉", msg)
        for term in BANNED:
            self.assertNotIn(term, msg)
            self.assertNotIn(term.lower(), msg.lower())

    def test_sample_uses_fixed_illustrative_numbers(self):
        from engine.trend_messages import format_sample_trial_alert

        long_msg = format_sample_trial_alert(side="long")
        self.assertIn("区间 95000.00 - 95200.00。", long_msg)
        self.assertIn("止盈目标 96000.00 - 96500.00。", long_msg)
        self.assertIn("跌破 94850.00", long_msg)
        self.assertIn("触发时间 2026-10-25 14:00", long_msg)

        short_msg = format_sample_trial_alert(side="short")
        self.assertIn("区间 97000.00 - 97200.00。", short_msg)
        self.assertIn("止盈目标 95800.00 - 96200.00。", short_msg)
        self.assertIn("站回 97350.00", short_msg)


class FormatTestMessage15mTests(unittest.TestCase):
    def test_build_format_test_message_15m_shape(self):
        from engine.trend_messages import (
            BANNED,
            TEST_FORMAT_PREFIX,
            TEST_FORMAT_SIDE_SEPARATOR,
            WEAK_REMINDER_FORBIDDEN,
            build_format_test_message_15m,
        )

        msg = build_format_test_message_15m()
        self.assertTrue(msg.startswith(TEST_FORMAT_PREFIX))
        self.assertIn("📍 BTC 15m 做多🟢位置提醒【测试】", msg)
        self.assertIn("📍 BTC 15m 做空🔴位置提醒【测试】", msg)
        self.assertEqual(TEST_FORMAT_SIDE_SEPARATOR, "────────────────")
        self.assertIn(f"\n\n{TEST_FORMAT_SIDE_SEPARATOR}\n\n", msg)
        long_idx = msg.index("📍 BTC 15m 做多🟢位置提醒【测试】")
        sep_idx = msg.index(f"\n\n{TEST_FORMAT_SIDE_SEPARATOR}\n\n")
        short_idx = msg.index("📍 BTC 15m 做空🔴位置提醒【测试】")
        self.assertLess(long_idx, sep_idx)
        self.assertLess(sep_idx, short_idx)
        self.assertIn("这不是 1H 正式观察，只提醒看盘。", msg)
        self.assertIn("区间 95000.00 - 95200.00。", msg)
        self.assertIn("跌破 94850.00 → 本提醒失效。", msg)
        self.assertIn("区间 97000.00 - 97200.00。", msg)
        self.assertIn("站回 97350.00 → 本提醒失效。", msg)
        self.assertIn("最终以 1H / 4H 为准。", msg)
        # Side emoji after 做多/做空; still single leading 📍 (no dual formal wrap / 预警).
        self.assertIn("做多🟢", msg)
        self.assertIn("做空🔴", msg)
        self.assertNotIn("做多📈", msg)
        self.assertNotIn("做空📉", msg)
        self.assertNotIn("📈 BTC", msg)
        self.assertNotIn("📉 BTC", msg)
        self.assertNotIn("预警", msg)
        for term in WEAK_REMINDER_FORBIDDEN:
            self.assertNotIn(term, msg)
        for term in BANNED:
            self.assertNotIn(term, msg)
            self.assertNotIn(term.lower(), msg.lower())

    def test_sample_weak_reminder_numbers(self):
        from engine.trend_messages import format_sample_weak_reminder

        long_msg = format_sample_weak_reminder(side="long")
        self.assertTrue(long_msg.startswith("📍 BTC 15m 做多🟢位置提醒【测试】"))
        self.assertIn("15m 出现可能的做多🟢位置。", long_msg)
        self.assertIn("区间 95000.00 - 95200.00。", long_msg)
        self.assertIn("跌破 94850.00 → 本提醒失效。", long_msg)

        short_msg = format_sample_weak_reminder(side="short")
        self.assertTrue(short_msg.startswith("📍 BTC 15m 做空🔴位置提醒【测试】"))
        self.assertIn("15m 出现可能的做空🔴位置。", short_msg)
        self.assertIn("区间 97000.00 - 97200.00。", short_msg)
        self.assertIn("站回 97350.00 → 本提醒失效。", short_msg)


class TelegramUpdateTestCommandTests(unittest.TestCase):
    def test_process_test_update_replies_sample(self):
        from services.ops_status import process_telegram_update

        update = {
            "update_id": 2,
            "message": {
                "text": "/test@AlertBot",
                "chat": {"id": -100123},
            },
        }
        with patch("services.ops_status.TELEGRAM_CHAT_ID", "-100123"), \
             patch("services.ops_status.TELEGRAM_BOT_TOKEN", "token"), \
             patch("services.ops_status.send_telegram_message", return_value={"ok": True}) as send_mock:
            result = process_telegram_update(update)

        self.assertTrue(result["handled"])
        self.assertEqual(result["command"], "test")
        self.assertTrue(result["ok"])
        send_mock.assert_called_once()
        sent_text = send_mock.call_args.args[2]
        self.assertTrue(sent_text.startswith("🧪 播报格式测试（非实盘信号）"))
        self.assertIn("试多观察【测试】", sent_text)
        self.assertIn("试空观察【测试】", sent_text)
        self.assertIn("\n\n────────────────\n\n", sent_text)

    def test_test_foreign_chat_ignored(self):
        from services.ops_status import process_telegram_update

        update = {"message": {"text": "/test", "chat": {"id": 999}}}
        with patch("services.ops_status.TELEGRAM_CHAT_ID", "111"), \
             patch("services.ops_status.TELEGRAM_BOT_TOKEN", "token"), \
             patch("services.ops_status.send_telegram_message") as send_mock:
            result = process_telegram_update(update)

        self.assertTrue(result["handled"])
        self.assertTrue(result.get("skipped"))
        send_mock.assert_not_called()

    def test_process_test_15_replies_weak_reminder_sample(self):
        from services.ops_status import process_telegram_update

        update = {
            "update_id": 3,
            "message": {
                "text": "/test 15",
                "chat": {"id": -100123},
            },
        }
        with patch("services.ops_status.TELEGRAM_CHAT_ID", "-100123"), \
             patch("services.ops_status.TELEGRAM_BOT_TOKEN", "token"), \
             patch("services.ops_status.send_telegram_message", return_value={"ok": True}) as send_mock:
            result = process_telegram_update(update)

        self.assertTrue(result["handled"])
        self.assertEqual(result["command"], "test")
        self.assertEqual(result.get("sample_kind"), "15m")
        self.assertTrue(result["ok"])
        send_mock.assert_called_once()
        sent_text = send_mock.call_args.args[2]
        self.assertIn("📍 BTC 15m 做多🟢位置提醒【测试】", sent_text)
        self.assertIn("📍 BTC 15m 做空🔴位置提醒【测试】", sent_text)
        self.assertNotIn("试多", sent_text)
        self.assertNotIn("试空", sent_text)

    def test_process_test_15m_alias(self):
        from services.ops_status import process_telegram_update

        update = {"message": {"text": "/test@AlertBot 15m", "chat": {"id": -100123}}}
        with patch("services.ops_status.TELEGRAM_CHAT_ID", "-100123"), \
             patch("services.ops_status.TELEGRAM_BOT_TOKEN", "token"), \
             patch("services.ops_status.send_telegram_message", return_value={"ok": True}) as send_mock:
            result = process_telegram_update(update)

        self.assertEqual(result.get("sample_kind"), "15m")
        sent_text = send_mock.call_args.args[2]
        self.assertIn("15m 做多🟢位置提醒【测试】", sent_text)

    def test_process_test_unknown_arg_falls_back_to_1h(self):
        from services.ops_status import process_telegram_update

        update = {"message": {"text": "/test 1", "chat": {"id": -100123}}}
        with patch("services.ops_status.TELEGRAM_CHAT_ID", "-100123"), \
             patch("services.ops_status.TELEGRAM_BOT_TOKEN", "token"), \
             patch("services.ops_status.send_telegram_message", return_value={"ok": True}) as send_mock:
            result = process_telegram_update(update)

        self.assertEqual(result.get("sample_kind"), "1h")
        sent_text = send_mock.call_args.args[2]
        self.assertIn("试多观察【测试】", sent_text)
        self.assertIn("试空观察【测试】", sent_text)
        self.assertNotIn("15m 做多🟢位置提醒", sent_text)

    def test_test_does_not_touch_runtime_state(self):
        from engine.runtime_state import RuntimeStateStore
        from services.ops_status import handle_test_command

        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "runtime.json"
            store = RuntimeStateStore(state_file=str(state_path))
            before = store.get_snapshot()
            with patch("services.ops_status.TELEGRAM_CHAT_ID", "111"), \
                 patch("services.ops_status.TELEGRAM_BOT_TOKEN", "token"), \
                 patch("services.ops_status.send_telegram_message", return_value={"ok": True}):
                handle_test_command(reply_chat_id="111")
            after = RuntimeStateStore(state_file=str(state_path)).get_snapshot()
        # Ops /test must not mutate signal/runtime state.
        self.assertEqual(before, after)



class ResolveGitHeadTests(unittest.TestCase):
    def test_explicit_cwd_without_git_returns_na(self):
        from services.ops_status import resolve_git_head

        with tempfile.TemporaryDirectory() as tmp:
            # Force only the empty dir: patch candidates to that single path
            with patch("services.ops_status._repo_root_candidates", return_value=[tmp]):
                self.assertEqual(resolve_git_head(cwd=tmp), "n/a")

    def test_prefers_smct_repo_root_over_bad_cwd(self):
        from services import ops_status

        repo_root = str(Path(__file__).resolve().parents[1])
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(ops_status, "SMCT_REPO_ROOT", repo_root), \
                 patch.dict("os.environ", {"SMCT_REPO_ROOT": repo_root}, clear=False):
                # Process cwd is irrelevant; env/install root should still resolve.
                sha = ops_status.resolve_git_head(cwd=tmp)
        self.assertNotEqual(sha, "n/a")
        self.assertTrue(len(sha) >= 7)

    def test_install_root_works_when_cwd_is_elsewhere(self):
        from services.ops_status import resolve_git_head

        with tempfile.TemporaryDirectory() as tmp:
            # cwd arg points at non-repo; install root (via __file__) still wins after it fails
            sha = resolve_git_head(cwd=tmp)
        self.assertNotEqual(sha, "n/a")
        self.assertRegex(sha, r"^[0-9a-f]{7,}$")


class OpsPollLockTests(unittest.TestCase):
    def test_second_acquire_skipped_while_held(self):
        from services.ops_poll_lock import release_ops_poll_lock, try_acquire_ops_poll_lock

        with tempfile.TemporaryDirectory() as tmp:
            lock_path = str(Path(tmp) / "smct-tg-ops-poll.lock")
            first = try_acquire_ops_poll_lock(lock_path)
            self.assertIsNotNone(first)
            second = try_acquire_ops_poll_lock(lock_path)
            self.assertIsNone(second)
            release_ops_poll_lock(first)
            third = try_acquire_ops_poll_lock(lock_path)
            self.assertIsNotNone(third)
            release_ops_poll_lock(third)

if __name__ == "__main__":
    unittest.main()
