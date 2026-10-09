"""Qt-free structural regression for Voice Lab profile management and startup UI."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class VoiceUIWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.voice_text = (ROOT / "modules/voice_imprint_trainer/module.py").read_text(encoding="utf-8")
        cls.main_text = (ROOT / "main.py").read_text(encoding="utf-8")
        cls.voice_tree = ast.parse(cls.voice_text)
        cls.window_tree = ast.parse(cls.main_text)

    def test_voice_profile_management_present_and_ui_only(self):
        source = self.voice_text
        for needed in (
            "rename_profile_from_ui", "archive_profile_from_ui", "reorder_profiles_from_ui",
            "test_voice_combo", "choose_test_voice", "open_profile_menu",
            "voice_menu_button", "menu.addAction", "Retrain voice",
            "advanced_voice_button", "right_scroll", "QMessageBox.question",
            "self.library.ordered_ids()",
            "test_voice_combo.currentIndexChanged.connect(select_test_voice)",
            "choose_test_voice.clicked.connect(do_activate)",
        ):
            self.assertIn(needed, source)
        voices = next(x for x in self.voice_tree.body if isinstance(x, ast.ClassDef) and x.name == "Module")
        methods = {node.name: node for node in voices.body if isinstance(node, ast.FunctionDef)}
        tools_source = ast.get_source_segment(source, methods["tools"])
        for forbidden in ("archive_profile_from_ui", "rename_profile_from_ui", "reorder_profiles_from_ui"):
            self.assertNotIn(forbidden, tools_source)

    def test_startup_recentered_once_not_restored_to_old_coordinates(self):
        source = self.main_text
        self.assertIn("from apollo_window_geometry import centered_window_geometry", source)
        self.assertIn("QTimer.singleShot(0, win.center_on_startup)", source)
        window = next(node for node in self.window_tree.body if isinstance(node, ast.ClassDef) and node.name == "ApolloWindow")
        methods = {node.name: node for node in window.body if isinstance(node, ast.FunctionDef)}
        init = ast.get_source_segment(source, methods["__init__"])
        self.assertNotIn('saved_window.get("x"', init)
        self.assertNotIn('saved_window.get("y"', init)
        self.assertIn("self._startup_centre_pending = True", init)
        self.assertIn("QApplication.screenAt(QCursor.pos())", ast.get_source_segment(source, methods["center_on_startup"]))


if __name__ == "__main__":
    unittest.main()
