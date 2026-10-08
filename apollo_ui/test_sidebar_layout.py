"""Regression tests for Apollo's persistent custom sidebar; no Qt required."""
import json
import tempfile
import unittest
from pathlib import Path

from apollo_sidebar import CORE_ITEMS, SidebarLayoutStore


class SidebarLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.layout = SidebarLayoutStore(self.root)

    def test_defaults_keep_navigation(self):
        self.assertEqual(self.layout.ordered(CORE_ITEMS), list(CORE_ITEMS))
        self.assertTrue(self.layout.is_visible("Hub"))
        self.assertTrue(self.layout.is_visible("Settings"))
        self.assertEqual(self.layout.display_label("Hub", "Hub"), "Home")

    def test_reorder_hide_labels_and_width_survive_restart(self):
        self.layout.apply(
            ["Coding", "module::voice_imprint_trainer", "Chat"],
            ["Hub", "Settings", "Medical", "module::voice_imprint_trainer"],
            {"Coding": "Development", "module::voice_imprint_trainer": "Voice Lab"},
            300, True,
        )
        restored = SidebarLayoutStore(self.root)
        order = restored.ordered(
            ["Chat", "Coding", "Memory", "module::voice_imprint_trainer", "module::new"]
        )
        self.assertEqual(
            order,
            ["Coding", "module::voice_imprint_trainer", "Chat", "Memory", "module::new"],
        )
        self.assertTrue(restored.is_visible("Hub"))
        self.assertTrue(restored.is_visible("Settings"))
        self.assertFalse(restored.is_visible("Medical"))
        self.assertFalse(restored.is_visible("module::voice_imprint_trainer"))
        self.assertEqual(restored.display_label("Coding", "Workshop"), "Development")
        self.assertEqual(restored.state()["width"], 300)
        self.assertTrue(restored.state()["collapsed"])

    def test_new_or_missing_module_does_not_erase_preferences(self):
        self.layout.apply(
            ["module::test", "Chat"], ["module::test"], {"module::test": "Custom"}
        )
        self.assertNotIn("module::test", self.layout.ordered(["Chat"]))
        self.layout.apply(["Chat"], [], {"Chat": "Chat"})
        again = SidebarLayoutStore(self.root)
        self.assertFalse(again.is_visible("module::test"))
        self.assertEqual(again.display_label("module::test", "Test"), "Custom")

    def test_corruption_is_backed_up(self):
        self.layout.path.parent.mkdir(parents=True, exist_ok=True)
        self.layout.path.write_text("{ not json", encoding="utf-8")
        recovered = SidebarLayoutStore(self.root)
        self.assertEqual(recovered.ordered(CORE_ITEMS), list(CORE_ITEMS))
        self.assertTrue(list(self.layout.path.parent.glob("sidebar_layout.corrupt-*.json")))

    def test_untrusted_values_are_clamped_and_ignored(self):
        self.layout.path.parent.mkdir(parents=True, exist_ok=True)
        self.layout.path.write_text(json.dumps({
            "order": ["Chat", "Chat", "Hub", "Settings", "module::../bad"],
            "hidden": ["Settings", "Hub", "Chat"],
            "labels": {"Hub": "Bad", "Chat": "  Hello\nWorld  "},
            "width": 999999,
            "collapsed": False,
        }), encoding="utf-8")
        loaded = SidebarLayoutStore(self.root)
        self.assertEqual(loaded.ordered(["Chat", "Coding"]), ["Chat", "Coding"])
        self.assertFalse(loaded.is_visible("Chat"))
        self.assertTrue(loaded.is_visible("Hub"))
        self.assertTrue(loaded.is_visible("Settings"))
        self.assertEqual(loaded.display_label("Chat", "Chat"), "Hello World")
        self.assertEqual(loaded.display_label("Hub", "Hub"), "Home")
        self.assertEqual(loaded.state()["width"], 360)

    def test_reset_is_persistent(self):
        self.layout.apply(["Coding", "Chat"], ["Chat"], width=260, collapsed=True)
        self.layout.reset()
        fresh = SidebarLayoutStore(self.root)
        self.assertTrue(fresh.is_visible("Chat"))
        self.assertFalse(fresh.state()["collapsed"])
        self.assertEqual(fresh.state()["width"], 220)


if __name__ == "__main__":
    unittest.main()
