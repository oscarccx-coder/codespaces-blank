"""Foundry workflow v2: dependency dispatch, real code context, safe rollback.

All tests are offline; no model, host-generated code or Docker is executed.
"""
import json
from pathlib import Path
import tempfile
import unittest

from apollo_foundry_artifacts import save_bundle
from apollo_foundry_workspace import (
    read_workspace_context, create_checkpoint, list_checkpoints, restore_checkpoint,
)
from apollo_project_studio import StudioStore
from apollo_project_workers import validate_subtask_plan


class DependencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = StudioStore(self.root)
        self.addCleanup(self.store.close)
        self.state = self.store.add_project("Graphing app", "Create a Python graphing app")
        self.pid = self.state["project"]["id"]
        self.parent = self.state["tasks"][0]["id"]

    def test_additive_dependency_migration_and_ready_dispatch(self):
        self.assertIsNotNone(self.store.conn.execute(
            "SELECT name FROM sqlite_master WHERE name='task_dependencies'").fetchone())
        plan = [
            {"title": "Define API", "brief": "Agree on interfaces", "role": "architect"},
            {"title": "Implement", "brief": "Create working code", "role": "implementer",
             "depends_on": [0]},
            {"title": "Test", "brief": "Run real tests", "role": "tester",
             "depends_on": [0, 1]},
        ]
        tasks = self.store.add_subtasks(self.parent, plan)
        state = self.store.details(self.pid)
        lookup = {t["id"]: t for t in state["tasks"]}
        self.assertEqual(lookup[tasks[2]["id"]]["depends_on"],
                         [tasks[0]["id"], tasks[1]["id"]])
        self.assertEqual(lookup[tasks[2]["id"]]["blocked_by"],
                         [tasks[0]["id"], tasks[1]["id"]])
        with self.assertRaisesRegex(ValueError, "dependencies"):
            self.store.start_task(tasks[1]["id"])
        self.store.start_task(tasks[0]["id"])
        self.store.submit_task(tasks[0]["id"], "Architecture", "Review draft")
        self.store.start_task(tasks[1]["id"])
        self.store.submit_task(tasks[1]["id"], "Implemented", "Static checks passed")
        self.store.start_task(tasks[2]["id"])
        self.assertEqual(self.store._task(tasks[2]["id"])["state"], "running")

    def test_plan_rejects_cycles_forward_references_and_duplicates(self):
        for deps in ([1], [-1], [False], [0, 0]):
            with self.subTest(deps=deps):
                with self.assertRaisesRegex(ValueError, "dependencies"):
                    validate_subtask_plan({"tasks": [
                        {"title": "A", "brief": "Do A", "role": "architect"},
                        {"title": "B", "brief": "Do B", "role": "tester",
                         "depends_on": deps},
                    ]})
        with self.assertRaisesRegex(ValueError, "Dependencies"):
            self.store.add_subtasks(self.parent, [
                {"title": "A", "brief": "Do A", "role": "architect",
                 "depends_on": [0]},
            ])

    def test_old_manager_plan_shape_still_works(self):
        plan = validate_subtask_plan({"tasks": [
            {"title": "A", "brief": "Do A", "role": "architect"},
        ]})
        self.assertEqual(set(plan[0]), {"title", "brief", "role"})
        self.assertEqual(self.store.add_subtasks(self.parent, plan)[0]["state"], "todo")


class WorkspaceCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = StudioStore(self.root)
        self.addCleanup(self.store.close)
        project = self.store.add_project("Casimir app", "Python simulator")
        self.pid = project["project"]["id"]
        self.folder = self.store.project_folder(self.pid)
        self.storage = self.root / "storage"
        save_bundle(self.folder, {"files": [
            {"path": "service.py", "content": "def calculate():\n    return 1\n"},
            {"path": "launch.py", "content": "print('not executed')\n"},
        ], "summary": "First version"})

    def test_worker_context_contains_actual_code_not_private_untracked_files(self):
        (self.folder / "private-notes.txt").write_text("PRIVATE_MARKER_8765")
        state = self.store.worker_state(self.pid)
        self.assertIn("return 1", state["source_context"])
        self.assertIn("FILE service.py", state["source_context"])
        self.assertNotIn("PRIVATE_MARKER_8765", state["source_context"])
        self.assertNotIn("PRIVATE_MARKER_8765", read_workspace_context(self.folder))

    def test_checkpoint_restore_preserves_newer_untracked_and_generated_files(self):
        original = create_checkpoint(self.folder, self.storage, self.pid, label="working")
        save_bundle(self.folder, {"files": [
            {"path": "service.py", "content": "def calculate():\n    return 2\n"},
            {"path": "ui.py", "content": "class UI: pass\n"},
        ], "summary": "Second version"})
        (self.folder / "private-notes.txt").write_text("Do not delete")
        result = restore_checkpoint(self.folder, self.storage, self.pid, original["id"])
        self.assertIn("return 1", (self.folder / "service.py").read_text())
        self.assertTrue((self.folder / "ui.py").exists())
        self.assertEqual((self.folder / "private-notes.txt").read_text(), "Do not delete")
        self.assertIn("ui.py", json.loads(
            (self.folder / ".foundry-generated.json").read_text()))
        self.assertIn(result["backup_id"], [cp["id"] for cp in list_checkpoints(
            self.storage, self.pid)])
        restore_checkpoint(self.folder, self.storage, self.pid, result["backup_id"])
        self.assertIn("return 2", (self.folder / "service.py").read_text())

    def test_manual_edit_prevents_rollback(self):
        checkpoint = create_checkpoint(self.folder, self.storage, self.pid)
        (self.folder / "service.py").write_text("MANUAL CHANGE\n")
        with self.assertRaisesRegex(ValueError, "Manual edits"):
            restore_checkpoint(self.folder, self.storage, self.pid, checkpoint["id"])
        self.assertEqual((self.folder / "service.py").read_text(), "MANUAL CHANGE\n")

    def test_tampered_checkpoint_refused(self):
        checkpoint = create_checkpoint(self.folder, self.storage, self.pid)
        directory = self.storage / "foundry" / "checkpoints" / f"app-{self.pid:04d}"
        (directory / checkpoint["id"] / "service.py").write_text("tampered")
        with self.assertRaisesRegex(ValueError, "integrity"):
            restore_checkpoint(self.folder, self.storage, self.pid, checkpoint["id"])

    def test_invalid_checkpoint_id_refused(self):
        with self.assertRaisesRegex(ValueError, "Invalid checkpoint"):
            restore_checkpoint(self.folder, self.storage, self.pid, "../other")


if __name__ == "__main__":
    unittest.main()
