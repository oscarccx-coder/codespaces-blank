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

    def test_workflow_diagram_and_team_meeting_controls(self):
        from PySide6.QtWidgets import QTabWidget, QPushButton, QInputDialog
        from apollo_foundry_diagram import ApolloTeamFlow, flow_snapshot
        from modules.project_studio.module import Module

        module = Module({"base_dir": self.base})
        self.addCleanup(module.close)
        project = module.store.add_project("Casimir project", "Python PySide6 desktop app")
        panel = module.build_ui()
        self.addCleanup(panel.close)

        tabs = panel.findChild(QTabWidget)
        self.assertIn("Workflow & Meetings",
                      [tabs.tabText(i) for i in range(tabs.count())])
        view = panel.findChild(ApolloTeamFlow)
        self.assertIsNotNone(view)
        self.assertEqual(view.snapshot["roles"]["architect"]["count"], 1)
        self.assertEqual(view.snapshot["roles"]["implementer"]["state"], "todo")
        button = next(b for b in panel.findChildren(QPushButton)
                      if b.text() == "Hold Team Meeting")
        # Cancelled manual meeting must not call Ollama or invent a transcript.
        with patch.object(QInputDialog, "getText", return_value=("", False)):
            button.click()
        self.assertEqual(module.store.meetings(project["project"]["id"]), [])
        module.store.record_handoff(project["project"]["id"],
                                    "manager", "architect", "Begin architecture")
        status = flow_snapshot(
            module.store.details(project["project"]["id"]), [],
            module.store.audit(project["project"]["id"]))
        self.assertIn(("manager", "architect"), status["handoffs"])
        view.update_flow(status)
        view.begin_meeting()
        self.assertEqual(view.active_role, "architect")
        view.note_speaker("architect")
        self.assertEqual(view.active_role, "implementer")
        view.note_speaker("integrator")
        self.assertEqual(view.active_role, "manager")
        view.note_speaker("manager")
        self.assertIsNone(view.active_role)
        view.finish_meeting()
        self.assertEqual(len(view.live_spoken), 0)
        view.repaint()

    def test_auto_build_prioritizes_implementation_source(self):
        # Inspect the actual UI scheduling closure without starting a model,
        # process or Qt background worker.
        import inspect
        import modules.project_studio.module as foundry_ui

        source = inspect.getsource(foundry_ui.Module.build_ui)
        self.assertIn('1 if t["role"] == "implementer"', source)
        self.assertIn('self.store.start_task(task["id"])', source)
        self.assertLess(
            source.index('self.store.start_task(task["id"])'),
            source.index('self.store.record_handoff(pid, "manager", task["role"]')
        )

    def test_continuous_controls_refuse_missing_docker_and_declined_consent(self):
        from PySide6.QtWidgets import QPushButton, QMessageBox, QLabel
        from modules.project_studio.module import Module

        module = Module({"base_dir": self.base})
        self.addCleanup(module.close)
        project = module.store.add_project("Build and test", "Create a calculator")
        panel = module.build_ui()
        self.addCleanup(panel.close)
        start = panel.findChild(QPushButton, "foundryContinuousStart")
        pause = panel.findChild(QPushButton, "foundryContinuousPause")
        resume = panel.findChild(QPushButton, "foundryContinuousResume")
        stop = panel.findChild(QPushButton, "foundryContinuousStop")
        status = panel.findChild(QLabel, "foundryContinuousStatus")
        self.assertIsNotNone(start)
        self.assertTrue(start.isEnabled())
        self.assertFalse(pause.isEnabled())
        self.assertFalse(resume.isEnabled())
        self.assertFalse(stop.isEnabled())
        with patch("apollo_foundry_sandbox.availability",
                   return_value={"ok": False, "reason": "Docker missing"}):
            with patch.object(QMessageBox, "warning") as warning:
                start.click()
                self.assertEqual(warning.call_count, 1)
                self.assertIn("Docker is not ready", warning.call_args.args[2])
        self.assertIn("off", status.text())
        with patch("apollo_foundry_sandbox.availability",
                   return_value={"ok": True, "reason": "ready"}):
            with patch.object(QMessageBox, "warning",
                              return_value=QMessageBox.StandardButton.No) as warning:
                start.click()
                self.assertEqual(warning.call_count, 1)
                self.assertIn("Docker", warning.call_args.args[2])
        self.assertEqual(module.store.meetings(project["project"]["id"]), [])
        self.assertFalse(pause.isEnabled())
        self.assertFalse(stop.isEnabled())

    def test_continuous_pipeline_wires_isolated_tests_and_pause_guard(self):
        import inspect
        import modules.project_studio.module as foundry_ui
        source = inspect.getsource(foundry_ui.Module.build_ui)
        self.assertIn("def start_auto_sandbox(pid, kind):", source)
        self.assertIn('auto["sandbox_stage"] = "unit"', source)
        self.assertIn('start_auto_sandbox(pid, "gui")', source)
        self.assertIn('auto["paused"] or active_jobs', source)
        self.assertIn("SandboxJob(pid, kind, self.store, signals)", source)
        self.assertIn('continuous_stop.clicked.connect(stop_continuous_action)', source)

    def test_local_app_preview_requires_explicit_consent(self):
        from PySide6.QtCore import QProcess
        from PySide6.QtWidgets import QPushButton, QMessageBox, QPlainTextEdit
        from modules.project_studio.module import Module

        module = Module({"base_dir": self.base})
        self.addCleanup(module.close)
        project = module.store.add_project("Local preview", "Test explicit consent")
        panel = module.build_ui()
        self.addCleanup(panel.close)
        launch = panel.findChild(QPushButton, "foundryLocalPreviewLaunch")
        stop = panel.findChild(QPushButton, "foundryLocalPreviewStop")
        console = panel.findChild(QPlainTextEdit, "foundryLocalPreviewOutput")
        self.assertIsNotNone(launch)
        self.assertIsNotNone(stop)
        self.assertIsNotNone(console)
        self.assertTrue(launch.isEnabled())
        self.assertFalse(stop.isEnabled())
        target = module.store.project_folder(project["project"]["id"]) / "launch.py"
        with patch("apollo_foundry_preview.prepare_local_preview", return_value=target):
            with patch.object(QMessageBox, "warning",
                              return_value=QMessageBox.StandardButton.No) as confirm:
                with patch.object(QProcess, "start") as start:
                    launch.click()
                    self.assertEqual(confirm.call_count, 1)
                    self.assertIn("NOT isolated", confirm.call_args.args[2])
                    start.assert_not_called()
        self.assertFalse(stop.isEnabled())

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
