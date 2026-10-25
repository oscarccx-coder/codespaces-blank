"""Offline JARVIS Director tests. No Ollama, Docker, shell, or cloud access."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apollo_jarvis_director import (
    Director, DirectorStore, candidate_entries, FALLBACK, MAX_AGENT_TASKS
)
from module import Module


class JarvisDirectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "config.json").write_text(
            '{"model":"qwen2.5-coder:7b"}', encoding="utf-8")
        self.messages = []
        self.plan = [{"title": title, "role": role, "brief": brief}
                     for title, role, brief in FALLBACK]

        def fake_plan(state, task_id, model, *, timeout):
            self.messages.append(("plan", model, task_id))
            return self.plan

        def fake_draft(state, task_id, model, *, timeout):
            role = state["tasks"][0]["role"]
            self.messages.append(("draft", role, task_id))
            if role == "implementer":
                return json.dumps({"files": [
                    {"path": "plugin.py", "content": "def calculate():\n    return 42\n"},
                    {"path": "test_plugin.py", "content":
                     "from plugin import calculate\nassert calculate() == 42\n"},
                ], "summary": "Only staged; no tests executed."})
            return "Proposed %s plan based on fixed source excerpt; not executed." % role

        self.director = Director(self.root, validation=True,
                                 plan_fn=fake_plan, draft_fn=fake_draft)
        self.addCleanup(self.director.close)

    def start(self, mode="fixed", max_calls=10):
        return self.director.owner_begin(
            "Reliability improvement", "Find a reproducible problem and propose one isolated, tested candidate.",
            mode=mode, max_calls=max_calls, interval_seconds=30)

    def due(self, mid):
        with self.director.store.lock, self.director.store.db:
            self.director.store.db.execute("UPDATE missions SET next_due=0 WHERE id=?", (mid,))

    def run_one(self, mid):
        self.due(mid)
        return self.director.step()

    def test_owner_gate_and_read_only_chat_tools(self):
        module = Module({"base_dir": str(self.root), "validation": True})
        self.addCleanup(module.close)
        names = [x["name"] for x in module.tools()]
        self.assertEqual(names, ["jarvis_mission_status", "jarvis_mission_detail", "jarvis_update_status", "jarvis_roles"])
        self.assertTrue(module.self_test())
        with self.assertRaises(KeyError):
            module.run("jarvis_start", {"objective": "write core"})
        with self.assertRaises(PermissionError):
            self.director.store.begin("Unapproved", "Attempting an unauthorised mission start.")

    def test_autonomous_agents_stage_code_but_never_execute(self):
        mission = self.start(max_calls=6)
        mid = mission["id"]
        plan = self.run_one(mid)
        self.assertEqual(plan["status"], "agents_created")
        self.assertEqual(plan["agents"], len(self.plan))
        created = self.director.store.detail(mid)
        self.assertEqual({t["role"] for t in created["agents"]},
                         {"architect", "implementer", "tester", "reviewer", "integrator"})
        results = [self.run_one(mid) for _ in self.plan]
        self.assertTrue(all(t["status"] == "draft_saved" for t in results))
        candidate = next(r["candidate"] for r in results if r["role"] == "implementer")
        self.assertTrue((self.root / candidate / "plugin.py").exists())
        self.assertFalse((self.root / "plugin.py").exists())
        meta = json.loads((self.root / candidate).parent.joinpath("candidate_manifest.json").read_text())
        self.assertEqual(meta["status"], "STATIC_ONLY_UNTESTED")
        self.assertFalse(any(t.get("verified") for t in results))
        self.assertFalse(any(t.get("executed") for t in results))
        self.assertEqual(self.run_one(mid)["status"], "idle")
        self.assertEqual(self.director.store.detail(mid)["mission"]["state"], "COMPLETED")
        self.assertEqual(self.director.store.detail(mid)["mission"]["calls_used"], 6)

    def test_pause_resume_and_stop_persist(self):
        mission = self.start()
        mid = mission["id"]
        self.director.owner_control(mid, "pause")
        self.assertEqual(self.run_one(mid)["status"], "idle")
        self.director.owner_control(mid, "resume")
        self.assertEqual(self.run_one(mid)["status"], "agents_created")
        self.director.owner_control(mid, "stop")
        self.assertEqual(self.run_one(mid)["status"], "idle")
        self.assertEqual(self.director.store.detail(mid)["mission"]["state"], "STOPPED")
        with self.assertRaises(ValueError):
            self.director.owner_control(mid, "resume")

    def test_call_budget_blocks_unlimited_model_usage(self):
        mission = self.start(mode="until_stop", max_calls=2)
        mid = mission["id"]
        self.run_one(mid)
        self.run_one(mid)
        self.assertEqual(self.run_one(mid)["status"], "idle")
        m = self.director.store.detail(mid)["mission"]
        self.assertEqual(m["state"], "BUDGET_EXHAUSTED")
        self.assertEqual(m["calls_used"], 2)
        self.assertEqual(len(self.messages), 2)

    def test_model_plan_fallback_and_failure_blocks(self):
        self.plan = [{"title": "manager only", "brief": "draft notes", "role": "manager"}]
        mission = self.start()
        mid = mission["id"]
        plan = self.run_one(mid)
        self.assertIn("fallback", plan["source"])
        self.assertEqual(len(self.director.store.detail(mid)["agents"]), 5)

    def test_planner_error_does_not_fabricate_results(self):
        def bad(*args, **kwargs):
            raise RuntimeError("No Ollama connection")
        self.director.plan_fn = bad
        mid = self.start()["id"]
        outcome = self.run_one(mid)
        self.assertEqual(outcome["status"], "blocked")
        m = self.director.store.detail(mid)["mission"]
        self.assertEqual(m["state"], "BLOCKED")
        self.assertEqual(m["calls_used"], 1)
        self.assertEqual(self.director.store.detail(mid)["agents"], [])

    def test_failed_implementer_does_not_create_core_files(self):
        mid = self.start()["id"]
        self.run_one(mid)
        self.run_one(mid)  # architect
        def malicious(state, task_id, model, *, timeout):
            return json.dumps({"files": [{"path": "../../main.py",
                                          "content": "print('unsafe')"}]})
        self.director.draft_fn = malicious
        result = self.run_one(mid)
        self.assertEqual(result["status"], "agent_failed")
        self.assertFalse((self.root / "main.py").exists())
        self.assertEqual(self.director.store.detail(mid)["mission"]["state"], "RUNNING")
        self.assertEqual(self.run_one(mid)["status"], "agent_failed")
        self.assertEqual(self.director.store.detail(mid)["mission"]["state"], "BLOCKED")

    def test_validation_rejects_traversal_and_invalid_source(self):
        bad = ["../main.py", "/tmp/exploit.py", "C:\\secret.py", ".env",
               "nested/../main.py", "folder/.hidden.py"]
        for path in bad:
            with self.subTest(path=path):
                with self.assertRaises(PermissionError):
                    candidate_entries(json.dumps({"files": [{"path": path, "content": "x=1"}]}))
        with self.assertRaises(SyntaxError):
            candidate_entries(json.dumps({"files": [{"path": "x.py", "content": "def broken("}]}))
        with self.assertRaises(ValueError):
            candidate_entries(json.dumps({"files": [
                {"path": "x.py", "content": "x=1"},
                {"path": "x.py", "content": "x=2"}]}))
        with self.assertRaises(ValueError):
            candidate_entries(json.dumps({"files": [
                {"path": "stuff.json", "content": "not json"}]}))

    def test_no_sensitive_runtime_or_workspace_source_is_sent_to_model(self):
        secret_dir = self.root / "storage" / "databases"
        secret_dir.mkdir(parents=True)
        (secret_dir / "memory.db").write_text("HIGHLY_PRIVATE_SAMPLE", encoding="utf-8")
        (self.root / "apollo_project_workers.py").write_text("def local_worker(): pass\n")
        excerpt = self.director.store.source_context()
        self.assertIn("def local_worker()", excerpt)
        self.assertNotIn("HIGHLY_PRIVATE_SAMPLE", excerpt)

    def test_restart_recovers_inflight_as_retry_not_extra_budget(self):
        store = DirectorStore(self.root)
        self.addCleanup(store.close)
        mid = store.begin("Recovery test", "Test restart recovery without claiming unrun work complete.",
                          max_calls=10, owner_confirmed=True)["id"]
        work = store.claim()
        self.assertEqual(work["kind"], "plan")
        store.save_plan(mid, 0, self.plan)
        task = store.claim() if False else None
        with store.lock, store.db:
            store.db.execute("UPDATE missions SET next_due=0 WHERE id=?", (mid,))
        task = store.claim()
        self.assertEqual(task["kind"], "task")
        pre = store.detail(mid)["mission"]["calls_used"]
        store.close()
        reopened = DirectorStore(self.root)
        try:
            self.assertEqual(reopened.detail(mid)["agents"][0]["state"], "QUEUED")
            self.assertEqual(reopened.detail(mid)["mission"]["calls_used"], pre)
        finally:
            reopened.close()


    def test_owner_authorised_docker_tests_only_inside_existing_foundry(self):
        mid = self.start()["id"]
        self.run_one(mid)  # plan
        self.run_one(mid)  # architect
        self.run_one(mid)  # implementer, creates candidate
        details = self.director.store.detail(mid)
        implementer = next(a for a in details["agents"] if a["role"] == "implementer")
        candidate = implementer["candidate_path"]
        with patch("apollo_foundry_sandbox.run_sandbox") as sandbox:
            with self.assertRaises(PermissionError):
                self.director.owner_test_candidate(mid, implementer["id"], approved=False)
            self.assertEqual(sandbox.call_count, 0)
            sandbox.return_value = {
                "status": "unavailable", "reason": "Docker not installed",
                "executed_project_code": False, "output": "",
            }
            result = self.director.owner_test_candidate(
                mid, implementer["id"], approved=True)
            self.assertEqual(result["status"], "unavailable")
            self.assertEqual(sandbox.call_count, 1)
            self.assertEqual(Path(sandbox.call_args.args[0]), Path(candidate))
            self.assertEqual(sandbox.call_args.args[1], "unit")
            info = self.director.store.detail(mid)
            self.assertEqual(info["sandbox_results"][0]["status"], "unavailable")
            self.assertEqual(info["sandbox_results"][0]["executed"], 0)
            (Path(candidate) / "plugin.py").write_text("print('tampered')")
            with self.assertRaisesRegex(ValueError, "modified"):
                self.director.owner_test_candidate(mid, implementer["id"], approved=True)
            self.assertEqual(sandbox.call_count, 1)
            (Path(candidate) / "plugin.py").write_text("def calculate():\\n    return 42\\n")
            (Path(candidate) / "rogue.py").write_text("print('not reviewed')")
            with self.assertRaisesRegex(ValueError, "file set changed"):
                self.director.owner_test_candidate(mid, implementer["id"], approved=True)
            self.assertEqual(sandbox.call_count, 1)

    def test_mocked_docker_pass_only_records_actual_test_receipt(self):
        mid = self.start()["id"]
        self.run_one(mid)
        self.run_one(mid)
        self.run_one(mid)
        implementer = next(a for a in self.director.store.detail(mid)["agents"]
                           if a["role"] == "implementer")
        with patch("apollo_foundry_sandbox.run_sandbox", return_value={
            "status": "passed", "executed_project_code": True,
            "source_digest": "a" * 64, "output": "Ran 1 test\\nOK",
        }):
            self.director.owner_test_candidate(mid, implementer["id"], approved=True)
        result = self.director.store.detail(mid)["sandbox_results"][0]
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["executed"], 1)
        # Only one candidate received evidence; this is not a production pass.
        self.assertEqual(self.director.store.detail(mid)["mission"]["state"], "RUNNING")


    def test_reviewer_sees_actual_isolated_generated_source(self):
        mid = self.start()["id"]
        self.run_one(mid)
        self.run_one(mid)
        self.run_one(mid)
        actual = self.director.store.staged_source_context(mid, 0)
        self.assertIn("UNTRUSTED GENERATED SOURCE", actual)
        self.assertIn("def calculate()", actual)
        self.assertNotIn("HIGHLY_PRIVATE_SAMPLE", actual)

    def test_next_round_reflects_previous_drafts_as_unverified(self):
        mid = self.start(mode="until_stop", max_calls=14)["id"]
        self.run_one(mid)
        for _ in self.plan:
            self.run_one(mid)
        feedback = self.director.store.previous_round_context(mid, 1)
        self.assertIn("untrusted DRAFTS", feedback)
        self.assertIn("Independent critical review", feedback)
        self.assertIn("Docker receipts", feedback)
        result = self.run_one(mid)
        self.assertEqual(result["status"], "agents_created")
        self.assertEqual(self.director.store.detail(mid)["mission"]["round"], 1)

if __name__ == "__main__":
    unittest.main()
