import os
import unittest
from unittest import mock

from config import env_amst_then_smct
from engine.volume_weak import abnormal_volume_weak_enabled


class EnvAmstThenSmctTests(unittest.TestCase):
    def test_prefers_amst_over_smct(self):
        env = {
            "AMST_SIGNAL_STATE_FILE": "/new/signal.json",
            "SMCT_SIGNAL_STATE_FILE": "/old/signal.json",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            self.assertEqual(
                env_amst_then_smct("SIGNAL_STATE_FILE", "/default.json"),
                "/new/signal.json",
            )

    def test_falls_back_to_smct_when_amst_unset(self):
        with mock.patch.dict(os.environ, {"SMCT_ENV_FILE": "/old/config/.env"}, clear=False):
            os.environ.pop("AMST_ENV_FILE", None)
            self.assertEqual(
                env_amst_then_smct("ENV_FILE", "/opt/amst-alert/config/.env"),
                "/old/config/.env",
            )

    def test_falls_back_to_smct_when_amst_empty_or_whitespace(self):
        env = {
            "AMST_RUNTIME_STATE_FILE": "  ",
            "SMCT_RUNTIME_STATE_FILE": "/old/runtime.json",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            self.assertEqual(
                env_amst_then_smct("RUNTIME_STATE_FILE", "/default.json"),
                "/old/runtime.json",
            )

    def test_default_when_both_unset(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AMST_REPO_ROOT", None)
            os.environ.pop("SMCT_REPO_ROOT", None)
            self.assertEqual(env_amst_then_smct("REPO_ROOT", ""), "")

    def test_default_when_both_empty(self):
        env = {"AMST_REPO_ROOT": "", "SMCT_REPO_ROOT": ""}
        with mock.patch.dict(os.environ, env, clear=False):
            self.assertEqual(env_amst_then_smct("REPO_ROOT", "/unused"), "/unused")


class AbnormalVolumeWeakEnabledDualReadTests(unittest.TestCase):
    def test_amst_key_on(self):
        with mock.patch.dict(
            os.environ, {"AMST_ABNORMAL_VOLUME_WEAK_ENABLED": "1"}, clear=False
        ):
            os.environ.pop("SMCT_ABNORMAL_VOLUME_WEAK_ENABLED", None)
            self.assertTrue(abnormal_volume_weak_enabled())

    def test_smct_key_on_when_amst_unset(self):
        with mock.patch.dict(
            os.environ, {"SMCT_ABNORMAL_VOLUME_WEAK_ENABLED": "1"}, clear=False
        ):
            os.environ.pop("AMST_ABNORMAL_VOLUME_WEAK_ENABLED", None)
            self.assertTrue(abnormal_volume_weak_enabled())

    def test_amst_off_wins_over_smct_on(self):
        env = {
            "AMST_ABNORMAL_VOLUME_WEAK_ENABLED": "0",
            "SMCT_ABNORMAL_VOLUME_WEAK_ENABLED": "1",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            self.assertFalse(abnormal_volume_weak_enabled())

    def test_default_off_when_unset(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AMST_ABNORMAL_VOLUME_WEAK_ENABLED", None)
            os.environ.pop("SMCT_ABNORMAL_VOLUME_WEAK_ENABLED", None)
            self.assertFalse(abnormal_volume_weak_enabled())


if __name__ == "__main__":
    unittest.main()
