"""Foundry sandbox security, failure and approval-flow tests (Docker mocked)."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from apollo_foundry_sandbox import (
    SANDBOX_KINDS, SandboxUnavailable, availability, run_sandbox,
    _make_snapshot, _container_args, QT_IMAGE,
)
from apollo_project_studio import StudioStore


class SandboxRegressions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = StudioStore(self.root)
        self.addCleanup(self.store.close)
        project = self.store.add_project("Sandbox", "Check local source safely.")
        self.pid = project["project"]["id"]
        self.folder = self.store.project_folder(self.pid)
        self.store.create_starter_ui(self.pid)

    def test_docker_missing_refuses_without_host_fallback(self):
        with patch("apollo_foundry_sandbox.shutil.which", return_value=None):
            with patch("apollo_foundry_sandbox.subprocess.run") as sub:
                report = self.store.run_sandbox_tests(self.pid, "unit")
        sub.assert_not_called()
        self.assertEqual(report["status"], "unavailable")
        self.assertFalse(report["executed_project_code"])
        self.assertEqual(len(self.store.sandbox_history(self.pid)), 1)
        self.assertEqual(self.store.check_history(self.pid), [])

    def test_required_image_never_auto_pulled(self):
        with patch("apollo_foundry_sandbox.subprocess.run", return_value=subprocess.CompletedProcess([], 1)):
            result = availability("gui", docker_bin="docker")
        self.assertFalse(result["ok"])
        self.assertIn("not installed", result["reason"])

    def test_container_security_arguments_are_fixed(self):
        argv = _container_args("docker", "apollo-foundry-123", "/tmp/safe-snapshot", "unit")
        cmd = " ".join(argv)
        for option in (
            "--network=none", "--read-only", "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--pids-limit=64", "--cpus=1", "--memory=768m",
            "--user=65534:65534", "--pull=never",
            "source=/tmp/safe-snapshot,target=/work,readonly"
        ):
            self.assertIn(option, cmd)
        self.assertNotIn("--privileged", argv)
        self.assertNotIn("--network=host", argv)
        self.assertNotIn("/var/run/docker.sock", cmd)
        self.assertEqual(argv[-6:], ["python", "-B", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"][-6:])
        gui = _container_args("docker", "apollo-foundry-456", "/tmp/snapshot", "gui")
        self.assertEqual(gui[-4:-1], ["python", "-B", "-c"])
        self.assertIn("launch.py", gui[-1])

    def test_code_executes_only_via_subprocess_docker_argv(self):
        calls = []
        def docker_run(argv, **kwargs):
            calls.append(list(argv))
            if argv[1:3] == ["image", "inspect"]:
                return subprocess.CompletedProcess(argv, 0, "", "")
            self.assertEqual(argv[:2], ["docker", "run"])
            self.assertNotIn("shell", kwargs)
            return subprocess.CompletedProcess(argv, 0, "", "Ran 1 test in 0.003s\n\nOK")
        with patch("apollo_foundry_sandbox.subprocess.run", side_effect=docker_run):
            result = self.store.run_sandbox_tests(self.pid, "unit", docker_bin="docker")
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["executed_project_code"])
        self.assertFalse(result["passed_ui_interactions"])
        self.assertEqual(len(calls), 2)
        self.assertTrue(any(e["kind"] == "sandbox" for e in self.store.audit(self.pid)))
        self.assertEqual(len(self.store.sandbox_history(self.pid)), 1)

    def test_unit_test_failures_recorded_without_auto_approval(self):
        def docker_run(argv, **kwargs):
            if argv[1] == "image":
                return subprocess.CompletedProcess(argv, 0, "", "")
            return subprocess.CompletedProcess(argv, 1, "", "AssertionError: button not connected")
        with patch("apollo_foundry_sandbox.subprocess.run", side_effect=docker_run):
            report = self.store.run_sandbox_tests(self.pid, "unit", docker_bin="docker")
        self.assertEqual(report["status"], "failed")
        self.assertIn("button not connected", report["output"])
        self.assertFalse(any(t["state"] == "accepted" for t in self.store.details(self.pid)["tasks"]))
        ticket = self.store.request_change(self.pid, report["output"])
        self.assertFalse(ticket["code_changed"])
        self.assertFalse(ticket["tests_passed"])

    def test_empty_unit_suite_cannot_pass(self):
        (self.folder / "tests/test_ui.py").unlink()
        with patch("apollo_foundry_sandbox.subprocess.run",
                   return_value=subprocess.CompletedProcess([], 0)):
            report = run_sandbox(self.folder, "unit", docker_bin="docker")
        self.assertEqual(report["status"], "incomplete")

    def test_false_zero_test_process_result_not_green(self):
        def docker_run(argv, **kwargs):
            if argv[1] == "image":
                return subprocess.CompletedProcess(argv, 0, "", "")
            return subprocess.CompletedProcess(argv, 0, "", "Ran 0 tests in 0.000s\n\nOK")
        with patch("apollo_foundry_sandbox.subprocess.run", side_effect=docker_run):
            report = run_sandbox(self.folder, "unit", docker_bin="docker")
        self.assertEqual(report["status"], "incomplete")

    def test_timeout_triggers_docker_forced_removal(self):
        calls = []
        def fake(argv, **kwargs):
            calls.append(argv)
            if argv[1] == "image":
                return subprocess.CompletedProcess(argv, 0, "", "")
            if argv[1] == "run":
                raise subprocess.TimeoutExpired(argv, timeout=45)
            return subprocess.CompletedProcess(argv, 0, "", "")
        with patch("apollo_foundry_sandbox.subprocess.run", side_effect=fake):
            report = run_sandbox(self.folder, "unit", docker_bin="docker")
        self.assertEqual(report["status"], "timeout")
        self.assertTrue(any(x[1:3] == ["rm", "-f"] for x in calls))

    def test_symlink_escape_cannot_be_snapshot(self):
        outside = self.root / "private.txt"
        outside.write_text("not-for-foundry")
        try:
            (self.folder / "private_link.txt").symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks not available")
        with self.assertRaises(ValueError):
            with tempfile.TemporaryDirectory() as d:
                _make_snapshot(self.folder, Path(d) / "snapshot")

    def test_project_snapshot_excludes_secrets_and_virtualenv(self):
        (self.folder / ".env").write_text("PRIVATE_KEY")
        (self.folder / ".venv").mkdir()
        (self.folder / ".venv" / "private.py").write_text("PASSWORD = 'secret'")
        with tempfile.TemporaryDirectory() as d:
            snap = Path(d) / "snapshot"
            files = _make_snapshot(self.folder, snap)
            self.assertGreater(files, 1)
            self.assertFalse((snap / ".env").exists())
            self.assertFalse((snap / ".venv").exists())
            self.assertTrue((snap / "tests" / "test_ui.py").exists())

    def test_no_symlinked_private_workspace(self):
        with self.assertRaises(ValueError):
            self.store.run_sandbox_tests(self.pid, "shell")
        with patch("apollo_foundry_sandbox.shutil.which", return_value=None):
            result = self.store.run_sandbox_tests(self.pid, "gui")
        self.assertEqual(result["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
