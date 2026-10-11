"""Regression tests for Apollo's staged Coding Company workflow."""
import tempfile
import unittest
from pathlib import Path

from apollo_coding_company import (
    CodingCompany, DemoRoleModel, OllamaRoleModel, parse_json, safe_file
)
from modules.coding_company.module import Module


class BrokenDeveloper(DemoRoleModel):
    def complete(self, role, request):
        if role == "developer":
            return {"files": {"main.py": "def broken(:\n    pass\n"}, "summary": "Bad syntax"}
        return super().complete(role, request)


class RejectOnce(DemoRoleModel):
    def __init__(self):
        self.rejected = False

    def complete(self, role, request):
        if role == "reviewer" and not self.rejected:
            self.rejected = True
            return {"approved": False, "feedback": "Improve the project."}
        return super().complete(role, request)


class ExploitDeveloper(DemoRoleModel):
    def complete(self, role, request):
        if role == "developer":
            return {"files": {"../../main.py": "print('escaped')"}}
        return super().complete(role, request)


class CodingCompanyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        (self.base / "config.json").write_text(
            '{"model":"mock","ollama_url":"http://127.0.0.1:11434"}')
        self.company = CodingCompany(self.base)
        self.addCleanup(self.company.close)

    def make(self, **opts):
        return self.company.create("Greeting App", "Build a very small greeting function", **opts)["id"]

    def run_until_review(self, pid, model=None):
        for _ in range(25):
            info = self.company.detail(pid)["project"]
            if info["state"] != "ready":
                return info
            self.company.step(pid, model or DemoRoleModel())
        self.fail("Unbounded agent loop")

    def test_complete_cycle_records_all_five_roles_without_execution(self):
        pid = self.make()
        p = self.run_until_review(pid)
        self.assertEqual(p["state"], "awaiting_user")
        d = self.company.detail(pid)
        self.assertEqual([t["role"] for t in d["turns"]], [
            "architect", "developer", "tester", "reviewer", "integrator"])
        self.assertTrue((Path(d["candidate"]) / "main.py").is_file())
        self.assertIn('no generated code executed', d['validation'])
        self.assertFalse((self.base / "main.py").exists())
        for t in d["turns"]:
            self.assertFalse(__import__("json").loads(t["evidence"]).get("runtime_tests_executed"))
        self.assertEqual(self.company.feedback(pid, "approve")["state"], "approved")
        with self.assertRaises(ValueError):
            self.company.step(pid, DemoRoleModel())

    def test_feedback_reopens_developer_and_keeps_history(self):
        pid = self.make()
        self.run_until_review(pid)
        p = self.company.feedback(pid, "changes", "Please add error handling")
        self.assertEqual(p["phase"], "developer")
        self.assertEqual(p["iteration"], 2)
        p = self.run_until_review(pid)
        self.assertEqual(p["state"], "awaiting_user")
        self.assertEqual(len(self.company.detail(pid)["reviews"]), 1)
        self.assertEqual(self.company.feedback(pid, "reject")["state"], "rejected")

    def test_syntax_failure_is_sent_back_and_bounded(self):
        pid = self.make(max_reworks=1)
        model = BrokenDeveloper()
        self.company.step(pid, model)  # architect
        self.company.step(pid, model)  # developer
        p = self.company.step(pid, model)["project"]  # tester
        self.assertEqual(p["phase"], "developer")
        self.assertEqual(p["attempts"], 1)
        self.company.step(pid, model)
        p = self.company.step(pid, model)["project"]
        self.assertEqual(p["state"], "failed")
        self.assertIn("syntax", p["last_error"].lower())

    def test_reviewer_can_send_code_back_and_recover(self):
        pid = self.make()
        self.run_until_review(pid, RejectOnce())
        p = self.company._project(pid)
        self.assertEqual(p["state"], "awaiting_user")
        self.assertEqual(p["iteration"], 2)
        self.assertEqual(p["attempts"], 1)

    def test_path_injection_does_not_modify_outside_workspace(self):
        pid = self.make()
        self.company.step(pid, ExploitDeveloper())
        state = self.company.step(pid, ExploitDeveloper())["project"]
        self.assertEqual(state["state"], "paused")
        self.assertFalse((self.base / "main.py").exists())
        root = Path(self.company.detail(pid)["candidate"])
        for name in ["../escape.py", "/tmp/bad.py", "x/../../bad.py",
                     ".git/config.py", "storage/data.py", "C:\\windows\\file.py",
                     "folder/.env", "file.exe"]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_file(root, name)

    def test_workspace_symlink_escape_is_rejected(self):
        pid = self.make()
        root = Path(self.company.detail(pid)["candidate"])
        outside = self.base / "outside"
        outside.mkdir()
        try:
            (root / "link").symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink unavailable on this machine")
        with self.assertRaises(ValueError):
            safe_file(root, "link/pwn.py")
        with self.assertRaises(ValueError):
            self.company._files(pid)

    def test_pause_resume_and_restart_recovery(self):
        pid = self.make()
        self.company.pause(pid)
        self.assertEqual(self.company._project(pid)["state"], "paused")
        self.company.resume(pid)
        self.company._update(pid, state="running")
        second = CodingCompany(self.base)
        try:
            self.assertEqual(second._project(pid)["state"], "paused")
            second.resume(pid)
            self.assertEqual(second.step(pid, DemoRoleModel())["project"]["phase"], "developer")
        finally:
            second.close()

    def test_turn_budget_never_runs_indefinitely(self):
        pid = self.make(max_turns=5)
        self.run_until_review(pid)
        self.company.feedback(pid, "changes", "Another round")
        p = self.company._project(pid)
        self.assertEqual(p["state"], "failed")
        with self.assertRaises(ValueError):
            self.company.resume(pid)

    def test_only_explicitly_approved_evidence_can_be_learned(self):
        pid = self.make()
        with self.assertRaises(ValueError):
            self.company.lesson(pid, "developer", "Check imports", "manual review")
        self.run_until_review(pid)
        self.company.feedback(pid, "approve")
        self.company.lesson(pid, "developer", "Check imports", "Reviewed the completed diff")
        self.assertEqual(len(self.company.lessons("developer")), 1)
        lesson_id = self.company.lessons("developer")[0]["id"]
        self.company.revoke_lesson(lesson_id)
        self.assertFalse(self.company.lessons("developer"))

    def test_staging_quota_and_malformed_model_are_handled(self):
        pid = self.make()
        self.company.step(pid, DemoRoleModel())
        class Malformed(DemoRoleModel):
            def complete(self, role, request):
                return {"files": {"huge.py": "x" * 60001}}
        p = self.company.step(pid, Malformed())["project"]
        self.assertEqual(p["state"], "paused")
        self.assertIn("large", p["last_error"])
        with self.assertRaises(ValueError):
            parse_json("No JSON")

    def test_public_agent_tools_are_read_only(self):
        module = Module({"base_dir": self.base})
        self.assertIn("read-only", module.self_test())
        self.assertEqual(len(module.tools()), 2)
        with self.assertRaises(KeyError):
            module.run("approve_project", {"project_id": 1})

    def test_model_mode_survives_restart(self):
        pid = self.company.create('Mode project', 'Test', mode='demo')['id']
        second = CodingCompany(self.base)
        try:
            self.assertEqual(second._project(pid)['mode'], 'demo')
            self.assertEqual(second.step(pid)['project']['phase'], 'developer')
        finally:
            second.close()

    def test_ollama_host_is_local_only(self):
        (self.base / "config.json").write_text('{"ollama_url":"http://example.org:11434"}')
        with self.assertRaises(ValueError):
            OllamaRoleModel(self.base)


if __name__ == "__main__":
    unittest.main()
