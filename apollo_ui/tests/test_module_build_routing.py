import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORKERS = ROOT / "workers.py"


def _method_source(name):
    source = WORKERS.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(name)


def test_generalized_module_route_present():
    source = WORKERS.read_text(encoding="utf-8")
    assert "def _explicit_module_request_body(self):" in source
    assert "APOLLO WORKSHOP REQUEST:" in source
    assert "SELF IMPROVEMENT WORKSHOP REQUEST:" in source
    assert "request = (\n            self._explicit_module_request_body()\n        )" in source


def test_fake_validate_is_explicitly_forbidden():
    source = _method_source("_run_explicit_module_build")
    assert "module_factory__validate" in source
    assert "nonexistent" in source or "Do NOT invent" in source


if __name__ == "__main__":
    test_generalized_module_route_present()
    test_fake_validate_is_explicitly_forbidden()
    print("module build routing regressions: PASS")
