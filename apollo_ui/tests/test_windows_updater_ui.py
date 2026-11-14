"""Qt Update Centre integration: click real button and run Git against local remote.

Windows-only, offline, no owner installation updated or code executed.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
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
            from PySide6.QtWidgets import QPlainTextEdit
            trace = "\n".join(
                editor.toPlainText()[-2200:] for editor in panel.findChildren(QPlainTextEdit)
            )
            trace += "\n" + "\n".join(
                label.text() for label in panel.findChildren(QLabel)
            )
            trace += "\nQProcess: " + qprocess.errorString()
            self.assertEqual(qprocess.state(), QProcess.ProcessState.NotRunning, trace)
            self.assertEqual((fixture.install / "README.md").read_text(), "version two\n", trace)
            self.assertGreaterEqual(approved.call_count, 2)
            warned.assert_not_called()
            self.assertTrue(observed_running or (fixture.install / "README.md").read_text() == "version two\n")

        output = "\n".join(label.text() for label in panel.findChildren(QLabel))
        self.assertIn("Restart required", output)


    def test_zip_install_offers_bootstrap_and_requires_approval(self):
        from PySide6.QtWidgets import QPushButton, QMessageBox
        from modules.update_manager.module import Module
        with tempfile.TemporaryDirectory(prefix="Apollo original ZIP ") as location:
            root = Path(location)
            base = root / "Old Apollo" / "apollo_ui"
            base.mkdir(parents=True)
            (base / "main.py").write_text("# old install\n", encoding="utf-8")
            (base / "storage").mkdir()
            (base / "storage" / "memory.txt").write_text("preserved", encoding="utf-8")
            (base / "Setup").mkdir()
            (base / "Setup" / "21_INSTALL_GIT_SOURCE.bat").write_text("@echo off\n")
            page = Module({"base_dir": base}).build_ui()
            try:
                buttons = {button.text(): button for button in page.findChildren(QPushButton)}
                self.assertIn("Install Git source (no release)", buttons)
                with patch.object(QMessageBox, "question", return_value=QMessageBox.No) as question:
                    buttons["Install Git source (no release)"].click()
                self.assertEqual(question.call_count, 1)
                self.assertFalse((root / "Apollo-Git").exists())
                self.assertEqual(
                    (base / "storage" / "memory.txt").read_text(encoding="utf-8"),
                    "preserved"
                )
            finally:
                page.close()


if __name__ == "__main__":
    unittest.main()
