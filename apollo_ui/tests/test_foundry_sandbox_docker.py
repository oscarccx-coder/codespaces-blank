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

    def test_real_declared_ui_click_invokes_backend_in_docker(self):
        report = self.store.run_sandbox_tests(self.pid, "ui")
        self.assertEqual(report["status"], "passed", report)
        self.assertTrue(report["passed_ui_interactions"])
        self.assertIn("UI INTERACTION PASSED: save_button clicked save", report["output"])

    def test_real_ui_wiring_regression_is_detected(self):
        folder = self.store.project_folder(self.pid)
        source = (folder / "ui.py").read_text(encoding="utf-8")
        self.assertIn("self.backend.save()", source)
        (folder / "ui.py").write_text(
            source.replace("self.backend.save()", "None  # broken connection"),
            encoding="utf-8",
        )
        report = self.store.run_sandbox_tests(self.pid, "ui")
        self.assertEqual(report["status"], "failed", report)
        self.assertFalse(report["passed_ui_interactions"])
        self.assertIn("UI interaction did not call backend", report["output"])

    def test_actual_gui_starts_and_survives_smoke_window(self):
        report = self.store.run_sandbox_tests(self.pid, "gui")
        self.assertEqual(report["status"], "passed", report)
        self.assertIn("GUI STARTUP SURVIVED 3s", report["output"])
        self.assertFalse(report["passed_ui_interactions"])

    def test_scientific_dependencies_work_inside_offline_container(self):
        folder = self.store.project_folder(self.pid)
        (folder / "tests" / "test_science.py").write_text(
            "import unittest\n"
            "import numpy as np\n"
            "import sympy as sp\n"
            "import matplotlib\n"
            "class Science(unittest.TestCase):\n"
            "    def test_derivative_and_array(self):\n"
            "        x = sp.symbols('x')\n"
            "        self.assertEqual(sp.diff(x**3, x), 3*x**2)\n"
            "        self.assertEqual(int(np.array([1,2,3]).sum()), 6)\n",
            encoding="utf-8",
        )
        report = self.store.run_sandbox_tests(self.pid, "unit")
        self.assertEqual(report["status"], "passed", report)
        self.assertIn("Ran 2 tests", report["output"])

    def test_container_restrictions_hold_at_runtime(self):
        """Enforce isolation inside Docker, not merely by checking CLI args."""
        folder = self.store.project_folder(self.pid)
        (folder / "tests" / "test_isolation.py").write_text(
            "import os\n"
            "import socket\n"
            "from pathlib import Path\n"
            "import tempfile\n"
            "import unittest\n\n"
            "class SandboxRestrictions(unittest.TestCase):\n"
            "    def test_user_is_non_root(self):\n"
            "        self.assertNotEqual(os.geteuid(), 0)\n"
            "    def test_project_files_are_read_only(self):\n"
            "        with self.assertRaises(OSError):\n"
            "            Path('/work/forbidden-write.txt').write_text('no')\n"
            "    def test_network_is_disabled(self):\n"
            "        with self.assertRaises(OSError):\n"
            "            socket.create_connection(('1.1.1.1', 53), timeout=1)\n"
            "    def test_no_docker_socket_and_tmp_is_writable(self):\n"
            "        self.assertFalse(Path('/var/run/docker.sock').exists())\n"
            "        with tempfile.TemporaryFile() as f:\n"
            "            f.write(b'ok')\n",
            encoding="utf-8",
        )
        report = self.store.run_sandbox_tests(self.pid, "unit")
        self.assertEqual(report["status"], "passed", report)
        self.assertIn("Ran 5 tests", report["output"])

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
