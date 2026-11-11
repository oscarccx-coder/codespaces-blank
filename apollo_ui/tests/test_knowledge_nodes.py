"""Offline migration, recall, history and real Qt interaction checks."""
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from modules.memory_bank.module import Module


class KnowledgeNodeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.bank = Module({"base_dir": self.temp.name, "validation": True})
        self.addCleanup(self.bank.close)

    def memory(self, name="Engine note", text="Calibration measurements", **kw):
        return self.bank.store_memory(name, text, **kw)["id"]

    def test_auto_sections_tags_sources_and_no_duplicate_nodes(self):
        first = self.memory(tags=["XTTS", "xtts"], source="Manual", memory_type="project")
        self.memory("Another note", "Different body", tags=["XTTS"])
        nodes = self.bank.memory_nodes(first)
        self.assertEqual({n["title"] for n in nodes}, {"Projects", "XTTS", "Manual"})
        self.assertEqual(len(self.bank.list_knowledge_nodes("XTTS")), 1)
        self.assertEqual(self.bank.list_knowledge_nodes("xtts")[0]["memory_count"], 2)

    def test_topic_hierarchy_rejects_cycles_and_unknown_parent_atomically(self):
        parent = self.bank.create_knowledge_node("Apollo", "project")
        child = self.bank.create_knowledge_node("Voice", parent_id=parent["id"])
        with self.assertRaises(ValueError):
            self.bank.create_knowledge_node("Apollo", "project", parent_id=child["id"])
        self.assertIsNone(self.bank.inspect_knowledge_node(parent["id"])["node"]["parent_id"])
        with self.assertRaises(KeyError):
            self.bank.create_knowledge_node("Invalid", parent_id=1234567)
        self.assertFalse(self.bank.list_knowledge_nodes("Invalid"))

    def test_manual_membership_survives_metadata_replacement(self):
        memory_id = self.memory(tags=["Old tag"], source="Manual")
        node = self.bank.create_knowledge_node("Private build", "project")
        self.bank.link_memory_node(memory_id, node["id"])
        result = self.bank.store_memory("Engine note", "New measurement", source="Manual", tags=["New tag"])
        self.assertEqual(result["id"], memory_id)
        titles = {n["title"] for n in self.bank.memory_nodes(memory_id)}
        self.assertIn("Private build", titles)
        self.assertIn("New tag", titles)
        self.assertNotIn("Old tag", titles)

    def test_confirmed_one_hop_retrieves_without_text_match(self):
        self.memory("Voice runtime", "XTTS installation", tags=["XTTS"])
        target = self.memory("Resource budget", "Quantised speech worker memory ceiling", tags=["Resource planning"])
        a = self.bank.list_knowledge_nodes("XTTS")[0]["id"]
        b = self.bank.list_knowledge_nodes("Resource planning")[0]["id"]
        self.bank.link_knowledge_nodes(a, b, source="User linked topics")
        matches = self.bank.search_memory("XTTS")
        expanded = next(m for m in matches if m["id"] == target)
        self.assertIn("confirmed related", expanded["retrieval_reason"])
        self.assertIn("Resource planning", expanded["retrieval_reason"])
        self.assertEqual(expanded["reference"], f"memory:{target}")

    def test_suggested_contradictory_low_confidence_and_second_hop_do_not_expand(self):
        a = self.bank.create_knowledge_node("Quokka")
        b = self.bank.create_knowledge_node("Hidden")
        c = self.bank.create_knowledge_node("Distant")
        target = self.memory("No keyword", "Only some measurements")
        self.bank.link_memory_node(target, b["id"])
        for relation, status, confidence in [("related", "suggested", 1), ("contradicts", "confirmed", 1), ("related", "confirmed", 0.2)]:
            self.bank.link_knowledge_nodes(a["id"], b["id"], relation, "manual", confidence, status)
            self.assertEqual(self.bank.search_memory("Quokka"), [])
        self.bank.remove_knowledge_link(self.bank.inspect_knowledge_node(a["id"])["edges"][0]["id"])
        self.bank.link_knowledge_nodes(a["id"], c["id"], source="manual")
        self.bank.link_knowledge_nodes(c["id"], b["id"], source="manual")
        self.assertEqual(self.bank.search_memory("Quokka"), [])

    def test_unrelated_important_memory_not_returned_without_fts(self):
        self.memory(importance=5)
        self.bank.fts_available = False
        self.assertEqual(self.bank.search_memory("xylophone"), [])

    def test_sources_and_character_budget_in_shared_context(self):
        self.memory("XTTS settings", "XTTS " * 2000, source="Owner", source_ref="local:setup", tags=["XTTS"])
        packet = self.bank.run("knowledge_context", {"query": "XTTS", "max_chars": 550})
        self.assertLessEqual(len(packet["text"]), 550)
        self.assertIn("Owner local:setup", packet["text"])
        self.assertIn("[memory:", packet["text"])
        self.assertIn("Nodes:", packet["text"])

    def test_edit_and_auto_replace_keep_source_linked_versions(self):
        ident = self.memory(source="Owner", source_ref="local:1")
        self.bank.update_memory(ident, "Second revision")
        self.bank.store_memory("Engine note", "Third revision", source="Owner", source_ref="local:2")
        history = self.bank.memory_history(ident)
        self.assertEqual([r["content"] for r in history], ["Second revision", "Calibration measurements"])
        self.assertEqual(history[0]["source_ref"], "local:1")
        self.assertEqual(self.bank.list_memories()[0]["content"], "Third revision")
        self.assertEqual(len(self.bank.list_memories()), 1)

    def test_delete_cascades_memberships_and_old_content(self):
        ident = self.memory(tags=["Safe cleanup"])
        self.bank.update_memory(ident, "Replacement")
        self.bank.remove_memory(str(ident))
        self.assertEqual(self.bank.memory_nodes(ident), [])
        self.assertEqual(self.bank.memory_history(ident), [])
        self.assertEqual(self.bank.search_memory("Safe cleanup"), [])

    def test_invalid_links_leave_no_rows(self):
        node = self.bank.create_knowledge_node("Valid")
        with self.assertRaises(KeyError):
            self.bank.link_memory_node(9999, node["id"])
        for confidence in [float("nan"), float("inf"), -1, 2]:
            with self.assertRaises(ValueError):
                self.bank.link_knowledge_nodes(node["id"], node["id"] + 1, confidence=confidence)
        self.assertEqual(self.bank.inspect_knowledge_node(node["id"])["edges"], [])

    def test_unlink_manual_only_and_literal_filter(self):
        ident = self.memory(tags=["100%_tested"])
        node = self.bank.list_knowledge_nodes("100%_tested")[0]
        self.bank.link_memory_node(ident, node["id"])
        self.bank.link_memory_node(ident, node["id"], unlink=True)
        self.assertEqual(self.bank.memory_nodes(ident)[-1]["origins"], "tag")
        self.assertFalse(self.bank.list_knowledge_nodes("%_unmatched"))

    def test_markdown_is_returned_without_writing_files(self):
        ident = self.memory(source="Manual", source_ref="local:notes")
        node = self.bank.create_knowledge_node("Test project", "project")
        self.bank.link_memory_node(ident, node["id"])
        exported = self.bank.export_knowledge_markdown(node["id"])
        self.assertIn("# Test project", exported["markdown"])
        self.assertIn("local:notes", exported["markdown"])
        self.assertIn(f"[memory:{ident}]", exported["markdown"])
        self.assertEqual(list(Path(self.temp.name).rglob("*.md")), [])

    def test_existing_schema_migrates_and_restart_is_idempotent(self):
        path = Path(self.temp.name) / "storage" / "databases" / "memory_bank.db"
        path.parent.mkdir(parents=True)
        # Baseline schema fixture has neither nodes nor history.
        with sqlite3.connect(path) as conn:
            conn.execute("""CREATE TABLE memories(id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,memory_type TEXT NOT NULL,summary TEXT NOT NULL,
                content TEXT NOT NULL,source TEXT NOT NULL,source_ref TEXT NOT NULL,
                tags_json TEXT NOT NULL,importance REAL NOT NULL,content_hash TEXT UNIQUE,
                learned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            conn.execute("""INSERT INTO memories(name,memory_type,summary,content,source,
                source_ref,tags_json,importance,content_hash) VALUES(?,?,?,?,?,?,?,?,?)""",
                ("Baseline", "knowledge", "", "Original stored body", "Owner", "local:old",
                 json.dumps(["XTTS"]), 1, "fixture"))
        for _ in range(2):
            migrated = Module({"base_dir": self.temp.name})
            try:
                self.assertEqual(migrated.list_memories()[0]["content"], "Original stored body")
                self.assertEqual(migrated.list_knowledge_nodes("XTTS")[0]["memory_count"], 1)
                self.assertEqual(migrated.conn.execute("SELECT count(*) FROM memory_node_links").fetchone()[0], 3)
            finally:
                migrated.close()

    def test_context_manager_uses_same_memories_and_honours_packet_budget(self):
        from modules.context_manager.module import Module as ContextModule
        ident = self.memory("XTTS evidence", "Local speech model settings", tags=["XTTS"])
        bank = self.bank
        class Manager:
            def get_module(self, key):
                return {"enabled": True, "instance": bank} if key == "memory_bank" else None
            def execute(self, module, action, arguments):
                self_call = (module, action)
                self_test_case.assertEqual(self_call, ("memory_bank", "knowledge_context"))
                return bank.run(action, arguments)
        self_test_case = self
        class Runtime:
            _manager = Manager()
            def capability_records(self, manager): return []
            def blackboard_all(self): return {}
            def task_history(self, limit): return []
            def goals(self, state): return [{"title": "x" * 5000}]
            def permission_profile(self): return "normal"
            def blackboard_set(self, key, packet, source): self.packet = packet
        context = ContextModule({"base_dir": self.temp.name, "runtime": Runtime()})
        result = context.run("build_context", {"task": "XTTS", "max_chars": 1200})
        self.assertIn(ident, result["knowledge"]["memory_ids"])
        self.assertLessEqual(len(json.dumps(result)), 1200)
        result = context.run("build_context", {"task": "XTTS", "include_knowledge": False})
        self.assertNotIn("knowledge", result)

    def test_research_verb_does_not_expand_the_whole_research_section(self):
        unrelated = self.memory("Garden biology", "Moss photosynthesis")
        matches = self.bank.search_memory("Research XTTS")
        self.assertNotIn(unrelated, [item["id"] for item in matches])

    def test_normal_chat_exposes_node_tools_only_for_memory_requests(self):
        from tests.test_growth_chat_routing import router_class
        tools = [{"function": {"name": "memory_bank__create_knowledge_node"}},
                 {"function": {"name": "file_manager__write_file"}}]
        router = router_class()()
        router.module_manager = None
        router.messages = [{"role": "user", "content": "Create a knowledge node for Apollo voice"}]
        self.assertEqual(router._select_tools(tools), tools[:1])
        router.messages.append({"role": "user", "content": "Hello"})
        self.assertEqual(router._select_tools(tools), [])


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtWidgets import (QApplication, QTreeWidget, QListWidget,
                                   QTextBrowser, QPushButton, QInputDialog)
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None, "PySide6 not installed")
class KnowledgeQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_real_browser_select_create_attach_and_export(self):
        with tempfile.TemporaryDirectory() as root:
            bank = Module({"base_dir": root, "validation": True})
            self.addCleanup(bank.close)
            ident = bank.store_memory("Voice record", "Use local XTTS", tags=["XTTS"], source="Owner")["id"]
            widget = bank.build_ui()
            self.addCleanup(widget.close)
            widget.resize(1200, 760); widget.show(); widget.setCurrentIndex(1)
            self.app.processEvents()
            tree = widget.findChild(QTreeWidget, "knowledge_nodes_tree")
            target = next(tree.topLevelItem(i) for i in range(tree.topLevelItemCount())
                          if tree.topLevelItem(i).text(0).startswith("XTTS"))
            tree.setCurrentItem(target)
            memories = widget.findChild(QListWidget, "knowledge_node_memories")
            self.assertEqual(memories.count(), 1)
            memories.setCurrentRow(0)
            self.assertIn("Use local XTTS", widget.findChild(QTextBrowser, "knowledge_node_details").toPlainText())
            buttons = {button.text(): button for button in widget.findChildren(QPushButton)}
            from PySide6.QtWidgets import QMessageBox, QFileDialog
            with patch.object(QInputDialog, "getText", return_value=("Apollo voice", True)), \
                 patch.object(QInputDialog, "getItem", return_value=("project", True)), \
                 patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
                buttons["New node"].click()
            with patch.object(QInputDialog, "getInt", return_value=(ident, True)):
                buttons["Link memory"].click()
            self.assertEqual(memories.count(), 1)
            node = bank.list_knowledge_nodes("Apollo voice")[0]
            self.assertEqual(node["memory_count"], 1)
            filename = Path(root) / "export.md"
            with patch.object(QFileDialog, "getSaveFileName", return_value=(str(filename), "")):
                buttons["Export selected node as Markdown"].click()
            self.assertIn("Use local XTTS", filename.read_text())
            buttons["Unlink memory"].click()  # Selection is optional; no accidental removal.
            self.assertTrue(bank.list_memories())


if __name__ == "__main__":
    unittest.main()
