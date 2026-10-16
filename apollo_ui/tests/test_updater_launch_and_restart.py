"""Signed updater handoff and restart smoke tests with isolated test fixtures.

No real Apollo installation, network access, model downloads or live processes.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding, PrivateFormat, NoEncryption,
)

from apollo_release import publish
from apollo_update import UpdateService, updater_python
from apollo_updater import apply_update


class SignedUpdaterLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="Apollo updater (spaces) ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "new-source"
        self.target = self.root / "Apollo install"
        self.source.mkdir()
        self.target.mkdir()
        (self.source / "config.json").write_text('{"version":"3.1.0"}', encoding="utf-8")
        (self.source / "main.py").write_text("UPDATE_VALUE=2\n", encoding="utf-8")
        (self.target / "config.json").write_text(
            '{"version":"3.0.0","model":"keep-this-model"}', encoding="utf-8"
        )
        (self.target / "main.py").write_text("UPDATE_VALUE=1\n", encoding="utf-8")
        (self.target / "storage" / "media" / "voice_imprint").mkdir(parents=True)
        (self.target / "storage" / "media" / "voice_imprint" / "private.wav").write_bytes(b"KEEP VOICE")
        (self.target / "workspace").mkdir()
        (self.target / "workspace" / "private.txt").write_text("KEEP PROJECT")
        private = Ed25519PrivateKey.generate()
        secret = private.private_bytes(
            Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
        ).decode("ascii")
        with patch.dict(os.environ, {"APOLLO_RELEASE_PRIVATE_PEM": secret}):
            package = publish(self.source, self.root / "releases", "stable")
        self.service = UpdateService(self.target)
        self.service.import_trusted_key(package["public_key"])
        stage = self.service.stage_local_package(package["package"])
        self.assertTrue(stage["ok"], stage)
        self.stage = stage["stage_dir"]

    def _assert_user_data_untouched(self):
        self.assertEqual(
            (self.target / "storage" / "media" / "voice_imprint" / "private.wav").read_bytes(),
            b"KEEP VOICE",
        )
        self.assertEqual((self.target / "workspace" / "private.txt").read_text(), "KEEP PROJECT")

    def test_restart_failure_keeps_successfully_health_checked_update(self):
        health = Mock(returncode=0, stdout="healthy", stderr="")
        with patch("apollo_updater.subprocess.run", return_value=health), \
             patch("apollo_updater.subprocess.Popen", side_effect=OSError("GUI blocked")):
            result = apply_update(self.target, self.stage, restart=True)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["version"], "3.1.0")
        self.assertFalse(result["restart_started"])
        self.assertIn("Start Apollo manually", result["restart_error"])
        self.assertEqual((self.target / "main.py").read_text(), "UPDATE_VALUE=2\n")
        cfg = json.loads((self.target / "config.json").read_text())
        self.assertEqual(cfg["version"], "3.1.0")
        self.assertEqual(cfg["model"], "keep-this-model")
        self.assertFalse(list((self.target / "storage" / "updates" / "logs").glob("rollback-*.json")))
        self._assert_user_data_untouched()

    def test_launch_process_failure_reports_error_without_quitting_apollo(self):
        (self.target / "apollo_updater.py").write_text("pass")
        with patch("apollo_update.subprocess.Popen", side_effect=OSError("Access denied")):
            result = self.service.launch_installer()
        self.assertFalse(result["ok"])
        self.assertFalse(result["installer_started"])
        self.assertIn("Access denied", result["error"])
        self.assertEqual((self.target / "main.py").read_text(), "UPDATE_VALUE=1\n")
        self._assert_user_data_untouched()

    def test_private_python_wins_over_unrelated_gui_interpreter(self):
        (self.target / "apollo_updater.py").write_text("pass")
        private = (self.target / ".venv" /
                   ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
        private.parent.mkdir(parents=True)
        private.write_bytes(b"fake test interpreter; never executed")
        process = Mock(pid=918)
        with patch("apollo_update.subprocess.Popen", return_value=process) as spawned:
            result = self.service.launch_installer()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["installer_pid"], 918)
        args = spawned.call_args.args[0]
        self.assertEqual(Path(args[0]), private.resolve())
        self.assertEqual(Path(args[1]), (self.target / "apollo_updater.py").resolve())
        self.assertIn("--wait-pid", args)

    def test_frozen_app_refuses_to_launch_without_python_runtime(self):
        (self.target / "apollo_updater.py").write_text("pass")
        with patch("apollo_update.sys.frozen", True, create=True), \
             patch("apollo_update.subprocess.Popen") as spawned:
            result = self.service.launch_installer()
        self.assertFalse(result["ok"])
        self.assertIn("private Python environment", result["error"])
        spawned.assert_not_called()

    def test_missing_updater_script_does_not_close_current_app(self):
        with patch("apollo_update.subprocess.Popen") as spawned:
            result = self.service.launch_installer()
        self.assertFalse(result["ok"])
        self.assertIn("script is missing", result["error"])
        spawned.assert_not_called()

    def test_health_failure_still_rolls_back_signed_changes(self):
        health = Mock(returncode=1, stdout="", stderr="intentional CI test failure")
        with patch("apollo_updater.subprocess.run", return_value=health):
            result = apply_update(self.target, self.stage, restart=False)
        self.assertFalse(result["ok"], result)
        self.assertEqual(result["stage"], "rollback")
        self.assertTrue(result["restored"], result)
        self.assertEqual((self.target / "main.py").read_text(), "UPDATE_VALUE=1\n")
        self.assertEqual(json.loads((self.target / "config.json").read_text())["version"], "3.0.0")
        self._assert_user_data_untouched()

    def test_no_signed_release_is_reported_not_silently_installed(self):
        with patch("apollo_update.latest_release", return_value=None):
            state = self.service.check_for_updates()
        self.assertTrue(state["ok"])
        self.assertFalse(state["available"])
        self.assertIn("No matching stable GitHub Release", state["reason"])
        self.assertEqual((self.target / "main.py").read_text(), "UPDATE_VALUE=1\n")


if __name__ == "__main__":
    unittest.main()
