"""Qt-free structural checks for sidebar integration in the large main.py."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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

    def test_any_installed_ui_app_can_be_pinned_from_sidebar(self):
        source = self.source
        self.assertIn("self.sidebar_state.register_module(", source)
        self.assertIn('self.sidebar_module_defaults[page_key] = placement == "sidebar"', source)
        self.assertIn("self.open_module_app(target)", source)
        self.assertIn("Add / Remove Apps", source)
        self.assertIn("Find an app to add or remove...", source)
        self.assertIn("self._sidebar_shortcut_menu(k, b, position)", source)
        self.assertIn("self.sidebar_state.set_visible(key, False)", source)
        self.assertIn('self.sidebar_state.reset(getattr(self, "sidebar_module_defaults", {}))', source)
        self.assertIn("_sidebar_shortcut_menu", self.methods)
        self.assertIn("register_module", (ROOT / "apollo_sidebar.py").read_text(encoding="utf-8"))

    def test_anchors_are_not_in_reorderable_host(self):
        text = ast.get_source_segment(self.source, self.methods["_build_sidebar"])
        self.assertIn('v.addWidget(self.nav_buttons["Hub"])', text)
        self.assertIn('v.addWidget(self.nav_buttons["Settings"])', text)
        self.assertIn('self.sidebar_nav_layout = QVBoxLayout(self.sidebar_nav_host)', text)


if __name__ == "__main__":
    unittest.main()
