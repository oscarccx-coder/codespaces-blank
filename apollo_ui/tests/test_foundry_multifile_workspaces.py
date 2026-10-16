"""Real multi-file Foundry handoff and chat routing; offline regression tests."""
import json
from pathlib import Path
import tempfile
import unittest

from apollo_foundry_artifacts import MANIFEST, save_bundle
from apollo_foundry_workspace import list_generated_files, read_workspace_context
from apollo_project_studio import StudioStore
from modules.project_studio.module import Module


class EditableStarterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = StudioStore(self.root)
        self.addCleanup(self.store.close)
        state = self.store.add_project("Multi module test", "An app with services and a Qt interface")
        self.pid = state["project"]["id"]
        self.folder = self.store.project_folder(self.pid)

    def test_starter_files_are_owned_and_can_be_improved_by_agents(self):
        created = self.store.create_starter_ui(self.pid)
        self.assertEqual(len(created["files"]), 5)
        owned = json.loads((self.folder / MANIFEST).read_text(encoding="utf-8"))
        self.assertEqual(set(created["files"]), set(owned))
        self.assertEqual(self.store.run_checks(self.pid)["status"], "passed")
        # Foundry can revise its own starter, without overwriting owner data.
        save_bundle(self.folder, {"files": [
            {"path": "service.py",
             "content": "class AppService:\n    def save(self):\n        return 42\n"},
        ], "summary": "Improve one service module"})
        self.assertIn("return 42", (self.folder / "service.py").read_text())
        self.assertIn("return 42", read_workspace_context(self.folder))
        self.assertEqual(len(list_generated_files(self.folder)), 5)

    def test_starter_still_refuses_unowned_or_manually_modified_files(self):
        self.store.create_starter_ui(self.pid)
        (self.folder / "private.py").write_text("secret", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not generated"):
            save_bundle(self.folder, {"files": [
                {"path": "private.py", "content": "changed\n"}
            ], "summary": "unsafe"})
        original = (self.folder / "private.py").read_text()
        self.assertEqual(original, "secret")
        (self.folder / "service.py").write_text("# human edited\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "manually edited"):
            save_bundle(self.folder, {"files": [
                {"path": "service.py", "content": "x = 9\n"},
            ], "summary": "unsafe"})
        listing = {row["path"]: row["state"] for row in list_generated_files(self.folder)}
        self.assertEqual(listing["service.py"], "modified")

    def test_multi_file_inventory_excludes_untracked_private_content(self):
        self.store.create_starter_ui(self.pid)
        for i in range(12):
            save_bundle(self.folder, {"files": [
                {"path": f"components/part_{i}.py",
                 "content": f"def part_{i}():\n    return {i}\n"}
            ], "summary": "Add component"})
        (self.folder / "secret-private-note.txt").write_text(
            "DO_NOT_LEAK_ME", encoding="utf-8")
        context = read_workspace_context(self.folder, focus="components/part_11.py", budget=5500)
        self.assertIn("part_11.py", context)
        self.assertIn("def part_11", context)
        self.assertNotIn("DO_NOT_LEAK_ME", context)
        self.assertIn("GENERATED FILE INVENTORY", context)
        self.assertLessEqual(len(context), 5500)

    def test_editing_source_does_not_invalidate_unrelated_owned_modules(self):
        self.store.create_starter_ui(self.pid)
        save_bundle(self.folder, {"files": [
            {"path": "components/service_a.py", "content": "VALUE = 7\n"},
            {"path": "components/service_b.py", "content": "VALUE = 8\n"},
        ], "summary": "Two modules"})
        save_bundle(self.folder, {"files": [
            {"path": "components/service_a.py", "content": "VALUE = 9\n"},
        ], "summary": "One change"})
        result = {row["path"]: row for row in list_generated_files(self.folder)}
        self.assertEqual(result["components/service_b.py"]["state"], "owned")
        self.assertEqual(result["components/service_a.py"]["state"], "owned")


class ChatAppCreationTests(unittest.TestCase):
    def test_chat_can_create_private_project_but_not_execute_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = Module({"base_dir": tmp})
            try:
                created = module.run("create_app_project", {
                    "title": "Science Calculator",
                    "brief": "Build an offline Python desktop calculator"
                })
                pid = created["project"]["id"]
                self.assertEqual(len(created["tasks"]), 5)
                self.assertEqual(module.run("app_project_files", {
                    "project_id": pid
                })["files"], [])
                self.assertTrue(module.store.project_folder(pid).is_dir())
                self.assertNotIn("run_app", {tool["name"] for tool in module.tools()})
                with self.assertRaises(KeyError):
                    module.run("approve_project", {"project_id": pid})
            finally:
                module.close()


if __name__ == "__main__":
    unittest.main()
