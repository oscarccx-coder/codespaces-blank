"""Safety, spaced revision, measurable reasoning and main-application wiring."""
import ast
from datetime import timedelta
import importlib.util
from pathlib import Path
import tempfile
import unittest

from apollo_growth import GrowthStore
from apollo_reasoning import (
    ReasoningStore, QUESTIONS, grade, run_practice, utc_now
)
from apollo_growth_director import direction_report
from apollo_module_catalog import group_for
from modules.reasoning_director.module import suggest_new_questions


ROOT = Path(__file__).resolve().parent


class FakeModel:
    model = "mock-local-llm"

    def __init__(self, texts):
        self.texts = list(texts)
        self.messages = []

    def chat_once(self, messages):
        self.messages.append(messages)
        answer = self.texts.pop(0)
        return {
            "message": {"content": answer},
            "eval_count": 50, "eval_duration": 2_000_000_000,
        }


class LearningDirectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = ReasoningStore(self.root)
        self.addCleanup(self.store.close)

    def topic(self):
        return self.store.propose_topic(
            "555 Timer Oscillator", "Understand 555 pulse timing and circuit faults", 5
        )

    def test_question_generation_is_automatic_bounded_and_deduplicated(self):
        info = self.topic()
        self.assertTrue(info["created"])
        questions = self.store.questions_for(info["id"])
        self.assertEqual(len(questions), 4)
        self.assertTrue(all(x["next_review"] for x in questions))
        self.assertEqual(len(self.store.due_questions()), 4)
        duplicate = self.topic()
        self.assertFalse(duplicate["created"])
        self.assertEqual(len(self.store.questions_for(info["id"])), 4)
        self.assertFalse(any(q["state"] != "open" for q in questions))
        for _ in range(8):
            self.store.suggest_questions(info["id"])
        self.assertEqual(len(self.store.questions_for(info["id"])), 4)

    def test_notes_revisit_and_provenance_never_prove_facts(self):
        topic = self.topic()
        question_id = self.store.questions_for(topic["id"])[0]["id"]
        result = self.store.record_research(
            question_id,
            "Datasheet suggests a specific timing formula; still needs simulation checks.",
            "https://example.org/datasheet", "public_source", "unverified", 7
        )
        self.assertFalse(result["proof_of_correctness"])
        self.assertEqual(len(self.store.research_for(question_id)), 1)
        self.assertEqual(self.store.research_for(question_id)[0]["source"], "https://example.org/datasheet")
        self.assertEqual(len(self.store.due_questions()), 3)
        later = utc_now() + timedelta(days=8)
        self.assertEqual(len(self.store.due_questions(as_of=later)), 4)
        restored = ReasoningStore(self.root)
        try:
            self.assertEqual(restored.research_for(question_id)[0]["confidence"], "unverified")
            self.assertEqual(restored.topic(topic["id"])["priority"], 5)
        finally:
            restored.close()

    def test_bad_sources_and_nonexistent_questions_rejected(self):
        topic = self.topic()
        qid = self.store.questions_for(topic["id"])[0]["id"]
        for source in ("http://example.org", "javascript:alert(1)", "https://user:pw@example.org"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.store.record_research(qid, "This is a test summary of many words.",
                                           source, "public_source")
        with self.assertRaises(ValueError):
            self.store.record_research(999, "An unresolved claim with enough characters.",
                                       "lab-record-1", "experiment")
        self.assertEqual(self.store.research_for(qid), [])

    def test_question_limits_stop_autonomous_queue_growth(self):
        t = self.topic()
        for n in range(8):
            self.store.add_question(t["id"], f"How could controlled experiment {n} test this claim?")
        self.assertEqual(len(self.store.questions_for(t["id"])), 12)
        with self.assertRaisesRegex(ValueError, "limit"):
            self.store.add_question(t["id"], "What else can the model research next week?")
        with self.assertRaises(ValueError):
            self.store.propose_topic("Invalid", "Tiny", 3)

    def test_deterministic_grading_never_trusts_model_self_assessment(self):
        self.assertTrue(grade("electronics_01", "FINAL: 300")["passed"])
        self.assertTrue(grade("inference_01", "FINAL: no")["passed"])
        self.assertFalse(grade("inference_01", "FINAL: yes")["passed"])
        self.assertFalse(grade("electronics_01", "I am 100% sure it is 301.")["passed"])
        with self.assertRaises(KeyError):
            grade("invented_solved_challenge", "FINAL: yes")

    def test_practice_tracks_mode_accuracy_and_output_speed(self):
        self.assertEqual(self.store.practice_questions(3, method="direct"),
                         self.store.practice_questions(3, method="self_review"))
        direct = FakeModel(["Work: drop 3V / 0.01A.\nFINAL: 300",
                            "Series resistors next 330.\nFINAL: 330", "FINAL: yes"])
        result = run_practice(direct, self.store, limit=3)
        self.assertEqual(result["completed"], 3)
        self.assertEqual([x["passed"] for x in result["results"]], [True, True, False])
        self.assertEqual(result["results"][0]["output_tokens_per_second"], 25.0)
        self.assertEqual(len(direct.messages), 3)
        self.assertTrue(all(len(item) == 2 for item in direct.messages))
        review = FakeModel(["FINAL: 300", "Reviewed: FINAL: 300",
                            "FINAL: 330", "Checked\nFINAL: 330",
                            "FINAL: yes", "FINAL: no"])
        checked = run_practice(review, self.store, limit=3, review=True)
        self.assertEqual(checked["completed"], 3)
        self.assertTrue(all(x["passed"] for x in checked["results"]))
        self.assertEqual(len(review.messages), 6)
        self.assertEqual(self.store.progress()["active_topics"], 0)
        self.assertEqual(sum(x["attempts"] for x in self.store.progress()["skills"]), 6)
        self.assertEqual(len(self.store.practice_questions(3, method="direct")), 3)
        self.assertEqual(self.store.practice_questions(3, method="direct")[0]["id"], QUESTIONS[3]["id"])

    def test_generated_questions_are_not_research_and_do_not_execute_tools(self):
        t = self.topic()
        model = FakeModel(['["What primary data could verify the oscillator timing?", '
                           '"What alternative explanation might fit the observations?"]'])
        result = suggest_new_questions(model, self.store, t["id"])
        self.assertEqual(len(result["questions"]), 2)
        self.assertFalse(result["facts_verified"])
        self.assertFalse(result["web_access"])
        self.assertEqual(len(self.store.questions_for(t["id"])), 6)
        self.assertEqual(len(model.messages), 1)
        self.assertTrue(all("tools" not in message for message in model.messages[0]))
        invalid = FakeModel(["The study is conclusive and ready."])
        with self.assertRaisesRegex(ValueError, "JSON"):
            suggest_new_questions(invalid, self.store, t["id"])

    def test_director_combines_no_fake_income_and_tracks_learning_and_work(self):
        growth = GrowthStore(self.root)
        try:
            growth.propose(
                "Reusable restaurant workbook",
                "Tested custom preorder sheet and documentation",
                "Business spreadsheet", "150.00"
            )
            growth.create_goal_from_ui("More capable GPU", "450.00",
                                       "Wait for actual VRAM and model benchmarks")
        finally:
            growth.close()
        t = self.topic()
        plan = direction_report(self.root)
        self.assertEqual(plan["draft_work_count"], 1)
        self.assertEqual(plan["approved_work_count"], 0)
        self.assertEqual(plan["upgrade_fund"], "£0.00")
        self.assertEqual(plan["active_research_topics"], 1)
        self.assertGreater(plan["due_research_questions"], 0)
        self.assertIsNone(plan["hardware"])  # no unsolicited subprocess/scan
        self.assertTrue(any(x["area"] == "learning" for x in plan["recommended_next"]))
        self.assertFalse(any("guarantee" in str(x).lower() for x in plan["recommended_next"]))

    def test_module_tool_contract_excludes_payments_browsing_and_model_training(self):
        path = ROOT / "modules/reasoning_director/module.py"
        source = path.read_text(encoding="utf-8")
        ast.parse(source)
        spec = importlib.util.spec_from_file_location("reasoning_module_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        app = module.Module({"base_dir": self.root})
        try:
            self.assertTrue(app.self_test())
            names = {t["name"] for t in app.tools()}
            self.assertEqual(names, {
                "learning_propose_topic", "learning_suggest_questions",
                "learning_due_questions", "learning_practice_scores",
                "growth_direction_status",
            })
            with self.assertRaises(KeyError):
                app.run("record_income", {"value": "120"})
            with self.assertRaises(KeyError):
                app.run("approve_hardware_purchase", {"item": "GPU"})
            with self.assertRaises(KeyError):
                app.run("browse_web", {"query": "anything"})
            with self.assertRaises(KeyError):
                app.run("train_main_llm", {})
            self.assertTrue(app.run("learning_propose_topic", {
                "name": "Circuit simulation and calibration",
                "purpose": "Compare calculations with measured waveform errors"
            })["created"])
            self.assertEqual(len(app.run("learning_due_questions", {})["questions"]), 4)
        finally:
            app.close()
        self.assertEqual(group_for("reasoning_director"), "Memory & Learning")
        for label in ("Run 3 Direct Answers", "Run 3 Self-Reviewed Answers",
                      "Record Source/Observation", "Generate AI Questions"):
            self.assertIn(label, source)


if __name__ == "__main__":
    unittest.main()
