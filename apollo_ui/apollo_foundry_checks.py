"""Apollo Foundry Phase 1: static, non-executing project / UI wiring checks.

These checks do NOT start applications or execute generated project code.
Real Qt click-through tests are only run on trusted Apollo-owned CI fixtures.
"""
from __future__ import annotations

import ast
from datetime import datetime, timezone
import json
from pathlib import Path, PurePosixPath, PureWindowsPath

MAX_SOURCE_FILES = 60
MAX_TOTAL_BYTES = 2 * 1024 * 1024
MAX_FILE_BYTES = 256 * 1024
MAX_MANIFEST_BYTES = 64 * 1024


def _safe_file(folder, value):
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ValueError("Project file path must be a relative forward-slash path")
    p = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if p.is_absolute() or windows.drive or windows.root or any(
        part in ("", ".", "..") for part in value.split("/")
    ) or value.endswith("/") or ":" in value:
        raise ValueError("Unsafe project file path")
    if not value.endswith(".py"):
        raise ValueError("A UI/backend contract must refer to a Python file")
    current = folder
    for part in p.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Symlinked project files are not allowed")
    target = (folder / Path(*p.parts)).resolve()
    if not target.is_relative_to(folder.resolve()):
        raise ValueError("Project file escapes its workspace")
    return target


def _read_source(file):
    if not file.is_file() or file.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"Missing or oversized project source file: {file.name}")
    return ast.parse(file.read_text(encoding="utf-8-sig"), filename=file.name)


def _class(tree, name):
    return next((x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == name), None)


