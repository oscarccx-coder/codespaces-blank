"""Apollo v8 learning: offline, permission and evidence regression checks."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from apollo_learning_v8 import LearningController, knowledge_query
from apollo_reasoning import ReasoningStore
from modules.reasoning_director.module import Module


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = ReasoningStore(self.tmp.name)
        self.addCleanup(self.store.close)
        self.learning = LearningController(self.tmp.name, self.store)
        self.topic = self.store.propose_topic(
            "Casimir effect", "Study measurable quantum vacuum force experiments"
        )
        self.question_id = self.store.questions_for(self.topic["id"])[0]["id"]

    def test_subject_lookup_in_chats(self):
        self.assertEqual(knowledge_query("What is the Casimir effect?"), "the Casimir effect")
        self.assertEqual(knowledge_query("What can XTTS do for me?"), "XTTS")
        self.assertEqual(knowledge_query("Tell me about Python"), "Python")
        self.assertEqual(knowledge_query("How can a Raspberry Pi help me?"), "a Raspberry Pi")

    def test_defaults_to_no_automatic_web_access(self):
        self.assertEqual(self.learning.status()["mode"], "manual")
        self.assertEqual(self.learning.reserve_due()["action"], "disabled")

    def test_scheduled_reminders_are_persistent_and_bounded(self):
        start = datetime(2026, 11, 1, tzinfo=timezone.utc)
        state = self.learning.configure("remind", interval_hours=2, review_days=14, now=start)
        self.assertEqual(state["next_run"], "2026-11-01T02:00:00+00:00")
        self.assertEqual(self.learning.reserve_due(start + timedelta(hours=1))["action"], "waiting")
        due = self.learning.reserve_due(start + timedelta(hours=2))
        self.assertEqual(due["action"], "reminder")
        self.assertIn("Casimir", due["question"]["topic"])
        self.assertEqual(self.learning.reserve_due(start + timedelta(hours=2))["action"], "waiting")
        restored = LearningController(self.tmp.name, self.store)
        self.assertEqual(restored.status()["mode"], "remind")
        self.assertEqual(restored.status()["interval_hours"], 2)

    def test_rejects_invalid_schedule(self):
        for mode, hours, days in [("anything", 1, 7), ("auto", 0, 7), ("auto", 721, 7),
                                  ("remind", 12, 0), ("remind", 12, 366)]:
            with self.assertRaises(ValueError):
                self.learning.configure(mode, hours, days)

    def test_only_source_backed_research_advances_review(self):
        with self.assertRaises(ValueError):
            self.learning.complete_research(self.question_id, {
                "source_pages_fetched": 0,
                "saved": {"saved": True, "filename": "reasoning_topics/empty.txt"}
            })
        self.assertEqual(self.store.questions_for(self.topic["id"])[0]["state"], "open")
        indexed = self.learning.complete_research(self.question_id, {
            "source_pages_fetched": 1,
            "saved": {"saved": True, "filename": "reasoning_topics/notes.txt"}
        })
        self.assertFalse(indexed["verified"])
        self.assertEqual(self.store.questions_for(self.topic["id"])[0]["state"], "researched")
        self.assertEqual(self.store.research_for(self.question_id)[0]["confidence"], "unverified")

    def test_prevents_traversal_reference_from_being_indexed(self):
        with self.assertRaises(ValueError):
            self.learning.complete_research(self.question_id, {
                "source_pages_fetched": 1,
                "saved": {"saved": True, "filename": "../outside.txt"}
            })

    def test_suggestions_are_explainable_not_applied(self):
        items = self.learning.suggestions()
        self.assertTrue(items)
        self.assertTrue(all("why" in item and "next" in item for item in items))
        self.assertFalse(any(item.get("applied") for item in items))


class FakeManager:
    def __init__(self, pages=1):
        self.pages = pages
        self.actions = []

    def get_module(self, key):
        if key in {"training_module", "memory_bank"}:
            return {"enabled": True, "instance": object()}
        return None

    def execute(self, module, action, args):
        self.actions.append((module, action, args))
        if action == "explore_web_and_save":
            return {"source_pages_fetched": self.pages,
                    "saved": {"saved": True, "filename": args["filename"]},
                    "sources": [{"title": "Example", "url": "https://example.org",
                                 "text": "A source text, requiring confirmation."}]}
        if action == "store_memory":
            return {"stored": True}
        raise AssertionError("Unexpected tool " + action)


class ReasoningIntegrationTests(unittest.TestCase):
    def test_approved_research_path_indexes_evidence_and_memory(self):
        with tempfile.TemporaryDirectory() as root:
            app = Module({"base_dir": root})
            try:
                topic = app.store.propose_topic(
                    "XTTS voice models", "Investigate audio generation performance metrics"
                )
                question = app.store.questions_for(topic["id"])[0]
                manager = FakeManager()
                app.context["runtime"] = type("Runtime", (), {"_manager": manager})()
                result = app.research_question(question["id"])
                self.assertFalse(result["verified"])
                self.assertEqual(result["source_pages_fetched"], 1)
                self.assertEqual([name for name, _, _ in manager.actions],
                                 ["training_module", "memory_bank"])
                self.assertTrue(app.store.research_for(question["id"]))
            finally:
                app.close()

    def test_zero_sources_does_not_fake_success(self):
        with tempfile.TemporaryDirectory() as root:
            app = Module({"base_dir": root})
            try:
                topic = app.store.propose_topic(
                    "Pi processing", "Assess simple benchmarks on Raspberry Pi hardware"
                )
                question = app.store.questions_for(topic["id"])[0]
                app.context["runtime"] = type("Runtime", (), {"_manager": FakeManager(0)})()
                with self.assertRaises(ValueError):
                    app.research_question(question["id"])
                self.assertFalse(app.store.research_for(question["id"]))
            finally:
                app.close()

    def test_ui_and_chat_wiring_have_no_eval(self):
        root = Path(__file__).resolve().parents[1]
        main = (root / "main.py").read_text(encoding="utf-8")
        learning = (root / "modules/reasoning_director/module.py").read_text(encoding="utf-8")
        self.assertIn("def run_learning_followups(self):", main)
        self.assertIn("knowledge_subject = knowledge_query(text)", main)
        self.assertIn('"Ask Apollo in Chat"', learning)
        self.assertIn('"Follow-ups & upgrades"', learning)
        self.assertIn('manager.execute("self_improvement_lab", "create_proposal"', learning)


if __name__ == "__main__":
    unittest.main()
