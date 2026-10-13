"""Foundry stress and recovery tests: real SQLite, multi-thread tasks and refusal history.

This suite is intentionally offline. It does not invoke generated code or
require Docker/voice models. Uses fresh private temporary workspaces.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from apollo_project_studio import MAX_PROJECTS, MAX_TASKS, StudioStore


class FoundryStressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = StudioStore(self.root)
        self.addCleanup(self.store.close)
        state = self.store.add_project("Load Test App", "Stress tasks, reports, and revisions.")
        self.pid = state["project"]["id"]
        self.first = state["tasks"][0]["id"]

    def test_all_project_slots_persist_and_next_is_rejected(self):
        # Use the real MAX_PROJECTS and real on-disk DB, not a simulated limit.
        for i in range(MAX_PROJECTS - 1):
            self.store.add_project(f"App {i}", "Simple project")
        self.assertEqual(len(self.store.list_projects()), MAX_PROJECTS)
        with self.assertRaisesRegex(ValueError, "Project limit"):
            self.store.add_project("Over max", "Should not create a folder")
        self.assertEqual(len(self.store.list_projects()), MAX_PROJECTS)
        self.assertEqual(self.store.conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        reopened = StudioStore(self.root)
        try:
            self.assertEqual(len(reopened.list_projects()), MAX_PROJECTS)
            self.assertEqual(len(reopened.details(self.pid)["tasks"]), 5)
        finally:
            reopened.close()

    def test_task_limit_stops_all_assignment_routes_without_partial_edits(self):
        for number in range(MAX_TASKS - 5):
            self.store.add_subtask(
                self.first, f"Child {number}", "One bounded subtask", "tester"
            )
        self.assertEqual(len(self.store.details(self.pid)["tasks"]), MAX_TASKS)
        issue = self.store.report_issue(self.pid, "Fix failure", "Needs an assigned task")
        with self.assertRaisesRegex(ValueError, "task limit"):
            self.store.assign_issue(issue["id"])
        with self.assertRaisesRegex(ValueError, "Task limit"):
            self.store.request_change(self.pid, "Modify UI", self.first)
        with self.assertRaisesRegex(ValueError, "task limit"):
            self.store.add_subtask(self.first, "Extra", "Over cap", "tester")
        self.assertEqual(len(self.store.details(self.pid)["tasks"]), MAX_TASKS)
        self.assertEqual(self.store.issue(issue["id"])["state"], "open")
        self.assertEqual(self.store.conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_bulk_manager_subtasks_refuse_partial_insert_at_limit(self):
        # A batch of eight must not half-write when only four slots are left.
        for number in range(MAX_TASKS - 9):
            self.store.add_subtask(self.first, f"Child {number}", "Instructions", "tester")
        original = len(self.store.details(self.pid)["tasks"])
        self.assertEqual(original, MAX_TASKS - 4)
        proposal = [
            {"title": f"Plan {i}", "brief": "Details", "role": "implementer"}
            for i in range(8)
        ]
        with self.assertRaisesRegex(ValueError, "limit"):
            self.store.add_subtasks(self.first, proposal)
        self.assertEqual(len(self.store.details(self.pid)["tasks"]), original)

    def test_concurrent_project_writes_are_consistent(self):
        projects = [self.store.add_project(f"Worker app {i}", "Independent task") for i in range(9)]
        ids = [p["tasks"][0]["id"] for p in projects]

        def run_one(tid):
            self.store.start_task(tid)
            self.store.submit_task(tid, f"Draft {tid}", "Test data")
            return self.store.review_task(tid, True, "Manually simulated review")["state"]

        with ThreadPoolExecutor(max_workers=6) as executor:
            outcomes = list(executor.map(run_one, ids))
        self.assertEqual(outcomes, ["accepted"] * len(ids))
        for project in projects:
            self.assertEqual(
                self.store.details(project["project"]["id"])["tasks"][0]["state"],
                "accepted",
            )
        self.assertEqual(self.store.conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_same_project_rejects_two_simultaneous_workers(self):
        tids = [t["id"] for t in self.store.details(self.pid)["tasks"][:2]]
        def attempt(tid):
            try:
                self.store.start_task(tid)
                return "started"
            except ValueError:
                return "blocked"
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(attempt, tids))
        self.assertEqual(sorted(results), ["blocked", "started"])
        self.assertEqual(sum(t["state"] == "running" for t in self.store.details(self.pid)["tasks"]), 1)

    def test_query_indexes_and_isolation(self):
        actual = {x[1] for x in self.store.conn.execute("PRAGMA index_list('test_runs')")}
        self.assertIn("idx_foundry_tests_project_kind", actual)
        query = self.store.conn.execute(
            "EXPLAIN QUERY PLAN SELECT id FROM test_runs WHERE project_id=? "
            "AND kind IN ('docker-unit','docker-gui') ORDER BY id DESC LIMIT 1",
            (self.pid,),
        ).fetchall()
        plan = " ".join(str(part) for row in query for part in row)
        self.assertIn("idx_foundry_tests_project_kind", plan)

    def test_sandbox_bad_source_is_saved_as_refused_not_crash(self):
        folder = self.store.project_folder(self.pid)
        self.store.create_starter_ui(self.pid)
        # A symlinked file must be refused without ever starting a container.
        outside = self.root / "outside.py"
        outside.write_text("raise AssertionError('never execute')")
        try:
            (folder / "escape.py").symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("Creating symlinks not supported on this runner")
        with patch("apollo_foundry_sandbox.availability", return_value={"ok": True}):
            with patch("apollo_foundry_sandbox._execute_bounded") as execute:
                report = self.store.run_sandbox_tests(self.pid, "unit", docker_bin="docker")
        self.assertEqual(report["status"], "refused", report)
        self.assertFalse(report["executed_project_code"])
        execute.assert_not_called()
        self.assertEqual(self.store.sandbox_history(self.pid)[0]["status"], "refused")

    def test_refused_execution_does_not_approve_or_modify_tasks(self):
        before = self.store.details(self.pid)
        with patch("apollo_foundry_sandbox.run_sandbox",
                   side_effect=ValueError("Deliberately malformed source")):
            report = self.store.run_sandbox_tests(self.pid, "gui", docker_bin="docker")
        self.assertEqual(report["status"], "refused")
        self.assertFalse(report["executed_project_code"])
        self.assertEqual(before["tasks"], self.store.details(self.pid)["tasks"])
        self.assertEqual(len(self.store.sandbox_history(self.pid)), 1)

    def test_review_history_is_limited_by_kind_and_persists(self):
        with patch("apollo_foundry_sandbox.run_sandbox") as fake:
            for i in range(37):
                fake.return_value = {
                    "kind": "docker-unit", "phase": "Foundry Sandbox", "status": "failed",
                    "created_at": f"test-{i}", "executed_project_code": False,
                    "passed_ui_interactions": False, "image": "test", "reason": "synthetic",
                    "output": str(i),
                }
                self.store.run_sandbox_tests(self.pid, "unit", docker_bin="docker")
        self.assertEqual(len(self.store.sandbox_history(self.pid, 30)), 30)
        self.assertEqual(self.store.sandbox_history(self.pid, 1)[0]["report"]["output"], "36")
        self.assertEqual(
            self.store.conn.execute("SELECT COUNT(*) FROM test_runs WHERE project_id=?", (self.pid,)).fetchone()[0],
            30,
        )


if __name__ == "__main__":
    unittest.main()
