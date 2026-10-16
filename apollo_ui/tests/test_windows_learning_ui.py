"""Real Qt widgets for three Apollo mission apps on offscreen Windows CI."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM","offscreen")

from PySide6.QtWidgets import QApplication,QPushButton,QLineEdit,QCheckBox,QPlainTextEdit,QMessageBox
from apollo_learning_missions import shared_service
from apollo_learning_mission_ui import mission_view


class LearningMissionsQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service=shared_service(self.temp.name,validation=True)
        self.addCleanup(self.cleanup_service)

    def cleanup_service(self):
        self.service.shutdown()
        self.service.store.close()
        if self.service._temp:
            self.service._temp.cleanup()

    def test_learning_window_click_creates_real_mission_and_stop(self):
        window=mission_view(self.service,kind="learning")
        buttons=window.findChildren(QPushButton)
        create=next(b for b in buttons if b.text()=="Authorise and start learning mission")
        name=next(w for w in window.findChildren(QLineEdit))
        goals=next(w for w in window.findChildren(QPlainTextEdit) if not w.isReadOnly())
        consent=next(w for w in window.findChildren(QCheckBox))
        name.setText("Reasoning model research")
        goals.setPlainText("Study evaluation methodologies for local LLMs")
        with patch.object(QMessageBox,"warning",return_value=QMessageBox.Ok):
            create.click()
        self.assertEqual(self.service.store.list(),[])
        consent.setChecked(True)
        with patch.object(QMessageBox,"question",return_value=QMessageBox.Yes):
            create.click()
        item=self.service.store.list()[0]
        self.assertEqual(item["state"],"RUNNING")
        stop=next(b for b in buttons if b.text()=="Stop and finish report")
        with patch.object(QMessageBox,"question",return_value=QMessageBox.Yes):
            stop.click()
        self.assertEqual(self.service.store.status(item["id"])["state"],"STOP_REQUESTED")
        self.service.store.finalize_stops()
        self.assertEqual(self.service.store.status(item["id"])["state"],"STOPPED")
        window.close()

    def test_control_and_library_inspect_same_actual_state(self):
        mid=self.service.begin("Independent research review",
                               "Compare memory evidence storage strategies",
                               mode="fixed",steps=2,web_allowed=True,
                               interval_seconds=120,owner_confirmed=True)["id"]
        control=mission_view(self.service,kind="control")
        library=mission_view(self.service,kind="library")
        self.assertTrue(any(str(mid) in b.item(i).text()
                            for b in control.findChildren(__import__(
                                "PySide6.QtWidgets",fromlist=["QListWidget"]).QListWidget)
                            for i in range(b.count())))
        self.assertIn("Research Library",
                      " ".join(w.text() for w in library.findChildren(
                          __import__("PySide6.QtWidgets",fromlist=["QLabel"]).QLabel)))
        control.close()
        library.close()


if __name__=="__main__":
    unittest.main()
