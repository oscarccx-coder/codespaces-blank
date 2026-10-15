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
        self.assertTrue(buttons["Run Selected Worker"].isEnabled())
        self.assertFalse(buttons["Approve Draft"].isEnabled())
        with patch.object(module.store, "details", wraps=module.store.details) as fetch:
            buttons["Refresh"].click()
            # One project snapshot, not duplicate full-table fetches.
            self.assertEqual(fetch.call_count, 1)
        self.assertEqual(task_tree.currentItem().data(0, 0x0100), chosen_id)
        self.assertTrue(buttons["Run Selected Worker"].isEnabled())

        search = next(edit for edit in panel.findChildren(QLineEdit)
                      if edit.placeholderText() == "Find a project...")
        search.setText("missing")
        self.assertEqual(project_list.count(), 0)
        self.assertFalse(buttons["Run Selected Worker"].isEnabled())
        search.clear()
        self.assertEqual(project_list.count(), 1)

    def test_voice_tiles_have_readable_labels_and_individual_delete(self):
        import json
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QListWidget, QPushButton, QToolButton, QMessageBox, QLabel
        from modules.voice_imprint_trainer.module import Module

        module = Module({"base_dir": self.root, "validation": True})
        self.addCleanup(module.close)
        for pid, name, trained in (
            ("voice_a", "Apollo narrator", True),
            ("voice_b", "Second saved voice", False),
        ):
            folder = module.profiles / pid
            folder.mkdir(parents=True)
            (folder / "profile.json").write_text(json.dumps({
                "id": pid, "name": name, "signature_trained": trained,
                "created_at": "2026-10-15",
            }), encoding="utf-8")
            (folder / "recording.wav").write_bytes(b"private test audio")
        page = module.build_ui()
        self.addCleanup(page.close)
        voices = page.findChild(QListWidget, "savedVoiceProfiles")
        self.assertIsNotNone(voices)
        self.assertEqual(voices.count(), 2)
        for index, name, expected_status in (
            (0, "Apollo narrator", "Ready"),
            (1, "Second saved voice", "Needs training"),
        ):
            item = voices.item(index)
            self.assertGreaterEqual(item.sizeHint().height(), 54)
            tile = voices.itemWidget(item)
            self.assertIsNotNone(tile)
            title = tile.findChild(QPushButton, "voiceProfileName")
            self.assertIsNotNone(title)
            self.assertIn(name, title.text())
            self.assertEqual(tile.findChild(QToolButton, "voiceProfileDelete").text(), "Delete")
            self.assertIn(expected_status, tile.findChild(QLabel, "voiceProfileStatus").text())

        second = voices.itemWidget(voices.item(1))
        delete = second.findChild(QToolButton, "voiceProfileDelete")
        with patch.object(QMessageBox, "question",
                          return_value=QMessageBox.StandardButton.Yes) as confirm:
            delete.click()
            self.assertEqual(confirm.call_count, 1)
        self.assertEqual(voices.count(), 1)
        self.assertEqual(voices.item(0).data(Qt.UserRole), "voice_a")
        self.assertTrue((module.profiles / "voice_a").exists())
        self.assertFalse((module.profiles / "voice_b").exists())
        self.assertEqual(len(list((module.storage / "deleted_profiles").glob("voice_b-*"))), 1)

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
