from pathlib import Path
import tempfile
import json
import shutil

from module_manager import ModuleManager

ROOT = Path(tempfile.mkdtemp(prefix="apollo_hotload_test_"))
try:
    modules = ROOT / "modules"
    pending = ROOT / "pending_modules"
    modules.mkdir()
    pending.mkdir()

    validator = ROOT / "module_validator.py"
    validator.write_text("""
import json, sys
print(json.dumps({"ok": True, "id": __import__("pathlib").Path(sys.argv[1]).name}))
""", encoding="utf-8")

    manager = ModuleManager(
        modules,
        ROOT / "modules_state.json",
        context={"base_dir": str(ROOT)},
        pending_dir=pending,
        validator_path=validator,
    )

    candidate = pending / "hello_module"
    candidate.mkdir()
    (candidate / "manifest.json").write_text(json.dumps({
        "id": "hello_module",
        "name": "Hello",
        "version": "1.0.0",
        "entrypoint": "module.py",
        "class": "Module"
    }), encoding="utf-8")
    (candidate / "module.py").write_text("""
class Module:
    def __init__(self, context=None):
        self.context = context or {}
    def tools(self):
        return [{"name":"hello","description":"hello","parameters":{"type":"object","properties":{}}}]
    def run(self, action, arguments):
        if action == "hello":
            return {"hello":"world"}
        raise KeyError(action)
    def self_test(self):
        return True
""", encoding="utf-8")

    blocked = manager.activate_certified_pending("hello_module", approved=False)
    assert blocked["ok"] is False and blocked["stage"] == "approval"

    result = manager.activate_certified_pending("hello_module", approved=True)
    assert result["ok"] is True
    assert manager.get_module("hello_module")["instance"] is not None
    assert manager.execute("hello_module", "hello", {})["hello"] == "world"

    # Approved upgrade test.
    upgrade = pending / "hello_module"
    upgrade.mkdir()
    (upgrade / "manifest.json").write_text(json.dumps({
        "id": "hello_module",
        "name": "Hello",
        "version": "2.0.0",
        "entrypoint": "module.py",
        "class": "Module"
    }), encoding="utf-8")
    (upgrade / "module.py").write_text("""
class Module:
    def __init__(self, context=None):
        self.context = context or {}
    def tools(self):
        return [{"name":"hello","description":"hello","parameters":{"type":"object","properties":{}}}]
    def run(self, action, arguments):
        if action == "hello":
            return {"hello":"version2"}
        raise KeyError(action)
    def self_test(self):
        return True
""", encoding="utf-8")

    upgraded = manager.activate_certified_pending(
        "hello_module",
        approved=True,
        replace_existing=True,
    )
    assert upgraded["ok"] is True and upgraded["upgrade"] is True
    assert manager.execute("hello_module", "hello", {})["hello"] == "version2"

    print("Certified activation tests passed.")
finally:
    shutil.rmtree(ROOT, ignore_errors=True)
