"""Qt-free checks for Apollo's updated project and updater interfaces."""
import ast
from pathlib import Path
import unittest

from project_studio_view_model import project_metrics, task_actions, issue_actions

ROOT = Path(__file__).resolve().parents[1]


class ProjectPresentationTests(unittest.TestCase):
    def setUp(self):
        self.project = {
            "project": {"state": "planning"},
            "tasks": [
                {"id": 1, "state": "todo", "parent_id": None},
                {"id": 2, "state": "accepted", "parent_id": None},
                {"id": 3, "state": "review", "parent_id": 1},
                {"id": 4, "state": "blocked", "parent_id": None},
            ],
            "issues": [{"id": 8, "state": "in_progress", "assigned_task": 2}],
        }

    def test_progress_counts_are_from_real_record_states(self):
        m = project_metrics(self.project)
        self.assertEqual(m["total"], 4)
        self.assertEqual(m["accepted"], 1)
        self.assertEqual(m["review"], 1)
        self.assertEqual(m["blocked"], 1)
        self.assertEqual(m["open_issues"], 1)
        self.assertEqual(m["percent"], 25)
        self.assertEqual(project_metrics({"tasks": [], "issues": []})["percent"], 0)

    def test_contextual_actions_never_enable_without_selection(self):
        self.assertFalse(any(task_actions(None, self.project).values()))
        self.assertFalse(any(issue_actions(None, self.project).values()))

    def test_drafts_and_reviews_only_at_correct_stage(self):
        todo = task_actions(self.project["tasks"][0], self.project)
        review = task_actions(self.project["tasks"][2], self.project)
        blocked = task_actions(self.project["tasks"][3], self.project)
        self.assertTrue(todo["draft"])
        self.assertTrue(todo["subtask"])
        self.assertFalse(todo["accept"])
        self.assertFalse(review["draft"])
        self.assertTrue(review["accept"])
        self.assertFalse(review["subtask"])
        self.assertTrue(blocked["retry"])
        self.assertFalse(blocked["draft"])

    def test_running_worker_and_approved_project_lock_mutations(self):
        self.project["tasks"][0]["state"] = "running"
        self.assertFalse(task_actions(self.project["tasks"][3], self.project)["draft"])
        self.project["project"]["state"] = "approved"
        self.assertFalse(any(task_actions(self.project["tasks"][2], self.project).values()))
        self.assertFalse(any(issue_actions(self.project["issues"][0], self.project).values()))

    def test_fix_requires_accepted_task(self):
        issue = self.project["issues"][0]
        self.assertTrue(issue_actions(issue, self.project)["close"])
        self.project["tasks"][1]["state"] = "review"
        self.assertFalse(issue_actions(issue, self.project)["close"])

    def test_new_ui_source_parses_and_contains_real_wiring(self):
        paths = ("main.py", "modules/project_studio/module.py", "modules/update_manager/module.py")
        texts = {}
        for path in paths:
            data = (ROOT / path).read_text(encoding="utf-8")
            ast.parse(data, filename=path)
            texts[path] = data
        studio = texts["modules/project_studio/module.py"]
        for phrase in (
            'project_search.textChanged.connect',
            'def update_actions():',
            'def refresh_projects(select_id=None):',
            'task_tree.setCurrentItem(nodes[previous_task])',
            'completion.setValue(metrics["percent"])',
            'issue_table.itemSelectionChanged.connect(update_actions)',
            'button.setEnabled(choices[action])',
        ):
            self.assertIn(phrase, studio)
        updates = texts["modules/update_manager/module.py"]
        for phrase in (
            'QProgressBar()', 'transferred = Signal(int, int)',
            'signals.transferred.connect(update_download_progress)',
            'check_btn.setText("Check only")',
            'combined_btn = QPushButton("Update Apollo")',
        ):
            self.assertIn(phrase, updates)
        main = texts["main.py"]
        self.assertIn('quick_projects.clicked.connect(lambda: self.open_module_app("project_studio"))', main)
        self.assertIn('quick_updates.clicked.connect(lambda: self.open_module_app("update_manager"))', main)


if __name__ == "__main__":
    unittest.main()
