"""Project Studio workflow, persistence, denial and crash recovery tests."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from apollo_project_studio import StudioStore
from apollo_project_workers import draft_for_task, model_from_config


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.store = StudioStore(self.root)
        self.addCleanup(self.store.close)
        state = self.store.add_project("Test App", "Build a local calculator for learning")
        self.pid = state["project"]["id"]
        self.first = state["tasks"][0]["id"]

    def test_project_creation_rolls_back_when_folder_is_reserved(self):
        # The next project ID is sequential; an attacker-created directory
        # must not be adopted or overwritten.
        stolen = self.root / "workspace" / "app_development" / "app-0002-unsafe"
        stolen.mkdir(parents=True)
        original = stolen / "PROJECT.md"
        original.write_text("EXISTING OWNER DATA", encoding="utf-8")
        before = len(self.store.list_projects())
        with self.assertRaises(FileExistsError):
            self.store.add_project("Unsafe", "Do not overwrite")
        self.assertEqual(original.read_text(encoding="utf-8"), "EXISTING OWNER DATA")
        self.assertEqual(len(self.store.list_projects()), before)

    def test_task_limit_applies_to_issue_fix_assignment(self):
        issue = self.store.report_issue(self.pid, "Stop crashing", "A reproducible bug")
        with patch("apollo_project_studio.MAX_TASKS", 5):
            with self.assertRaisesRegex(ValueError, "task limit"):
                self.store.assign_issue(issue["id"])
        self.assertEqual(self.store.issue(issue["id"])["state"], "open")
        self.assertEqual(len(self.store.details(self.pid)["tasks"]), 5)

    def test_subtasks_cannot_be_added_to_active_worker(self):
        self.store.start_task(self.first)
        with self.assertRaisesRegex(ValueError, "not-started"):
            self.store.add_subtask(self.first, "Late plan", "This should be rejected", "tester")

    def test_issue_closure_does_not_repeat_or_change_approved_projects(self):
        issue = self.store.report_issue(self.pid, "Fix", "Review first")
        assigned = self.store.assign_issue(issue["id"])
        with self.assertRaisesRegex(ValueError, "reviewer"):
            self.store.close_issue(issue["id"])
        self.store.start_task(assigned["id"])
        self.store.submit_task(assigned["id"], "Draft", "Tested")
        self.store.review_task(assigned["id"], True, "Accepted")
        self.store.close_issue(issue["id"])
        with self.assertRaisesRegex(ValueError, "Only assigned"):
            self.store.close_issue(issue["id"])

    def test_projects_and_workspaces_persist(self):
        saved = self.store.details(self.pid)
        self.assertEqual(len(saved["tasks"]), 5)
        directory = self.root / "workspace" / "app_development" / saved["project"]["folder"]
        self.assertTrue((directory / "PROJECT.md").exists())
        other = StudioStore(self.root)
        try:
            self.assertEqual(other.details(self.pid)["project"]["title"], "Test App")
        finally:
            other.close()

    def test_interrupted_job_can_be_recovered_and_retried(self):
        self.store.start_task(self.first)
        self.assertEqual(self.store.recover_interrupted_tasks(self.pid), 1)
        self.assertEqual(self.store._task(self.first)["state"], "blocked")
        self.assertEqual(self.store.recover_interrupted_tasks(self.pid), 0)
        self.store.reopen_task(self.first, "User reviewed interruption")
        self.store.start_task(self.first)
        self.store.submit_task(self.first, "Retried draft", "Re-review needed")
        self.assertEqual(self.store._task(self.first)["state"], "review")
        self.assertTrue(any(x["kind"] == "interrupted" for x in self.store.audit(self.pid)))

    def test_subtasks_and_review_not_fabricated(self):
        subtask = self.store.add_subtask(self.first, "Design API", "Define JSON inputs and errors.", "architect")
        self.assertEqual(subtask["parent_id"], self.first)
        self.store.start_task(self.first)
        self.store.submit_task(self.first, "Draft design", "A draft, not a passing test.")
        with self.assertRaisesRegex(ValueError, "subtasks"):
            self.store.review_task(self.first, True, "Looks reasonable")
        self.store.start_task(subtask["id"])
        self.store.submit_task(subtask["id"], "API contract", "Reviewer to inspect")
        self.store.review_task(subtask["id"], True, "Checked the contract")
        self.store.review_task(self.first, True, "Parent now complete")
        self.assertEqual(self.store.details(self.pid)["tasks"][0]["state"], "accepted")

    def test_only_one_worker_per_project(self):
        ids = [t["id"] for t in self.store.details(self.pid)["tasks"]]
        self.store.start_task(ids[0])
        with self.assertRaisesRegex(ValueError, "Only one worker"):
            self.store.start_task(ids[1])
        self.store.fail_task(ids[0], "Offline model unavailable")
        self.assertEqual(self.store._task(ids[0])["state"], "blocked")
        self.store.reopen_task(ids[0], "Retry after installing model")
        self.assertEqual(self.store._task(ids[0])["state"], "todo")

    def test_rework_and_issue_closure_need_real_review(self):
        issue = self.store.report_issue(self.pid, "Crashes on start", "Reproduce failed launch in sandbox")
        with self.assertRaisesRegex(ValueError, "Only assigned"):
            self.store.close_issue(issue["id"])
        fix = self.store.assign_issue(issue["id"])
        self.assertEqual(fix["role"], "implementer")
        self.store.start_task(fix["id"])
        self.store.submit_task(fix["id"], "Proposed fix", "No test yet")
        self.store.review_task(fix["id"], False, "Need a failing test and rerun")
        self.store.start_task(fix["id"])
        self.store.submit_task(fix["id"], "Updated proposal", "Recorded synthetic test run")
        self.store.review_task(fix["id"], True, "Review complete")
        self.assertEqual(self.store.close_issue(issue["id"])["state"], "closed")
        self.assertEqual(self.store._task(fix["id"])["iteration"], 2)

    def test_project_cannot_auto_approve(self):
        with self.assertRaisesRegex(ValueError, "Every worker"):
            self.store.approve_project(self.pid)
        for item in self.store.details(self.pid)["tasks"]:
            tid = item["id"]
            self.store.start_task(tid)
            self.store.submit_task(tid, "Synthetic role draft", "Reviewed in test")
            self.store.review_task(tid, True, "Synthetic human approval")
        self.assertEqual(self.store.approve_project(self.pid)["state"], "approved")
        with self.assertRaisesRegex(ValueError, "Reopen the project"):
            self.store.report_issue(self.pid, "Bug", "An untested issue")
        self.store.reopen_project(self.pid, "New issue needs attention")
        self.assertEqual(self.store.report_issue(self.pid, "Bug", "New issue")["state"], "open")
        with self.assertRaisesRegex(ValueError, "issues"):
            self.store.approve_project(self.pid)

    def test_untrusted_input_and_limits(self):
        with self.assertRaises(ValueError):
            self.store.add_subtask(self.first, "x", "y", "administrator")
        sub = self.store.add_subtask(self.first, "Safe", "Review", "architect")
        with self.assertRaisesRegex(ValueError, "Maximum"):
            self.store.add_subtask(sub["id"], "Nested", "No", "tester")
        project = self.store.details(self.pid)["project"]
        self.assertFalse(Path(project["folder"]).is_absolute())
        self.assertNotIn("..", project["folder"])

    def test_model_draft_is_local_bounded_and_not_auto_executed(self):
        (self.root / "config.json").write_text('{"model":"qwen2.5-coder:7b"}')
        self.assertEqual(model_from_config(self.root), "qwen2.5-coder:7b")
        self.store.start_task(self.first)
        state = self.store.details(self.pid)

        class DummyResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, count):
                return json.dumps({"response": "A safe unexecuted design draft"}).encode("utf-8")

        class DummyOpener:
            def open(self, req, timeout):
                self_req = req
                assert req.full_url == "http://127.0.0.1:11434/api/generate"
                payload = json.loads(req.data)
                assert payload["stream"] is False
                assert "tools" not in payload
                return DummyResponse()

        with patch("apollo_project_workers.urllib.request.build_opener", return_value=DummyOpener()):
            # No external network access, only a mocked fixed localhost endpoint.
            draft = draft_for_task(state, self.first, model_from_config(self.root))
        self.assertIn("unexecuted", draft)
        self.assertEqual(self.store._task(self.first)["state"], "running")
        self.store.submit_task(self.first, draft, "Mock draft: not reviewed")
        self.assertEqual(self.store._task(self.first)["state"], "review")

    def test_tool_interface_excludes_mutating_privileged_actions(self):
        from modules.project_studio.module import Module
        module = Module({"validation": True, "base_dir": self.root})
        try:
            self.assertTrue(module.self_test())
            names = {t["name"] for t in module.tools()}
            self.assertEqual(names, {"create_app_project", "app_project_files", "app_coding_progress", "create_coding_practice", "list_app_projects", "app_project_status", "queue_app_change"})
            with self.assertRaises(KeyError):
                module.run("approve_project", {"project_id": 1})
        finally:
            module.close()


if __name__ == "__main__":
    unittest.main()
