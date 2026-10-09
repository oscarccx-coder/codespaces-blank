"""Qt-free regression assertions for the 7.5.13.8 interface and 7.5.13.9 cleanup."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FriendlyUITests(unittest.TestCase):
    def test_voice_profiles_have_per_item_actions(self):
        voice = (ROOT / "modules/voice_imprint_trainer/module.py").read_text(encoding="utf-8")
        ast.parse(voice)
        for token in ('QToolButton', 'QMenu(dots)', '("Retrain", "retrain")',
                      '("Delete…", "delete")', 'profiles_list.setItemWidget(item, cell)',
                      'make_voice_tab("Advanced Settings")', 'make_voice_tab("Test / Use")'):
            self.assertIn(token, voice)

    def test_learning_can_research_selected_topic(self):
        learning = (ROOT / "modules/reasoning_director/module.py").read_text(encoding="utf-8")
        ast.parse(learning)
        for token in ('QPushButton("Research This Topic")', 'def do_research():',
                      '"explore_web_and_save"', 'research.clicked.connect(do_research)',
                      'More options'):
            self.assertIn(token, learning)

    def test_updater_keeps_signing_and_avoids_stale_install(self):
        ui = (ROOT / "modules/update_manager/module.py").read_text(encoding="utf-8")
        ast.parse(ui)
        for token in ('QPushButton("Update Apollo")', 'Advanced options',
                      'advanced_panel.setVisible(False)', 'trust_github_btn',
                      'self.service.stage_update', 'self.service.launch_installer',
                      'not result.get("stage_dir")'):
            self.assertIn(token, ui)

    def test_tests_not_bundled_in_signed_application(self):
        release = (ROOT / "apollo_release.py").read_text(encoding="utf-8")
        ast.parse(release)
        self.assertIn('"tests"', release)
        self.assertIn('"remove": legacy_root_tests', release)
        self.assertTrue((ROOT / "docs/patch_notes/2026-10-10_UI_USABILITY.md").is_file())


if __name__ == "__main__":
    unittest.main()
