"""Windows/offscreen PySide6 smoke tests for the JARVIS Director App."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication, QPushButton, QTabWidget, QMessageBox
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None, "PySide6 not installed")
class JarvisUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from modules.jarvis_director.module import Module
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "config.json").write_text('{"model": "qwen2.5-coder:7b"}')
        self.module = Module({"base_dir": str(self.root), "validation": True})
        self.addCleanup(self.module.close)
        self.page = self.module.build_ui()
        self.addCleanup(self.page.close)

    def button(self, caption):
        return next(x for x in self.page.findChildren(QPushButton)
                    if x.text() == caption)

    def test_ui_opens_without_starting_any_model_tasks(self):
        self.assertGreaterEqual(len(self.page.findChildren(QTabWidget)), 1)
        self.assertEqual(self.module.director.store.list(), [])
        self.assertIsNone(self.module.director._worker)

    def test_owner_controls_start_pause_resume_stop(self):
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            self.button("Authorise and start LOCAL engineering mission").click()
        missions = self.module.director.store.list()
        self.assertEqual(len(missions), 1)
        self.assertEqual(missions[0]["state"], "RUNNING")
        self.button("Pause").click()
        self.assertEqual(self.module.director.store.list()[0]["state"], "PAUSED")
        self.button("Resume").click()
        self.assertEqual(self.module.director.store.list()[0]["state"], "RUNNING")
        self.button("Stop").click()
        self.assertEqual(self.module.director.store.list()[0]["state"], "STOPPED")
        # UI test does not call a live model, shell, or sandbox.
        self.assertEqual(self.module.director.store.list()[0]["calls_used"], 0)


if __name__ == "__main__":
    unittest.main()
