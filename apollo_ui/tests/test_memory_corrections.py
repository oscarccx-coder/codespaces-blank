"""Tests for targeted Memory Bank corrections and search index consistency."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_FILE = ROOT / "modules" / "memory_bank" / "module.py"
spec = importlib.util.spec_from_file_location("apollo_memory_bank_test_module", MODULE_FILE)
code = importlib.util.module_from_spec(spec)
spec.loader.exec_module(code)


class MemoryCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.mem = code.Module({"base_dir": self.temp.name, "validation": True})
        self.addCleanup(self.mem.close)

    def test_correct_only_selected_memory(self):
        one = self.mem.store_memory("Fact A", "Some old data", "knowledge", source="manual")
        two = self.mem.store_memory("Fact B", "Retain original", "knowledge", source="manual")
        result = self.mem.update_memory(one["id"], "Corrected data")
        self.assertEqual(result["id"], one["id"])
        entries = {m["id"]: m for m in self.mem.list_memories()}
        self.assertEqual(entries[one["id"]]["content"], "Corrected data")
        self.assertEqual(entries[two["id"]]["content"], "Retain original")
        self.assertEqual(entries[one["id"]]["source"], "manual")
        self.assertTrue(any(m["id"] == one["id"] for m in self.mem.search_memory("Corrected", 10)))

    def test_reject_empty_and_unknown_and_duplicates(self):
        a = self.mem.store_memory("A", "one", source="manual")
        b = self.mem.store_memory("B", "two", source="manual")
        with self.assertRaises(ValueError):
            self.mem.update_memory(a["id"], " ")
        with self.assertRaises(KeyError):
            self.mem.update_memory(99999, "hello")
        with self.assertRaises(ValueError):
            self.mem.update_memory(a["id"], "two")
        self.assertEqual(self.mem.stats()["total_memories"], 2)


if __name__ == "__main__":
    unittest.main()
