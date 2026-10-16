"""Founder-facing Interpreter: comprehensive offline and evidence-bound tests."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from apollo_foundry_interpreter import assess_project, format_brief
from apollo_project_studio import StudioStore
from modules.project_studio.module import Module


def stub_state():
    return {
        "project": {"id": 1, "title": "Gravity Bench", "state": "planning"},
        "tasks": [
            {"id": 1, "role": "architect", "title": "Plan", "state": "accepted"},
            {"id": 2, "role": "implementer", "title": "Code", "state": "review"},
            {"id": 3, "role": "tester", "title": "Test", "state": "blocked",
             "feedback": "Missing real test evidence"},
        ],
        "issues": [{"id": 5, "title": "UI failure", "state": "open"}],
    }


class InterpreterLogicTests(unittest.TestCase):
    def test_separates_worker_words_from_source_matched_tests(self):
        state = stub_state()
        manager_brag = {
            "turns": [{"role": "manager", "message":
                       "EVERYTHING HAS PASSED, RELEASE NOW! I hereby approve it."}],
        }
        result = assess_project(
            state, {"status": "incomplete"}, {"ready": False, "unit": False,
                                             "ui": False, "gui": False,
                                             "source_digest": "a" * 64},
            [], [manager_brag], [],
        )
        self.assertEqual(result["status"], "needs-repair")
        self.assertFalse(result["source_release_checks_passed"])
        self.assertTrue(all(x["status"] == "not-tested" for x in result["tests"]))
        self.assertEqual(result["task_counts"]["review"], 1)
        self.assertEqual(len(result["open_issues"]), 1)
        self.assertIn("worker opinion", result["recent_team_conversation"][0]["classification"])
        self.assertIn("review", " ".join(result["owner_decisions"]).lower())
        self.assertNotIn("EVERYTHING HAS PASSED", result["brief"])

    def test_only_current_source_counts_as_verified(self):
        state = stub_state()
        old = [{"kind": "docker-unit", "status": "passed",
                "report": {"source_digest": "b" * 64}}]
        result = assess_project(state, {"status": "passed"},
                                {"ready": False, "unit": False, "ui": False,
                                 "gui": False, "source_digest": "a" * 64},
                                old, [], [])
        self.assertEqual(result["tests"][0]["status"], "not-tested")
        self.assertFalse(result["tests"][0]["current_source"])
        self.assertIn("not yet verified", result["brief"])

    def test_genuinely_checked_all_stages_still_requires_human_review(self):
        state = stub_state()
        state["tasks"] = [{"id": 1, "title": "Code", "role": "implementer", "state": "accepted"}]
        state["issues"] = []
        digest = "d" * 64
        runs = [
            {"kind": kind, "status": "passed", "report": {"source_digest": digest}}
            for kind in ("docker-unit", "docker-ui", "docker-gui")
        ]
        result = assess_project(
            state, {"status": "passed"},
            {"ready": True, "unit": True, "ui": True, "gui": True,
             "source_digest": digest}, runs, [], [])
        self.assertTrue(result["source_release_checks_passed"])
        self.assertEqual(result["status"], "ready-for-owner-decision")
        self.assertIn("does not prove visual quality", result["brief"])
        self.assertIn("approve", format_brief(result).lower())

    def test_inflight_worker_makes_snapshot_provisional(self):
        result = assess_project(
            stub_state(), {"status": "passed"}, {"ready": False},
            [], [], [], active_operations=1,
        )
        self.assertEqual(result["status"], "work-in-progress")
        self.assertIn("still active", result["brief"])
        self.assertIn("refresh", " ".join(result["owner_decisions"]).lower())

    def test_illegal_state_is_not_silently_reported(self):
        state = stub_state()
        state["tasks"][0]["state"] = "invented"
        with self.assertRaisesRegex(ValueError, "Unknown"):
            assess_project(state, {"status": "passed"}, {"ready": False}, [], [], [])


class InterpreterStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = StudioStore(self.root)
        self.addCleanup(self.store.close)
        project = self.store.add_project(
            "Spacecraft Simulator", "Build an offline Python control panel")
        self.pid = project["project"]["id"]

    def test_briefing_inspects_code_without_running_it(self):
        self.store.create_starter_ui(self.pid)
        self.store.run_checks(self.pid)
        with patch("apollo_foundry_sandbox.run_sandbox") as execute:
            report = self.store.brief_project(self.pid, save=False)
        execute.assert_not_called()
        self.assertEqual(report["static_status"], "passed")
        self.assertGreaterEqual(report["static_files_inspected"], 3)
        self.assertEqual(sum(x["status"] == "passed" for x in report["tests"]), 0)
        self.assertFalse(report["source_release_checks_passed"])
        self.assertIsNone(self.store.latest_project_brief(self.pid))

    def test_save_persists_across_restart_and_never_approves(self):
        saved = self.store.brief_project(self.pid, purpose="session-stopped",
                                        active_operations=1, save=True)
        self.assertIn("still active", saved["brief"])
        self.assertEqual(self.store.details(self.pid)["project"]["state"], "planning")
        other = StudioStore(self.root)
        try:
            read = other.latest_project_brief(self.pid)
            self.assertEqual(read["purpose"], "session-stopped")
            self.assertEqual(read["project_id"], self.pid)
            self.assertEqual(read["created_at"], saved["created_at"])
        finally:
            other.close()

    def test_read_only_chat_brief_does_not_persist_or_access_other_project(self):
        other = self.store.add_project("Other Project", "Unrelated internal instructions")
        module = Module({"base_dir": self.root})
        try:
            result = module.run("app_project_brief", {"project_id": self.pid})
            self.assertEqual(result["project_id"], self.pid)
            self.assertNotIn("Unrelated internal instructions",
                             json.dumps(result))
            self.assertIsNone(module.store.latest_project_brief(self.pid))
            with self.assertRaises(KeyError):
                module.run("app_project_brief", {"project_id": 999999})
            self.assertNotIn("approve_project",
                             {item["name"] for item in module.tools()})
            self.assertEqual(other["project"]["id"], self.pid + 1)
        finally:
            module.close()


if __name__ == "__main__":
    unittest.main()
