"""Hardware/game-free Apollo Circuit Lab regression tests."""
import ast
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from apollo_circuit_lab import (
    CircuitProjectStore, EXAMPLES, inspect_crumb_save, resistor_for_led
)
from apollo_module_catalog import group_for


ROOT = Path(__file__).resolve().parents[1]


class CircuitLabTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_led_calculation_e12_and_power(self):
        result = resistor_for_led(5, 2, 10)
        self.assertEqual(result["suggested_e12_ohms"], 330)
        self.assertAlmostEqual(result["estimated_current_ma"], 9.09, places=2)
        self.assertLess(result["resistor_dissipation_w"], 0.05)
        self.assertEqual(result["suggested_resistor_rating_w"], 0.25)

    def test_reject_invalid_or_hazardous_inputs(self):
        invalid = ((230, 2, 10), (5, 6, 10), (5, 2, 0), (5, 2, 500),
                   (float("nan"), 2, 10), (5, float("inf"), 10))
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValueError):
                resistor_for_led(*values)

    def test_project_persists_in_private_storage(self):
        store = CircuitProjectStore(self.dir)
        project = store.create_project("Prototype One", "Simple LED", template="led")
        self.assertEqual(len(project["components"]), 4)
        self.assertEqual(store.get_project(project["id"])["name"], "Prototype One")
        self.assertEqual(store.list_projects()[0]["id"], project["id"])
        updated = store.set_notes(project["id"], "Voltage: 5 V, powered off before wiring")
        self.assertIn("powered off", updated["notes"])
        reloaded = CircuitProjectStore(self.dir).get_project(project["id"])
        self.assertEqual(reloaded["notes"], updated["notes"])
        self.assertTrue((self.dir / "storage/projects/electronics").is_dir())

    def test_project_id_guards_and_bad_names(self):
        store = CircuitProjectStore(self.dir)
        for name in ("", " " * 12, "X" * 90):
            with self.subTest(name=name), self.assertRaises(ValueError):
                store.create_project(name)
        with self.assertRaises(ValueError):
            store.get_project("../outside")
        with self.assertRaises(ValueError):
            store.create_project("test", template="arbitrary_code")
        project = store.create_project("Valid Name")
        with self.assertRaises(ValueError):
            store.set_notes(project["id"], "too long" * 1200)

    def test_cru_is_read_only_xml_metadata_not_circuit_proof(self):
        original = b'<Circuit><Components><Component type="RESISTOR" /><Component type="LED"/></Components></Circuit>'
        file = self.dir / "safe.cru"
        file.write_bytes(original)
        summary = inspect_crumb_save(file)
        self.assertEqual(summary["xml_root"], "Circuit")
        self.assertEqual(summary["xml_tag_frequencies"]["Component"], 2)
        self.assertFalse(summary["claims"]["electrical_wiring_verified"])
        self.assertFalse(summary["claims"]["project_modified"])
        self.assertEqual(file.read_bytes(), original)
        self.assertEqual(summary["compatibility"], "unknown until validated against this CRUMB game version")

    def test_cru_refuses_malformed_dtd_oversize_and_other_formats(self):
        file = self.dir / "bad.cru"
        payloads = [
            b"not XML", b'<!DOCTYPE circuit [<!ENTITY a "foo">]><Circuit>&a;</Circuit>',
            b"<Circuit>" + b"a" * (8 * 1024 * 1024),
        ]
        for data in payloads:
            with self.subTest(size=len(data)):
                file.write_bytes(data)
                with self.assertRaises(ValueError):
                    inspect_crumb_save(file)
        file.rename(self.dir / "different.txt")
        with self.assertRaises(ValueError):
            inspect_crumb_save(self.dir / "different.txt")

    def test_module_tool_bus_has_only_safe_math_and_templates(self):
        path = ROOT / "modules/circuit_lab/module.py"
        spec = importlib.util.spec_from_file_location("apollo_circuit_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        instance = module.Module({"base_dir": self.dir, "validation": True})
        self.assertTrue(instance.self_test())
        names = {item["name"] for item in instance.tools()}
        self.assertEqual(names, {"circuit_example_templates", "circuit_led_resistor"})
        self.assertEqual(len(instance.run("circuit_example_templates", {})["templates"]), len(EXAMPLES))
        with self.assertRaises(KeyError):
            instance.run("execute_cru_commands", {"path": "../test.cru"})

    def test_ui_wiring_is_present_but_never_invokes_game_in_background(self):
        source = (ROOT / "modules/circuit_lab/module.py").read_text(encoding="utf-8")
        ast.parse(source)
        for required in (
            "Split-screen Companion", "Launch CRUMB in Steam", "steam://rungameid/2198800",
            "Inspect CRUMB .cru Save (Read-Only)", "Ask Apollo", "chat_once",
            "QDesktopServices.openUrl", "create_project", "set_notes",
        ):
            self.assertIn(required, source)
        self.assertNotIn("os.system(", source)
        self.assertNotIn("subprocess.Popen(", source)
        self.assertEqual(group_for("circuit_lab"), "Everyday")


if __name__ == "__main__":
    unittest.main()
