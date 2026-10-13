"""Real Foundry Docker integration: sample PySide6 UI and backend code in sandbox.

Enabled explicitly by CI; never runs user's project outside Docker.
"""
import os
from pathlib import Path
import tempfile
import unittest

from apollo_project_studio import StudioStore


@unittest.skipUnless(os.environ.get("APOLLO_FOUNDRY_INTEGRATION") == "1",
                     "Run only in isolated Foundry Docker integration CI")
class RealDockerFoundryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = StudioStore(self.temp.name)
        self.addCleanup(self.store.close)
        created = self.store.add_project("Trusted Foundry GUI example", "Test UI button connection.")
        self.pid = created["project"]["id"]
        self.store.create_starter_ui(self.pid)

    def test_actual_qt_ui_button_reaches_backend_in_container(self):
        report = self.store.run_sandbox_tests(self.pid, "unit")
        self.assertEqual(report["status"], "passed", report)
        self.assertTrue(report["executed_project_code"])
        self.assertIn("Ran 1 test", report["output"])
        self.assertEqual(self.store.sandbox_history(self.pid)[0]["report"]["kind"], "docker-unit")

    def test_actual_gui_starts_and_survives_smoke_window(self):
        report = self.store.run_sandbox_tests(self.pid, "gui")
        self.assertEqual(report["status"], "passed", report)
        self.assertIn("GUI STARTUP SURVIVED 3s", report["output"])
        self.assertFalse(report["passed_ui_interactions"])

    def test_real_failing_test_must_report_failure(self):
        folder = self.store.project_folder(self.pid)
        (folder / "tests" / "test_ui.py").write_text(
            "import unittest\n"
            "class Regression(unittest.TestCase):\n"
            "    def test_breakage(self):\n"
            "        self.assertEqual(1, 2)\n",
            encoding="utf-8",
        )
        report = self.store.run_sandbox_tests(self.pid, "unit")
        self.assertEqual(report["status"], "failed", report)
        self.assertIn("FAILED", report["output"])
        self.assertTrue(any(x["status"] == "failed" for x in self.store.sandbox_history(self.pid)))

    def test_gui_launch_failure_is_reported(self):
        folder = self.store.project_folder(self.pid)
        (folder / "launch.py").write_text(
            "raise RuntimeError('App startup failure for sandbox CI')\n",
            encoding="utf-8",
        )
        report = self.store.run_sandbox_tests(self.pid, "gui")
        self.assertEqual(report["status"], "failed", report)
        self.assertIn("App startup failure", report["output"])


if __name__ == "__main__":
    unittest.main()
