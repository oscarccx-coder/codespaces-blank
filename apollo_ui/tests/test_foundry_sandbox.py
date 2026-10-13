"""Security and failure regressions for Docker-only Apollo Foundry runtime tests."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from apollo_foundry_sandbox import (
    availability, run_sandbox, _make_snapshot, _container_args,
    _execute_bounded, MAX_LOG_BYTES,
)
from apollo_project_studio import StudioStore


def docker_installed(argv, **kwargs):
    assert argv[:3] == ["docker", "image", "inspect"]
    return subprocess.CompletedProcess(argv, 0, "", "")


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
            with patch("apollo_foundry_sandbox.subprocess.Popen") as process:
                report = self.store.run_sandbox_tests(self.pid, "unit")
        process.assert_not_called()
        self.assertEqual(report["status"], "unavailable")
        self.assertFalse(report["executed_project_code"])
        self.assertEqual(len(self.store.sandbox_history(self.pid)), 1)
        self.assertEqual(self.store.check_history(self.pid), [])

    def test_required_image_never_auto_pulled(self):
        with patch("apollo_foundry_sandbox.subprocess.run",
                   return_value=subprocess.CompletedProcess([], 1)):
            result = availability("gui", docker_bin="docker")
        self.assertFalse(result["ok"])
        self.assertIn("not installed", result["reason"])

    def test_container_security_arguments_are_fixed(self):
        argv = _container_args("docker", "apollo-foundry-123", "/tmp/snapshot", "unit")
        command = " ".join(argv)
        for option in (
            "--network=none", "--read-only", "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true", "--pids-limit=64",
            "--cpus=1", "--memory=768m", "--user=65534:65534",
            "--pull=never", "source=/tmp/snapshot,target=/work,readonly",
        ):
            self.assertIn(option, command)
        self.assertNotIn("--privileged", argv)
        self.assertNotIn("--network=host", argv)
        self.assertNotIn("/var/run/docker.sock", command)
        self.assertEqual(argv[-6:], ["unittest", "discover", "-s", "tests", "-p", "test_*.py"])
        gui = _container_args("docker", "apollo-foundry-456", "/tmp/snapshot", "gui")
        self.assertEqual(gui[-4:-1], ["python", "-B", "-c"])
        self.assertIn("launch.py", gui[-1])

    def test_code_only_runs_via_docker_and_reports_are_saved(self):
        invocations = []
        def fake_execute(argv, binary, name, timeout):
            invocations.append(argv)
            self.assertEqual(argv[:2], ["docker", "run"])
            return {"returncode": 0, "timeout": False, "overflow": False,
                    "cleanup_ok": None, "output": "Ran 1 test in 0.003s\n\nOK"}
        with patch("apollo_foundry_sandbox.subprocess.run", side_effect=docker_installed):
            with patch("apollo_foundry_sandbox._execute_bounded", side_effect=fake_execute):
                report = self.store.run_sandbox_tests(self.pid, "unit", docker_bin="docker")
        self.assertEqual(report["status"], "passed")
        self.assertTrue(report["executed_project_code"])
        self.assertFalse(report["passed_ui_interactions"])
        self.assertEqual(len(invocations), 1)
        self.assertEqual(self.store.sandbox_history(self.pid)[0]["status"], "passed")

    def test_failures_cannot_approve_project_automatically(self):
        fake = {"returncode": 1, "timeout": False, "overflow": False,
                "cleanup_ok": None, "output": "AssertionError: button not connected"}
        with patch("apollo_foundry_sandbox.subprocess.run", side_effect=docker_installed):
            with patch("apollo_foundry_sandbox._execute_bounded", return_value=fake):
                report = self.store.run_sandbox_tests(self.pid, "unit", docker_bin="docker")
        self.assertEqual(report["status"], "failed")
        self.assertIn("button not connected", report["output"])
        self.assertFalse(any(t["state"] == "accepted" for t in self.store.details(self.pid)["tasks"]))
        ticket = self.store.request_change(self.pid, report["output"])
        self.assertFalse(ticket["code_changed"])
        self.assertFalse(ticket["tests_passed"])

    def test_empty_unit_suite_cannot_pass(self):
        (self.folder / "tests/test_ui.py").unlink()
        with patch("apollo_foundry_sandbox.subprocess.run", side_effect=docker_installed):
            with patch("apollo_foundry_sandbox._execute_bounded") as runner:
                report = run_sandbox(self.folder, "unit", docker_bin="docker")
        runner.assert_not_called()
        self.assertEqual(report["status"], "incomplete")

    def test_false_green_zero_test_process_rejected(self):
        fake = {"returncode": 0, "timeout": False, "overflow": False,
                "cleanup_ok": None, "output": "Ran 0 tests in 0.000s\n\nOK"}
        with patch("apollo_foundry_sandbox.subprocess.run", side_effect=docker_installed):
            with patch("apollo_foundry_sandbox._execute_bounded", return_value=fake):
                report = run_sandbox(self.folder, "unit", docker_bin="docker")
        self.assertEqual(report["status"], "incomplete")

    def test_timeout_forces_docker_cleanup(self):
        class HungProcess:
            returncode = None
            killed = False
            def poll(self):
                return -9 if self.killed else None
            def kill(self):
                self.killed = True
                self.returncode = -9
            def wait(self, timeout=None):
                return self.returncode
        with patch("apollo_foundry_sandbox.subprocess.Popen", return_value=HungProcess()):
            with patch("apollo_foundry_sandbox._force_remove", return_value=True) as cleanup:
                report = _execute_bounded(["docker", "run", "bad"], "docker",
                                          "apollo-foundry-safe", timeout=0)
        self.assertTrue(report["timeout"])
        self.assertTrue(report["cleanup_ok"])
        cleanup.assert_called_once_with("docker", "apollo-foundry-safe")

    def test_unbounded_output_is_stopped_before_ram_exhaustion(self):
        class LoudProcess:
            returncode = 0
            def __init__(self, **kwargs):
                kwargs["stdout"].write(b"Z" * (MAX_LOG_BYTES + 1))
                kwargs["stdout"].flush()
            def poll(self):
                return 0
        with patch("apollo_foundry_sandbox.subprocess.Popen",
                   side_effect=lambda *args, **kwargs: LoudProcess(**kwargs)):
            with patch("apollo_foundry_sandbox._force_remove", return_value=True):
                report = _execute_bounded(["docker", "run"], "docker",
                                          "apollo-foundry-logcheck", timeout=5)
        self.assertTrue(report["overflow"])
        self.assertLessEqual(len(report["output"]), 15000)

    def test_symlink_escape_cannot_be_snapshot(self):
        outside = self.root / "private.txt"
        outside.write_text("not-for-foundry")
        try:
            (self.folder / "private_link.txt").symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unavailable on test host.")
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

    def test_unknown_test_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            self.store.run_sandbox_tests(self.pid, "shell")


if __name__ == "__main__":
    unittest.main()
