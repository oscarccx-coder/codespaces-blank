"""Qt-free structural checks for sidebar integration in the large main.py."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class SidebarWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "main.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source, filename="main.py")
        cls.window = next(
            node for node in cls.tree.body
            if isinstance(node, ast.ClassDef) and node.name == "ApolloWindow"
        )
        cls.methods = {
            node.name: node for node in cls.window.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

    def test_parser_and_expected_methods(self):
        for method in (
            "_build_sidebar", "_refresh_sidebar", "open_sidebar_manager",
            "rebuild_module_ui", "_build_settings", "switch_page",
        ):
            self.assertIn(method, self.methods)

    def test_layout_registry_and_editor_are_connected(self):
        source = self.source
        self.assertIn("from apollo_sidebar import SidebarLayoutStore", source)
        self.assertIn("self.sidebar_state = SidebarLayoutStore(BASE_DIR)", source)
        self.assertIn("self.sidebar_customize_btn.clicked.connect(self.open_sidebar_manager)", source)
        self.assertIn("sidebar_settings_btn.clicked.connect(self.open_sidebar_manager)", source)
        self.assertIn("self.sidebar_default_labels[page_key]", source)
        self.assertIn("self._refresh_sidebar()", ast.get_source_segment(source, self.methods["rebuild_module_ui"]))
        self.assertIn("self.sidebar_nav_layout.addWidget(button)", source)

    def test_anchors_are_not_in_reorderable_host(self):
        text = ast.get_source_segment(self.source, self.methods["_build_sidebar"])
        self.assertIn('v.addWidget(self.nav_buttons["Hub"])', text)
        self.assertIn('v.addWidget(self.nav_buttons["Settings"])', text)
        self.assertIn('self.sidebar_nav_layout = QVBoxLayout(self.sidebar_nav_host)', text)


if __name__ == "__main__":
    unittest.main()
