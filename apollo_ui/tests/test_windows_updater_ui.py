"""Qt Update Centre integration: click real button and run Git against local remote.

Windows-only, offline, no owner installation updated or code executed.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@unittest.skipUnless(os.name == "nt" and shutil.which("git"), "Windows Git only")
class UpdateCentreButtonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_git_update_button_fast_forwards_disposable_checkout(self):
        from PySide6.QtCore import QProcess
        from PySide6.QtWidgets import QPushButton, QMessageBox, QLabel
        from modules.update_manager.module import Module
        from tests.test_git_updater_windows import WindowsMainGitUpdateTests

        # The shared fixture creates two throwaway local Git clones and a
        # bare remote, all under a path containing spaces and parentheses.
        fixture = WindowsMainGitUpdateTests("test_real_local_origin_fast_forward_from_numbered_setup")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture._make_remote_update()
        base = fixture.install / "apollo_ui"
        self.assertEqual((fixture.install / "README.md").read_text(), "version one\n")

        module = Module({"base_dir": base})
        panel = module.build_ui()
        self.addCleanup(panel.close)
        buttons = {button.text(): button for button in panel.findChildren(QPushButton)}
        self.assertIn("Update from Git (main)", buttons)
        qprocesses = panel.findChildren(QProcess)
        self.assertEqual(len(qprocesses), 1)
        qprocess = qprocesses[0]

        with patch.object(QMessageBox, "question", side_effect=[
            QMessageBox.StandardButton.Yes,  # Authorize disposable Git fast-forward
            QMessageBox.StandardButton.No,   # Don't relaunch any application
        ]) as approved, patch.object(QMessageBox, "warning") as warned:
            buttons["Update from Git (main)"].click()
            deadline = time.monotonic() + 20
            observed_running = False
            while time.monotonic() < deadline:
                self.app.processEvents()
                if qprocess.state() != QProcess.ProcessState.NotRunning:
                    observed_running = True
                if (fixture.install / "README.md").read_text() == "version two\n" and \
                        qprocess.state() == QProcess.ProcessState.NotRunning and approved.call_count >= 2:
                    break
                time.sleep(0.03)
            self.app.processEvents()
            self.assertEqual(qprocess.state(), QProcess.ProcessState.NotRunning)
            self.assertEqual((fixture.install / "README.md").read_text(), "version two\n")
            self.assertGreaterEqual(approved.call_count, 2)
            warned.assert_not_called()
            self.assertTrue(observed_running or (fixture.install / "README.md").read_text() == "version two\n")

        output = "\n".join(label.text() for label in panel.findChildren(QLabel))
        self.assertIn("Restart required", output)


if __name__ == "__main__":
    unittest.main()
