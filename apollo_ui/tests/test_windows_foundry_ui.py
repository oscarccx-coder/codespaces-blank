"""Trusted Foundry Phase 1 Qt click-through and Project Studio GUI tests.

This file executes only Apollo-maintained test fixture code; it never imports
or runs user-generated project files from workspace/app_development.
"""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests.test_foundry_phase1 import GOOD_UI, GOOD_BACKEND, CONTRACT


class FoundryWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        (self.base / "config.json").write_text('{"model":"qwen2.5-coder:7b"}')

    def test_sandbox_controls_require_owner_confirmation(self):
        from PySide6.QtWidgets import QTabWidget, QPushButton, QMessageBox
        from modules.project_studio.module import Module

        module = Module({"base_dir": self.base})
        self.addCleanup(module.close)
        state = module.store.add_project("Safe UI", "Test sandbox controls")
        panel = module.build_ui()
        self.addCleanup(panel.close)
        buttons = {button.text(): button for button in panel.findChildren(QPushButton)}
        self.assertIn("Run Tests in Sandbox", buttons)
        self.assertIn("GUI Launch Smoke Test", buttons)
        self.assertIn("Send Failures to Worker", buttons)
        tabs = panel.findChild(QTabWidget)
        self.assertIn("4. Sandbox", [tabs.tabText(i) for i in range(tabs.count())])
        with patch.object(QMessageBox, "question", return_value=QMessageBox.No):
            with patch("apollo_foundry_sandbox.subprocess.run") as runner:
                buttons["Run Tests in Sandbox"].click()
                buttons["GUI Launch Smoke Test"].click()
        runner.assert_not_called()
        self.assertEqual(module.store.sandbox_history(state["project"]["id"]), [])

    def test_trusted_reference_button_calls_backend(self):
        from PySide6.QtWidgets import QWidget, QPushButton

        class AppService:
            def __init__(self):
                self.saved = 0

            def save(self):
                self.saved += 1

        class AppWindow(QWidget):
            def __init__(self, backend):
                super().__init__()
                self.backend = backend
                self.save_button = QPushButton("Save", self)
                self.save_button.clicked.connect(self.on_save)

            def on_save(self):
                self.backend.save()

        service = AppService()
        widget = AppWindow(service)
        self.addCleanup(widget.close)
        widget.save_button.click()
        self.assertEqual(service.saved, 1)

    def test_foundry_check_button_is_connected_to_stored_report(self):
        from PySide6.QtWidgets import QTabWidget, QLabel, QPushButton
        from modules.project_studio.module import Module

        module = Module({"base_dir": self.base})
        self.addCleanup(module.close)
        project = module.store.add_project("Widget", "Make a working Save button")
        folder = module.store.project_folder(project["project"]["id"])
        (folder / "ui.py").write_text(GOOD_UI)
        (folder / "service.py").write_text(GOOD_BACKEND)
        (folder / "foundry.json").write_text(json.dumps(CONTRACT))
        panel = module.build_ui()
        self.addCleanup(panel.close)
        buttons = {b.text(): b for b in panel.findChildren(QPushButton)}
        self.assertIn("Run UI & Code Checks", buttons)
        self.assertIn("Request a Change", buttons)
        self.assertIn("Request Fix for Failures", buttons)
        buttons["Run UI & Code Checks"].click()

        history = module.store.check_history(project["project"]["id"])
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["status"], "passed")
        self.assertFalse(history[0]["report"]["verified_runtime_ui"])
        self.assertTrue(any("Latest static check: PASSED" in x.text()
                            for x in panel.findChildren(QLabel)))
        self.assertIn("2. Check Code", [
            t.tabText(i) for t in panel.findChildren(QTabWidget)
            for i in range(t.count())
        ])

    def test_change_this_button_creates_reviewable_task_without_execution(self):
        from PySide6.QtWidgets import QPushButton, QTreeWidget, QInputDialog
        from modules.project_studio.module import Module

        module = Module({"base_dir": self.base})
        self.addCleanup(module.close)
        state = module.store.add_project("Notes UI", "Create a simple notes app")
        panel = module.build_ui()
        self.addCleanup(panel.close)
        tree = panel.findChild(QTreeWidget)
        tree.setCurrentItem(tree.topLevelItem(1))
        buttons = {b.text(): b for b in panel.findChildren(QPushButton)}
        with patch.object(QInputDialog, "getMultiLineText", return_value=("Make the save button wider", True)):
            buttons["Request a Change"].click()
        result = module.store.details(state["project"]["id"])
        self.assertEqual(len(result["issues"]), 1)
        self.assertEqual(result["issues"][0]["state"], "in_progress")
        self.assertEqual(result["tasks"][-1]["role"], "implementer")
        self.assertIn("Make the save button wider", result["tasks"][-1]["brief"])
        self.assertEqual(result["tasks"][-1]["state"], "todo")


if __name__ == "__main__":
    unittest.main()
