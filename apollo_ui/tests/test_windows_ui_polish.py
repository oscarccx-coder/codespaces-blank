"""Real PySide6 widget smoke tests, run on Windows CI after Apollo installs Qt."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class FriendlyWindowsUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        (self.root / "config.json").write_text('{"version":"8.0.0.0","model":"qwen2.5-coder:7b"}', encoding="utf-8")

    def test_project_studio_opens_and_keeps_selection_after_refresh(self):
        from PySide6.QtWidgets import QLineEdit, QPushButton, QListWidget, QTreeWidget, QProgressBar
        from modules.project_studio.module import Module

        module = Module({"base_dir": self.root})
        self.addCleanup(module.close)
        state = module.store.add_project("UI test app", "Create a simple offline test app.")
        panel = module.build_ui()
        self.addCleanup(panel.close)

        project_list = panel.findChild(QListWidget)
        task_tree = panel.findChild(QTreeWidget)
        progress = panel.findChild(QProgressBar)
        self.assertEqual(project_list.count(), 1)
        self.assertEqual(progress.value(), 0)
        self.assertEqual(task_tree.topLevelItemCount(), 5)
        task_tree.setCurrentItem(task_tree.topLevelItem(0))
        chosen_id = task_tree.currentItem().data(0, 0x0100)  # Qt.UserRole
        buttons = {b.text(): b for b in panel.findChildren(QPushButton)}
        self.assertTrue(buttons["Draft with Local AI"].isEnabled())
        self.assertFalse(buttons["Accept Draft"].isEnabled())
        with patch.object(module.store, "details", wraps=module.store.details) as fetch:
            buttons["Refresh"].click()
            # One project snapshot, not duplicate full-table fetches.
            self.assertEqual(fetch.call_count, 1)
        self.assertEqual(task_tree.currentItem().data(0, 0x0100), chosen_id)
        self.assertTrue(buttons["Draft with Local AI"].isEnabled())

        search = next(edit for edit in panel.findChildren(QLineEdit)
                      if edit.placeholderText() == "Find a project...")
        search.setText("missing")
        self.assertEqual(project_list.count(), 0)
        self.assertFalse(buttons["Draft with Local AI"].isEnabled())
        search.clear()
        self.assertEqual(project_list.count(), 1)

    def test_update_centre_opens_without_network_or_signing(self):
        from PySide6.QtWidgets import QComboBox, QPushButton, QProgressBar
        from modules.update_manager.module import Module

        module = Module({"base_dir": self.root})
        panel = module.build_ui()
        self.addCleanup(panel.close)
        buttons = {b.text(): b for b in panel.findChildren(QPushButton)}
        self.assertIn("Update Apollo", buttons)
        self.assertIn("Check only", buttons)
        progress = panel.findChildren(QProgressBar)
        self.assertEqual(len(progress), 1)
        self.assertFalse(progress[0].isVisible())
        channel = next(c for c in panel.findChildren(QComboBox)
                       if c.findText("beta") != -1)
        self.assertEqual(channel.currentText(), "stable")


if __name__ == "__main__":
    unittest.main()
