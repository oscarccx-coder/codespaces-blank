import tempfile
from pathlib import Path
from module_manager import ModuleManager


def main():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        modules = root / "modules"
        modules.mkdir()
        state = root / "modules_state.json"
        manager = ModuleManager(modules, state, context={"base_dir": str(root)})
        manager._loaded["demo"] = {
            "id": "demo",
            "manifest": {"id": "demo", "ui": {"enabled": True, "default_placement": "apps"}},
            "enabled": True,
            "instance": object(),
            "tools": [],
            "folder": modules / "demo",
            "validation": {"ok": True},
        }
        assert manager.get_ui_surfaces("demo") == ["apps"]
        manager.set_ui_surfaces("demo", ["apps", "sidebar"])
        assert manager.get_ui_surfaces("demo") == ["apps", "sidebar"]
        assert manager.get_ui_placement("demo") == "sidebar"
        manager.set_ui_placement("demo", "apps")
        assert manager.get_ui_surfaces("demo") == ["apps"]
        assert manager.get_ui_placement("demo") == "apps"
        manager.set_ui_placement("demo", "none")
        assert manager.get_ui_surfaces("demo") == []
    print("ModuleManager UI surface tests passed")


if __name__ == "__main__":
    main()
