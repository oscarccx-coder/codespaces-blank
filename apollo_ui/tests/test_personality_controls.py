"""Regression checks for Apollo's configurable conversational style."""
import unittest
from pathlib import Path
from apollo_personality import normalize_sarcasm_level, personality_instruction


class PersonalityTests(unittest.TestCase):
    def test_levels_and_bounds(self):
        self.assertEqual(normalize_sarcasm_level("3"), 3)
        self.assertEqual(normalize_sarcasm_level(-3), 0)
        self.assertEqual(normalize_sarcasm_level(42), 3)
        self.assertEqual(normalize_sarcasm_level("bad"), 1)
        self.assertIn("Neutral", personality_instruction(0))
        self.assertIn("Mad Scientist", personality_instruction(3))

    def test_every_level_enforces_high_stakes_limits(self):
        for n in range(4):
            with self.subTest(level=n):
                instruction = personality_instruction(n)
                self.assertIn("medical", instruction.lower())
                self.assertIn("safety", instruction.lower())
                self.assertIn("Drop humour", instruction)

    def test_live_ui_wiring_present(self):
        source = Path(__file__).with_name("main.py").read_text(encoding="utf-8")
        self.assertIn('system += personality_instruction(self.config.get("sarcasm_level", 1))', source)
        self.assertIn('self.setting_sarcasm_level = QComboBox()', source)
        self.assertIn('self.config["sarcasm_level"] = normalize_sarcasm_level(', source)


if __name__ == "__main__":
    unittest.main()
