"""Apollo Foundry Phase 1: persistent revision requests and safe UI wiring tests."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from apollo_project_workers import propose_subtasks, validate_subtask_plan

from apollo_foundry_checks import scan_project
from apollo_project_studio import StudioStore


GOOD_UI = """from PySide6.QtWidgets import QPushButton, QWidget
class AppWindow(QWidget):
    def __init__(self, backend):
        super().__init__()
        self.backend = backend
        self.save_button = QPushButton("Save", self)
        self.save_button.clicked.connect(self.on_save)
    def on_save(self):
        self.backend.save()
"""
GOOD_BACKEND = """class AppService:
    def __init__(self):
        self.saved = 0
    def save(self):
        self.saved += 1
"""
CONTRACT = {
    "schema_version": 1,
    "ui": {
        "file": "ui.py", "class": "AppWindow",
        "bindings": [{
            "widget": "save_button", "signal": "clicked", "handler": "on_save",
            "backend_attribute": "backend",
            "backend_file": "service.py", "backend_class": "AppService",
            "backend_method": "save",
        }],
    },
}


class FoundryPhaseOneTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = StudioStore(self.root)
        self.addCleanup(self.store.close)
        data = self.store.add_project("Simple desktop app", "Save a note by clicking a button.")
        self.project_id = data["project"]["id"]
        self.task_id = data["tasks"][1]["id"]
        self.folder = self.store.project_folder(self.project_id)

    def code_fixture(self, ui=GOOD_UI, backend=GOOD_BACKEND, contract=CONTRACT):
        (self.folder / "ui.py").write_text(ui, encoding="utf-8")
        (self.folder / "service.py").write_text(backend, encoding="utf-8")
        (self.folder / "foundry.json").write_text(json.dumps(contract), encoding="utf-8")

    def test_manager_proposal_does_not_create_jobs_until_review(self):
        before = len(self.store.details(self.project_id)["tasks"])
        suggestions = [
            {"title": "Design save workflow", "brief": "Specify API and acceptance checks", "role": "architect"},
            {"title": "Test button callback", "brief": "Define click-through and failure tests", "role": "tester"},
        ]

        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, count):
                return json.dumps({
                    "response": json.dumps({"tasks": suggestions})
                }).encode("utf-8")

        class LocalOnly:
            def open(self, request, timeout):
                assert request.full_url == "http://127.0.0.1:11434/api/generate"
                data = json.loads(request.data)
                assert data["format"] == "json"
                assert "tools" not in data
                return Response()

        with patch("apollo_project_workers.urllib.request.build_opener", return_value=LocalOnly()):
            proposal = propose_subtasks(self.store.details(self.project_id), self.task_id, "qwen2.5-coder:7b")

        self.assertEqual(proposal, suggestions)
        self.assertEqual(len(self.store.details(self.project_id)["tasks"]), before)
        accepted = self.store.add_subtasks(self.task_id, proposal)
        self.assertEqual(len(accepted), 2)
        self.assertEqual(len(self.store.details(self.project_id)["tasks"]), before + 2)
        self.assertEqual({entry["parent_id"] for entry in accepted}, {self.task_id})

    def test_manager_plan_invalid_data_rejected_atomically(self):
        original = len(self.store.details(self.project_id)["tasks"])
        invalid = [
            {"title": "One", "brief": "OK", "role": "implementer"},
            {"title": "Two", "brief": "BAD", "role": "root"},
        ]
        with self.assertRaises(ValueError):
            validate_subtask_plan({"tasks": invalid})
        with self.assertRaises(ValueError):
            self.store.add_subtasks(self.task_id, invalid)
        self.assertEqual(len(self.store.details(self.project_id)["tasks"]), original)
        with self.assertRaises(ValueError):
            self.store.add_subtasks(self.task_id, [{"title": "Duplicate", "brief": "x", "role": "tester"}] * 2)
        self.assertEqual(len(self.store.details(self.project_id)["tasks"]), original)

    def test_starter_ui_can_be_checked_without_running_it(self):
        created = self.store.create_starter_ui(self.project_id)
        self.assertEqual(set(created["files"]), {"ui.py", "service.py", "foundry.json", "launch.py", "tests/test_ui.py"})
        self.assertFalse(created["executed"])
        report = self.store.run_checks(self.project_id)
        self.assertEqual(report["status"], "passed", report["checks"])
        self.assertFalse(report["verified_runtime_ui"])
        self.assertFalse(report["executed_project_code"])

    def test_starter_never_overwrites_existing_user_code(self):
        (self.folder / "ui.py").write_text("KEEP USER SOURCE")
        with self.assertRaises(FileExistsError):
            self.store.create_starter_ui(self.project_id)
        self.assertEqual((self.folder / "ui.py").read_text(), "KEEP USER SOURCE")
        self.assertFalse((self.folder / "foundry.json").exists())

    def test_no_code_is_not_green(self):
        result = self.store.run_checks(self.project_id)
        self.assertEqual(result["status"], "incomplete")
        self.assertFalse(result["executed_project_code"])
        self.assertFalse(result["verified_runtime_ui"])

    def test_valid_wiring_passes_static_only_and_persists(self):
        self.code_fixture()
        report = self.store.run_checks(self.project_id)
        self.assertEqual(report["status"], "passed", report["checks"])
        self.assertGreaterEqual(len(report["checks"]), 6)
        self.assertFalse(report["verified_runtime_ui"])
        self.assertFalse(report["executed_project_code"])
        second_store = StudioStore(self.root)
        try:
            self.assertEqual(second_store.check_history(self.project_id)[0]["status"], "passed")
            self.assertEqual(second_store.details(self.project_id)["project"]["title"], "Simple desktop app")
        finally:
            second_store.close()

    def test_missing_signal_or_backend_is_detected(self):
        self.code_fixture(ui=GOOD_UI.replace("self.save_button.clicked.connect(self.on_save)",
                                             "self.save_button.setText('Nothing connected')"),
                          backend="class AppService:\n    pass\n")
        result = scan_project(self.folder)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any(x["check"] == "signal:1" and x["status"] == "fail"
                            for x in result["checks"]))
        self.assertTrue(any(x["check"] == "backend:1" and x["status"] == "fail"
                            for x in result["checks"]))

    def test_incorrect_backend_call_is_detected(self):
        self.code_fixture(ui=GOOD_UI.replace("self.backend.save()", "pass"))
        report = scan_project(self.folder)
        self.assertEqual(report["status"], "failed")
        self.assertTrue(any(x["check"] == "call:1" and x["status"] == "fail"
                            for x in report["checks"]))

    def test_broken_python_fails(self):
        self.code_fixture(ui="class AppWindow:\n    def broken( :\n        pass\n")
        self.assertEqual(self.store.run_checks(self.project_id)["status"], "failed")

    def test_missing_ui_manifest_is_pending(self):
        (self.folder / "service.py").write_text(GOOD_BACKEND)
        self.assertEqual(scan_project(self.folder)["status"], "incomplete")

    def test_traversal_in_contract_is_refused(self):
        evil = json.loads(json.dumps(CONTRACT))
        evil["ui"]["file"] = "../private.py"
        self.code_fixture(contract=evil)
        report = scan_project(self.folder)
        self.assertEqual(report["status"], "failed")
        self.assertFalse(report["executed_project_code"])

    def test_untrusted_source_not_executed(self):
        self.code_fixture(ui="raise RuntimeError('WOULD HAVE EXECUTED')\n" + GOOD_UI)
        report = scan_project(self.folder)
        self.assertEqual(report["status"], "passed", report["checks"])
        self.assertFalse(report["executed_project_code"])

    def test_oversized_source_fails_without_import(self):
        self.code_fixture(ui=GOOD_UI + "\n# " + "x" * (260 * 1024))
        self.assertEqual(scan_project(self.folder)["status"], "failed")

    def test_symlink_refused_if_supported(self):
        outside = self.root / "sensitive.py"
        outside.write_text("SECRET")
        try:
            (self.folder / "escape.py").symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink privileges unavailable on this platform.")
        self.assertEqual(scan_project(self.folder)["status"], "failed")

    def test_change_request_creates_reviewable_work_not_code_modification(self):
        self.code_fixture()
        initial = (self.folder / "service.py").read_bytes()
        outcome = self.store.request_change(self.project_id, "Make save confirmation visible", self.task_id)
        self.assertEqual(outcome["state"], "queued_for_human_review")
        self.assertFalse(outcome["code_changed"])
        self.assertFalse(outcome["tests_passed"])
        task = self.store._task(outcome["task_id"])
        self.assertEqual(task["role"], "implementer")
        self.assertIn("save confirmation", task["brief"])
        self.assertEqual(self.store.issue(outcome["issue_id"])["state"], "in_progress")
        self.assertEqual(initial, (self.folder / "service.py").read_bytes())
        with self.assertRaises(ValueError):
            self.store.close_issue(outcome["issue_id"])
        self.store.start_task(task["id"])
        self.store.submit_task(task["id"], "Proposed confirmation change", "Review only, tests pending")
        self.store.review_task(task["id"], True, "Manually reviewed proposal")
        self.assertEqual(self.store.close_issue(outcome["issue_id"])["state"], "closed")

    def test_cross_project_change_rejected(self):
        other = self.store.add_project("Other", "Other app")
        with self.assertRaisesRegex(ValueError, "does not belong"):
            self.store.request_change(other["project"]["id"], "Change UI", self.task_id)

    def test_approved_projects_require_reopening(self):
        for task in self.store.details(self.project_id)["tasks"]:
            self.store.start_task(task["id"])
            self.store.submit_task(task["id"], "Review result", "Test-only evidence")
            self.store.review_task(task["id"], True, "Test acceptance")
        self.store.approve_project(self.project_id)
        with self.assertRaisesRegex(ValueError, "Reopen"):
            self.store.request_change(self.project_id, "Change the app")
        self.store.reopen_project(self.project_id, "Owner wants additional functionality")
        self.assertEqual(self.store.request_change(self.project_id, "New feature")["state"],
                         "queued_for_human_review")

    def test_chat_tool_only_queues_change(self):
        from modules.project_studio.module import Module
        module = Module({"base_dir": self.root})
        self.addCleanup(module.close)
        names = {x["name"] for x in module.tools()}
        self.assertEqual(names, {"list_app_projects", "app_project_status", "queue_app_change",
                                 "scan_apollo_core_suggestions",
                                 "list_apollo_core_suggestions",
                                 "propose_apollo_core_improvement"})
        with self.assertRaises(KeyError):
            module.run("approve_project", {"project_id": self.project_id})
        response = module.run("queue_app_change", {
            "project_id": self.project_id,
            "request": "Make this button larger",
            "task_id": self.task_id,
        })
        self.assertFalse(response["code_changed"])


if __name__ == "__main__":
    unittest.main()
