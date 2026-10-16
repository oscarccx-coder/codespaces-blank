"""No-network Growth Lab -> Foundry mission smoke and refusal tests."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from apollo_growth_missions import GrowthMissionStore, intent
from apollo_growth import GrowthStore
from apollo_project_studio import StudioStore


def fake_draft(state, task_id):
    assert next(t for t in state["tasks"] if t["id"] == task_id)["state"] == "running"
    return json.dumps({
        "files": [
            {"path": "service.py", "content": "class AppService:\n    def calculate(self):\n        return 4\n"},
            {"path": "ui.py", "content": (
                "from service import AppService\n"
                "class AppWindow:\n"
                "    def __init__(self):\n"
                "        self.backend = AppService()\n"
                "        self.go_button = None\n"
                "        self.go_button.clicked.connect(self.on_calculate)\n"
                "    def on_calculate(self):\n"
                "        return self.backend.calculate()\n"
            )},
            {"path": "foundry.json", "content": json.dumps({
                "schema_version": 1,
                "ui": {"file": "ui.py", "class": "AppWindow", "bindings": [{
                    "widget": "go_button", "signal": "clicked",
                    "handler": "on_calculate", "backend_attribute": "backend",
                    "backend_file": "service.py", "backend_class": "AppService",
                    "backend_method": "calculate",
                }]}
            })},
        ],
        "summary": "Basic static UI/backend integration demo fixture only.",
    })


class GrowthMissionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "config.json").write_text(
            '{"version":"8.0.0","model":"qwen2.5-coder:7b"}', encoding="utf-8",
        )
        self.missions = GrowthMissionStore(self.root)
        self.addCleanup(self.missions.close)

    def test_recognises_explicit_choice_and_control_only(self):
        for phrase in ("begin Apollo project 1", "start option 2", "yes, begin project 3"):
            self.assertEqual(intent(phrase)[0], "begin")
        self.assertEqual(intent("status Apollo project"), ("status", None))
        self.assertEqual(intent("pause Apollo project"), ("pause", None))
        self.assertEqual(intent("continue Apollo project"), ("continue", None))
        for unrelated in (
            "make money for your upgrade", "hello", "yes", "start",
            "you need to learn AI", "Can we make money in future?",
            "begin Apache project 1", "begin Apollo project 4",
            "I saw begin Apollo project 1 in my notes",
        ):
            self.assertIsNone(intent(unrelated), unrelated)

    def test_offer_only_does_not_create_growth_work_or_foundry_app(self):
        offer = self.missions.offer()
        self.assertIn("begin Apollo project 1", offer)
        self.assertFalse(self.missions.snapshot()["exists"])
        growth = GrowthStore(self.root)
        studio = StudioStore(self.root)
        try:
            self.assertEqual(growth.list_work(), [])
            self.assertEqual(studio.list_projects(), [])
        finally:
            growth.close()
            studio.close()

    def test_begin_refused_without_prior_explicit_offer(self):
        with self.assertRaises(PermissionError):
            self.missions.begin(1, owner_confirmed=True)
        self.missions.offer()
        with self.assertRaises(PermissionError):
            self.missions.begin(1)
        self.assertFalse(self.missions.snapshot()["exists"])
        with self.assertRaises(ValueError):
            self.missions.begin(7, owner_confirmed=True)

    def test_authorized_begin_creates_real_project_then_verified_static_draft(self):
        self.missions.offer()
        initial = self.missions.begin(1, owner_confirmed=True)
        self.assertEqual(initial["state"], "READY_TO_DRAFT")
        self.assertGreater(initial["project_id"], 0)
        self.assertGreater(initial["work_id"], 0)
        growth = GrowthStore(self.root)
        studio = StudioStore(self.root)
        try:
            rows = growth.list_work()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["status"], "proposed")
            self.assertEqual(rows[0]["estimate_pence"], 0)
            project = studio.details(initial["project_id"])
            self.assertEqual(len(project["tasks"]), 5)
            self.assertIn("No personal data collection", project["project"]["brief"])
        finally:
            growth.close()
            studio.close()
        with self.assertRaises(ValueError):
            # A single offer must never create multiple Foundry projects.
            self.missions.begin(2, owner_confirmed=True)

        result = self.missions.run_one_step(owner_confirmed=True, draft=fake_draft)
        self.assertEqual(result["state"], "REVIEW_REQUIRED", result)
        self.assertIn("service.py", result["output"])
        self.assertIn("foundry.json", result["output"])
        self.assertEqual(result["tasks"]["review"], 1)
        self.assertEqual(result["tasks"]["accepted"], 0)
        self.assertTrue((Path(result["workspace"]) / "service.py").exists())
        self.assertIn("No revenue has been earned", self.missions.report())
        with self.assertRaises(ValueError):
            self.missions.run_one_step(owner_confirmed=True, draft=fake_draft)

    def test_failure_does_not_fabricate_success_and_owner_can_retry(self):
        self.missions.offer()
        self.missions.begin(3, owner_confirmed=True)
        def fail(_state, _id):
            raise RuntimeError("Ollama offline, no draft")
        blocked = self.missions.run_one_step(owner_confirmed=True, draft=fail)
        self.assertEqual(blocked["state"], "BLOCKED")
        self.assertIn("Ollama offline", blocked["error"])
        self.assertEqual(blocked["tasks"]["review"], 0)
        resumed = self.missions.resume(owner_confirmed=True)
        self.assertEqual(resumed["state"], "READY_TO_DRAFT")
        completed = self.missions.run_one_step(owner_confirmed=True, draft=fake_draft)
        self.assertEqual(completed["state"], "REVIEW_REQUIRED")

    def test_pause_requires_new_authorization_and_keeps_evidence(self):
        self.missions.offer()
        self.missions.begin(2, owner_confirmed=True)
        paused = self.missions.pause()
        self.assertEqual(paused["state"], "PAUSED")
        with self.assertRaises(PermissionError):
            self.missions.run_one_step(owner_confirmed=True, draft=fake_draft)
        with self.assertRaises(PermissionError):
            self.missions.resume()
        self.missions.resume(owner_confirmed=True)
        done = self.missions.run_one_step(owner_confirmed=True, draft=fake_draft)
        self.assertEqual(done["state"], "REVIEW_REQUIRED")

    def test_no_model_response_without_authorization(self):
        self.missions.offer()
        self.missions.begin(1, owner_confirmed=True)
        def forbidden(*a):
            raise AssertionError("Unauthorized code generation must never be called")
        with self.assertRaises(PermissionError):
            self.missions.run_one_step(draft=forbidden)


if __name__ == "__main__":
    unittest.main()
