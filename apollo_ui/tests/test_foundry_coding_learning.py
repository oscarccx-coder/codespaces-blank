"""Coding practice measures executed-source evidence; it cannot train weights."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apollo_foundry_learning import evidence_row, summarize_coding_progress
from apollo_project_studio import StudioStore
from modules.project_studio.module import Module

A = "a" * 64
B = "b" * 64
C = "c" * 64


def row(kind="docker-unit", status="passed", digest=A):
    return {"kind": kind, "status": status, "source_digest": digest}


def report(kind="unit", status="passed", digest=A, executed=True):
    return {"kind": "docker-" + kind, "status": status,
            "source_digest": digest,
            "executed_project_code": executed, "output": "Synthetic report"}


class EvidenceTests(unittest.TestCase):
    def test_no_success_claim_without_real_executed_fingerprinted_report(self):
        for payload in (
            report(executed=False),
            report(digest=None),
            report(digest="not-a-hash"),
            report(status="unavailable"),
            report(status="refused"),
        ):
            item = evidence_row(payload)
            self.assertEqual(item["status"], "unverified")
            self.assertIsNone(item["source_digest"])
        self.assertEqual(evidence_row(report())["status"], "passed")
        with self.assertRaises(ValueError):
            evidence_row({"kind": "docker-network", "status": "passed"})

    def test_cross_revision_repairs_and_regressions_are_not_invented(self):
        profile = summarize_coding_progress([
            row(status="failed", digest=A),
            row(status="passed", digest=A),  # rerunning identical source is NOT a repair
            row(status="passed", digest=B),  # a clean new revision; A already passed
            row(status="failed", digest=C),  # newer revision breaks previously passing source
            row(status="passed", digest=B),  # reversal repairs C
        ])
        unit = profile["skills"][0]
        self.assertEqual(unit["tested_runs"], 5)
        self.assertEqual(unit["passed_runs"], 3)
        self.assertEqual(unit["verified_repairs"], 1)
        self.assertEqual(unit["detected_regressions"], 1)

    def test_unverified_attempts_are_not_skill_failures(self):
        profile = summarize_coding_progress([
            {"kind": "docker-unit", "status": "unverified", "source_digest": None},
        ])
        unit = profile["skills"][0]
        self.assertEqual(unit["tested_runs"], 0)
        self.assertEqual(unit["failed_runs"], 0)
        self.assertEqual(unit["unverified_runs"], 1)
        self.assertIsNone(unit["pass_rate_percent"])
        self.assertIn("no verified evidence", profile["worker_guidance"])


class DurableLearningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = StudioStore(self.root)
        self.addCleanup(self.store.close)
        self.project = self.store.add_project("Coding clinic", "Test a multi-module app")
        self.pid = self.project["project"]["id"]

    def test_sandbox_evidence_persists_and_guides_worker_context(self):
        with patch("apollo_foundry_sandbox.run_sandbox", side_effect=[
            report(status="failed", digest=A),
            report(status="passed", digest=B),
            report(kind="ui", status="unavailable", digest=None, executed=False),
        ]):
            for kind in ("unit", "unit", "ui"):
                self.store.run_sandbox_tests(self.pid, kind)
        before = self.store.coding_progress()
        unit = before["skills"][0]
        self.assertEqual(unit["tested_runs"], 2)
        self.assertEqual(unit["verified_repairs"], 1)
        ui = before["skills"][1]
        self.assertEqual(ui["tested_runs"], 0)
        self.assertEqual(ui["unverified_runs"], 1)
        state = self.store.worker_state(self.pid)
        self.assertIn("Python logic", state["coding_learning_context"])
        other = StudioStore(self.root)
        try:
            self.assertEqual(other.coding_progress()["skills"][0]["verified_repairs"], 1)
        finally:
            other.close()

    def test_chat_practice_creates_tasks_not_model_execution(self):
        module = Module({"base_dir": self.root})
        try:
            progress = module.run("app_coding_progress", {})
            self.assertIn("next_practice", progress)
            before = len(module.store.list_projects())
            with patch("apollo_project_workers.draft_for_task") as draft:
                result = module.run("create_coding_practice", {})
            draft.assert_not_called()
            self.assertEqual(len(module.store.list_projects()), before + 1)
            self.assertEqual(len(result["tasks"]), 5)
            self.assertIn("tests", result["project"]["brief"])
        finally:
            module.close()


if __name__ == "__main__":
    unittest.main()