def _methods(cls):
    return {node.name: node for node in cls.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _is_self_attr(value, name):
    return (isinstance(value, ast.Attribute) and value.attr == name
            and isinstance(value.value, ast.Name) and value.value.id == "self")


def _has_widget(cls, widget):
    for node in ast.walk(cls):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(_is_self_attr(t, widget) for t in targets):
                return True
    return False


def _has_connection(cls, widget, signal, handler):
    for node in ast.walk(cls):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "connect" or len(node.args) != 1:
            continue
        if not isinstance(node.func.value, ast.Attribute):
            continue
        signal_node = node.func.value
        if signal_node.attr != signal or not _is_self_attr(signal_node.value, widget):
            continue
        if _is_self_attr(node.args[0], handler):
            return True
    return False


def _handler_calls_backend(handler_method, backend_attr, method):
    for node in ast.walk(handler_method):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == method and _is_self_attr(node.func.value, backend_attr):
                return True
    return False


def scan_project(folder: Path) -> dict:
    """Inspect a single ID-generated private project folder; never recurse outside it."""
    folder = Path(folder).resolve()
    findings = []
    seen = set()

    def add(key, status, detail):
        if key in seen:
            return
        seen.add(key)
        findings.append({"check": key, "status": status, "detail": str(detail)[:500]})

    if not folder.is_dir():
        raise ValueError("Project folder does not exist")
    paths = list(folder.rglob("*"))
    if len(paths) > 350:
        raise ValueError("Project contains too many paths for a quick scan")
    if any(p.is_symlink() for p in paths):
        add("workspace-safety", "fail", "Symlink found; static scan refused")
        return _report(findings, 0)

    sources = sorted(p for p in paths if p.is_file() and p.suffix == ".py")
    if len(sources) > MAX_SOURCE_FILES:
        add("source-budget", "fail", "Too many Python source files for Phase 1")
        return _report(findings, len(sources))
    total = sum(p.stat().st_size for p in sources)
    if total > MAX_TOTAL_BYTES:
        add("source-budget", "fail", "Python source exceeds the Phase 1 size limit")
        return _report(findings, len(sources))
    if not sources:
        add("source-present", "pending", "No .py files yet. Add project code before checking UI.")
        return _report(findings, 0)

    trees = {}
    for path in sources:
        relative = path.relative_to(folder).as_posix()
        try:
            trees[relative] = _read_source(path)
            add("syntax:" + relative, "pass", "Python syntax is valid")
        except (SyntaxError, ValueError, UnicodeError) as err:
            add("syntax:" + relative, "fail", f"{type(err).__name__}: {err}")
    manifest_path = folder / "foundry.json"
    if manifest_path.is_symlink():
        add("ui-contract", "fail", "Symlinked UI manifest forbidden")
        return _report(findings, len(sources))
    if not manifest_path.is_file():
        add("ui-contract", "pending", "Add foundry.json to declare the UI/backend links.")
        return _report(findings, len(sources))
    try:
        if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ValueError("Manifest exceeds 64 KiB")
        contract = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(contract, dict) or contract.get("schema_version") != 1:
            raise ValueError("Expected schema_version: 1")
        ui = contract.get("ui")
        if not isinstance(ui, dict):
            raise ValueError("Manifest must contain a ui object")
        file_name, class_name = ui.get("file"), ui.get("class")
        if not isinstance(class_name, str) or not class_name.isidentifier():
            raise ValueError("Valid UI class name required")
        ui_path = _safe_file(folder, file_name)
        ui_rel = ui_path.relative_to(folder).as_posix()
        ui_tree = trees.get(ui_rel)
        if ui_tree is None:
            raise ValueError("UI source is missing or has invalid syntax")
        cls = _class(ui_tree, class_name)
        if cls is None:
            raise ValueError(f"UI class {class_name!r} not found in {ui_rel}")
        add("ui-class", "pass", f"Found {class_name} in {ui_rel}")
        bindings = ui.get("bindings")
        if not isinstance(bindings, list) or not 1 <= len(bindings) <= 40:
            raise ValueError("Declare between 1 and 40 UI bindings")
        for idx, binding in enumerate(bindings, 1):
            if not isinstance(binding, dict):
                raise ValueError(f"Binding {idx} must be an object")
            fields = ("widget", "signal", "handler", "backend_attribute",
                      "backend_file", "backend_class", "backend_method")
            for field in fields:
                item = binding.get(field)
                if not isinstance(item, str) or not item.isidentifier():
                    if field != "backend_file":
                        raise ValueError(f"Binding {idx}: invalid {field}")
            widget, signal, handler = (binding[x] for x in ("widget", "signal", "handler"))
            if not _has_widget(cls, widget):
                add(f"widget:{idx}", "fail", f"UI widget self.{widget} is not declared")
            else:
                add(f"widget:{idx}", "pass", f"UI widget self.{widget} declared")
            methods = _methods(cls)
            if handler not in methods:
                add(f"handler:{idx}", "fail", f"UI handler {handler} is missing")
            else:
                add(f"handler:{idx}", "pass", f"UI handler {handler} exists")
            if not _has_connection(cls, widget, signal, handler):
                add(f"signal:{idx}", "fail",
                    f"Missing self.{widget}.{signal}.connect(self.{handler})")
            else:
                add(f"signal:{idx}", "pass", f"Connected {widget}.{signal} -> {handler}")
            backend_path = _safe_file(folder, binding.get("backend_file"))
            backend_rel = backend_path.relative_to(folder).as_posix()
            backend_tree = trees.get(backend_rel)
            backend_cls = _class(backend_tree, binding["backend_class"]) if backend_tree else None
            backend_method = binding["backend_method"]
            if backend_cls is None or backend_method not in _methods(backend_cls):
                add(f"backend:{idx}", "fail", f"{backend_rel}:{binding['backend_class']}.{backend_method} not found")
            else:
                add(f"backend:{idx}", "pass", f"Backend method {backend_method} declared")
            if handler in methods and _handler_calls_backend(
                methods[handler], binding["backend_attribute"], backend_method
            ):
                add(f"call:{idx}", "pass", f"{handler} references self.{binding['backend_attribute']}.{backend_method}()")
            else:
                add(f"call:{idx}", "fail",
                    f"{handler} does not call self.{binding['backend_attribute']}.{backend_method}()")
    except (ValueError, OSError, UnicodeError, KeyError, TypeError, json.JSONDecodeError) as err:
        add("ui-contract", "fail", f"{type(err).__name__}: {err}")
    else:
        add("ui-contract", "pass", "Declared UI/backend links inspected statically")
    return _report(findings, len(sources))


def _report(checks, files_count):
    statuses = {x["status"] for x in checks}
    return {
        "phase": "Foundry 1",
        "kind": "static-ui-contract",
        "status": "failed" if "fail" in statuses else ("incomplete" if "pending" in statuses else "passed"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files_inspected": files_count,
        "checks": checks,
        "executed_project_code": False,
        "verified_runtime_ui": False,
        "note": "Passing means syntax and declared links were found in source. It does NOT prove the GUI launches, renders or works correctly.",
    }
