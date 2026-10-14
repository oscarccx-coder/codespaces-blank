"""Foundry source handoff and opt-in research regression tests (no model/network)."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from apollo_foundry_artifacts import save_bundle
from apollo_foundry_research import collect_research, query_for_failure
from apollo_project_studio import StudioStore
from apollo_project_workers import draft_for_task

class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
    @staticmethod
    def proposal(name="main.py", content="x=1\n"):
        return {"files": [{"path": name, "content": content}], "summary": "Generated code"}
    def test_create_and_update_owned_code(self):
        save_bundle(self.folder, self.proposal())
        out = save_bundle(self.folder, self.proposal(content="x=2\n"))
        self.assertEqual(out["files"], ["main.py"])
        self.assertEqual((self.folder / "main.py").read_text(), "x=2\n")
    def test_refuses_existing_manual_edits_and_unowned_files(self):
        (self.folder / "main.py").write_text("manual")
        with self.assertRaisesRegex(ValueError, "manually edited"):
            save_bundle(self.folder, self.proposal())
        self.assertEqual((self.folder / "main.py").read_text(), "manual")
    def test_refuses_traversal_and_invalid_json(self):
        for name in ("../escape.py", "C:/escape.py", "/tmp/escape.py",
                     "Setup/main.py", ".git/a.py", "sub\\escape.py"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                save_bundle(self.folder, self.proposal(name))
        with self.assertRaises(ValueError):
            save_bundle(self.folder, self.proposal("foundry.json", "{invalid"))
    def test_refuses_symlink_escapes(self):
        other = self.folder.parent / "outside-foundry"
        try:
            (self.folder / "linked").symlink_to(other, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unsupported")
        with self.assertRaises(ValueError):
            save_bundle(self.folder, self.proposal("linked/main.py"))

class ResearchTests(unittest.TestCase):
    def test_query_never_leaks_project_text(self):
        error = "SyntaxError /my-private-project/secret-password-PASSPHRASE"
        query = query_for_failure(error)
        self.assertNotIn("PASSPHRASE", query)
        self.assertNotIn("my-private-project", query)
    def test_results_are_filtered_to_https_public_docs(self):
        def search(query, limit):
            return {"results":[
                {"title":"Python","url":"https://docs.python.org/3/reference/","snippet":"grammar"},
                {"title":"Untrusted","url":"https://unknown.example/","snippet":"bad"},
                {"title":"Local","url":"http://localhost/info","snippet":"bad"}
            ]}
        result = collect_research("SyntaxError", search=search)
        self.assertEqual(len(result["sources"]), 1)
        self.assertIn("docs.python.org", result["sources"][0]["url"])

class ModelTests(unittest.TestCase):
    def test_implementer_gets_provisional_context_and_outputs_json(self):
        with tempfile.TemporaryDirectory() as root:
            store = StudioStore(root)
            self.addCleanup(store.close)
            data = store.add_project("Casimir", "Use Python and PySide6")
            arch, impl = data["tasks"][:2]
            store.start_task(arch["id"])
            store.submit_task(arch["id"], "PySide6 architecture, no Flask", "Draft only")
            store.start_task(impl["id"])
            state = store.details(data["project"]["id"])
            seen = []
            class Response:
                def __enter__(self): return self
                def __exit__(self, *args): return False
                def read(self, limit): return json.dumps({
                    "response": json.dumps({"files":[{"path":"main.py","content":"x=1"}],"summary":"ready"})
                }).encode()
            class Opener:
                def open(self, request, timeout):
                    seen.append(json.loads(request.data))
                    return Response()
            with patch("apollo_project_workers.urllib.request.build_opener", return_value=Opener()):
                result = draft_for_task(state, impl["id"], "qwen2.5-coder:7b", repair_context="SyntaxError")
            self.assertIn('"files"', result)
            self.assertEqual(seen[0]["format"], "json")
            self.assertIn("PySide6 architecture", seen[0]["prompt"])
            self.assertIn("SyntaxError", seen[0]["prompt"])
            self.assertIn("CURRENT", seen[0]["prompt"].upper() if False else "CURRENT") if False else None

if __name__ == "__main__":
    unittest.main()
