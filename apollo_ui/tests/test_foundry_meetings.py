"""Offline coordination tests: real sequential mocked model responses, persistence, safety."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from apollo_foundry_meetings import SPECIALISTS, current_requirements, hold_meeting, meeting_prompt
from apollo_project_studio import StudioStore


class FoundryMeetingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = StudioStore(self.root)
        self.addCleanup(self.store.close)
        self.pid = self.store.add_project("Casimir Lab", "Use PySide6 to simulate plates.")["project"]["id"]

    def complete_meeting(self):
        roles = [*SPECIALISTS, "manager"]
        return {
            "topic": "Casimir project kickoff",
            "turns": [{"role": role, "message": f"{role}: Use PySide6; test real files."}
                      for role in roles],
            "decisions": "manager: Use PySide6; test real files."
        }

    def test_sequential_meeting_uses_real_model_responses_and_cumulative_context(self):
        state = self.store.details(self.pid)
        seen = []
        progress = []
        def fake_read(request, timeout):
            payload = json.loads(request.data.decode())
            seen.append(payload["prompt"])
            return {"response": f"Responding for turn {len(seen)}"}
        with patch("apollo_foundry_meetings._read_model_response", side_effect=fake_read):
            result = hold_meeting(
                state, "qwen2.5-coder:7b", topic="Design the Casimir UI",
                on_message=lambda role, msg: progress.append((role, msg)))
        self.assertEqual(len(progress), 6)
        self.assertEqual([x["role"] for x in result["turns"]], [*SPECIALISTS, "manager"])
        self.assertIn("Responding for turn 1", seen[1])
        self.assertIn("Responding for turn 5", seen[-1])
        self.assertIn("Use PySide6", seen[0])
        self.assertEqual(result["decisions"], "Responding for turn 6")
        self.assertEqual(self.store.meetings(self.pid), [])  # No pretending persistence.

    def test_latest_owner_change_is_authoritative_in_meeting(self):
        self.store.request_change(self.pid, "No React, Python PySide6 desktop app only.")
        state = self.store.details(self.pid)
        self.assertIn("No React", current_requirements(state))
        prompt = meeting_prompt(state, "architect", [], topic="Architecture")
        self.assertIn("AUTHORITATIVE", prompt)
        self.assertIn("No React", prompt)

    def test_saved_meeting_survives_restart_and_feeds_project_context(self):
        number = self.store.save_meeting(self.pid, self.complete_meeting())
        self.assertGreater(number, 0)
        self.assertIn("Use PySide6", self.store.details(self.pid)["meeting_context"])
        self.store.close()
        self.addCleanup(lambda: None)
        reopened = StudioStore(self.root)
        self.addCleanup(reopened.close)
        self.assertEqual(len(reopened.meetings(self.pid)), 1)
        self.assertEqual(reopened.meetings(self.pid)[0]["turns"][0]["role"], "architect")
        self.assertEqual(reopened.details(self.pid)["meeting_context"],
                         "manager: Use PySide6; test real files.")

    def test_incomplete_or_fake_meeting_decisions_rejected(self):
        sample = self.complete_meeting()
        sample["turns"].pop()
        with self.assertRaises(ValueError):
            self.store.save_meeting(self.pid, sample)
        sample = self.complete_meeting()
        sample["decisions"] = "The team passed all tests."
        with self.assertRaises(ValueError):
            self.store.save_meeting(self.pid, sample)
        self.assertEqual(self.store.meetings(self.pid), [])

    def test_handoffs_are_factual_persisted_audit_events(self):
        task = self.store.details(self.pid)["tasks"][0]
        self.store.record_handoff(self.pid, "manager", "architect", "Assign design", task["id"])
        self.store.record_handoff(self.pid, "architect", "manager", "Draft submitted", task["id"])
        audit = self.store.audit(self.pid)
        self.assertEqual([e["kind"] for e in audit[:2]], ["handoff", "handoff"])
        self.assertIn("architect → manager", audit[0]["detail"])
        self.assertIn("manager → architect", audit[1]["detail"])
        other_pid = self.store.add_project("Other", "Other app")["project"]["id"]
        with self.assertRaises(ValueError):
            self.store.record_handoff(other_pid, "manager", "tester", "Wrong project", task["id"])

    def test_no_model_response_does_not_produce_fake_manager_decisions(self):
        def fake_read(request, timeout):
            payload = json.loads(request.data.decode())
            return {"response": "" if "YOUR ROLE: tester" in payload["prompt"] else "ok"}
        with patch("apollo_foundry_meetings._read_model_response", side_effect=fake_read):
            with self.assertRaisesRegex(RuntimeError, "tester returned an empty"):
                hold_meeting(self.store.details(self.pid), "qwen2.5-coder:7b")
        self.assertEqual(self.store.meetings(self.pid), [])

if __name__ == "__main__":
    unittest.main()
