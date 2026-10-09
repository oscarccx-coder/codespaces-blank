"""Qt-free wiring tests for the user-facing Apollo simplification."""
import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FriendlyUITests(unittest.TestCase):
    def test_voice_menu_and_panel_structure(self):
        source = (ROOT / "modules/voice_imprint_trainer/module.py").read_text(encoding="utf-8")
        ast.parse(source)
        for token in (
            "def open_profile_menu", "voice_menu_button", "setItemWidget",
            "Retrain voice", "Delete voice", "def test_selected_profile",
            "advanced_voice_button", "right_scroll", "QScrollArea",
        ):
            self.assertIn(token, source)
        self.assertNotIn("archive_profile_button = QPushButton", source)

    def test_curiosity_research_is_actionable(self):
        source = (ROOT / "modules/reasoning_director/module.py").read_text(encoding="utf-8")
        ast.parse(source)
        for token in (
            'QPushButton("Research These Topics")',
            "def research_queued_topics", "research_all.clicked.connect",
            "explore_web_and_save", "source_pages_fetched",
            "advanced_panel.hide()", "More options",
        ):
            self.assertIn(token, source)

    def test_updater_is_simple_but_keeps_trust_controls(self):
        source = (ROOT / "modules/update_manager/module.py").read_text(encoding="utf-8")
        ast.parse(source)
        for token in (
            'QPushButton("Check for Updates")',
            'QPushButton("Update & Restart")',
            "advanced_panel.hide()", "output.hide()",
            "trust_github_btn", "import_trusted_key",
            "self.service.stage_update", "self.service.launch_installer",
        ):
            self.assertIn(token, source)

    def test_developer_tests_separated_from_release_payload(self):
        source = (ROOT / "apollo_release.py").read_text(encoding="utf-8")
        ast.parse(source)
        self.assertIn('"tests"', source)
        self.assertTrue((ROOT / "docs/patch_notes/2026-10-10_UI_USABILITY.md").is_file())


if __name__ == "__main__":
    unittest.main()
