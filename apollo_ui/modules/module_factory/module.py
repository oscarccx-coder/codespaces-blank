import json
import re
from pathlib import Path


VALID_ID = re.compile(r"^[a-zA-Z0-9_-]+$")


class Module:
    def __init__(self, context=None):
        context = context or {}
        self.base = Path(context.get("base_dir", ".")).resolve()
        self.pending = (self.base / "pending_modules").resolve()
        self.pending.mkdir(parents=True, exist_ok=True)
        self.template = self.base / "modules" / "_template"

    def tools(self):
        return [
            {
                "name": "get_contract",
                "description": (
                    "Read Apollo's official module manifest/module templates and rules. "
                    "Use this BEFORE creating or repairing an Apollo module."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "read_candidate",
                "description": (
                    "Read the current files of an existing pending Apollo module "
                    "so you can diagnose and repair it."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "module_id": {"type": "string"}
                    },
                    "required": ["module_id"]
                }
            },
            {
                "name": "create_candidate",
                "description": (
                    "Create a NEW Apollo module candidate in pending_modules. "
                    "This does NOT install or enable the module. The candidate must "
                    "pass validation/tests and then be explicitly approved by the user."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "module_id": {"type": "string"},
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "module_code": {
                            "type": "string",
                            "description": (
                                "Complete Python source for module.py. It must define "
                                "class Module and follow the Apollo module contract."
                            )
                        },
                        "tests_code": {
                            "type": "string",
                            "description": (
                                "Optional complete tests.py source. Tests must be "
                                "non-interactive and safe."
                            )
                        },
                        "version": {"type": "string"},
                        "ui": {
                            "type": "object",
                            "description": (
                                "Optional Apollo UI metadata. When enabled, module.py must implement "
                                "build_ui(parent=None, ui_context=None)."
                            ),
                            "properties": {
                                "enabled": {"type": "boolean"},
                                "title": {"type": "string"},
                                "default_placement": {"type": "string"}
                            }
                        }
                    },
                    "required": [
                        "module_id", "name", "description", "module_code"
                    ]
                }
            },
            {
                "name": "update_candidate_file",
                "description": (
                    "Modify a file in an existing PENDING module to repair it. "
                    "Allowed files: module.py, manifest.json, tests.py, README.md. "
                    "The module remains pending until validation and user approval."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "module_id": {"type": "string"},
                        "filename": {"type": "string"},
                        "content": {"type": "string"}
                    },
                    "required": ["module_id", "filename", "content"]
                }
            }
        ]

    def _module_dir(self, module_id):
        module_id = str(module_id or "").strip()
        if not VALID_ID.match(module_id):
            raise ValueError("Invalid module_id.")

        target = (self.pending / module_id).resolve()
        if self.pending not in target.parents:
            raise PermissionError("Path escaped pending_modules.")
        return target

    def self_test(self):
        test = self._module_dir("validation_test")
        assert self.pending in test.parents
        return "Pending-module path safety passed."

    def _read_text(self, path, max_chars=120000):
        if not path.exists() or not path.is_file():
            return ""
        return path.read_text(
            encoding="utf-8",
            errors="replace"
        )[:max_chars]

    def run(self, action, arguments):
        arguments = arguments or {}

        if action == "get_contract":
            return {
                "manifest_template": self._read_text(
                    self.template / "manifest.json"
                ),
                "module_template": self._read_text(
                    self.template / "module.py"
                ),
                "module_api": self._read_text(
                    self.template / "MODULE_API.md"
                ),
                "rules": [
                    "Entrypoint normally defines class Module.",
                    "tools() returns Apollo tool definitions.",
                    "run(action, arguments) executes exposed actions.",
                    "self_test() should raise or return False on failure.",
                    "tests.py may provide additional non-interactive tests.",
                    "New modules stay pending until validation and user approval.",
                    "UI modules set manifest.ui.enabled=true and implement build_ui(parent=None, ui_context=None).",
                    "Import PySide6 inside build_ui rather than at module import time so validation remains headless-safe.",
                    "Once validation passes, stop modifying the candidate.",
                    "Never repeat an identical create/update call.",
                ],
            }

        if action == "read_candidate":
            module_id = str(arguments.get("module_id", "")).strip()
            folder = self._module_dir(module_id)
            if not folder.exists():
                raise FileNotFoundError(module_id)

            result = {}
            for filename in [
                "manifest.json",
                "module.py",
                "tests.py",
                "README.md",
            ]:
                path = folder / filename
                if path.exists():
                    result[filename] = self._read_text(path)

            return {
                "module_id": module_id,
                "files": result,
                "status": "PENDING - not installed.",
            }

        if action == "create_candidate":
            module_id = str(arguments.get("module_id", "")).strip()
            folder = self._module_dir(module_id)

            if folder.exists():
                raise FileExistsError(
                    "Candidate already exists. Read it and repair it instead."
                )

            folder.mkdir(parents=True)

            manifest = {
                "id": module_id,
                "name": str(arguments.get("name", module_id)),
                "version": str(arguments.get("version", "1.0")),
                "entrypoint": "module.py",
                "class": "Module",
                "description": str(arguments.get("description", "")),
            }

            ui = arguments.get("ui")
            if isinstance(ui, dict) and bool(ui.get("enabled")):
                placement = str(ui.get("default_placement", "apps")).strip().lower()
                if placement not in {"apps", "sidebar", "none"}:
                    placement = "apps"
                manifest["ui"] = {
                    "enabled": True,
                    "title": str(ui.get("title") or manifest["name"]),
                    "default_placement": placement,
                }

            (folder / "manifest.json").write_text(
                json.dumps(manifest, indent=2) + "\n",
                encoding="utf-8"
            )
            (folder / "module.py").write_text(
                str(arguments.get("module_code", "")).rstrip() + "\n",
                encoding="utf-8"
            )

            tests_code = str(arguments.get("tests_code", "") or "")
            if tests_code.strip():
                (folder / "tests.py").write_text(
                    tests_code.rstrip() + "\n",
                    encoding="utf-8"
                )

            return {
                "created": True,
                "module_id": module_id,
                "folder": str(folder),
                "status": (
                    "PENDING ONLY. It is not installed. "
                    "Apollo should inspect the validation result and repair "
                    "the candidate until it passes."
                )
            }

        if action == "update_candidate_file":
            module_id = str(arguments.get("module_id", "")).strip()
            folder = self._module_dir(module_id)
            if not folder.exists():
                raise FileNotFoundError(module_id)

            filename = str(
                arguments.get("filename", "")
            ).strip().replace("\\", "/")

            if filename not in {
                "module.py",
                "manifest.json",
                "tests.py",
                "README.md",
            }:
                raise PermissionError(
                    "Only module.py, manifest.json, tests.py or README.md "
                    "may be updated."
                )

            target = (folder / filename).resolve()
            if folder not in target.parents:
                raise PermissionError("Path escaped candidate folder.")

            content = str(arguments.get("content", ""))
            if len(content.encode("utf-8")) > 600_000:
                raise ValueError("Candidate file is too large.")

            target.write_text(content, encoding="utf-8")

            return {
                "updated": True,
                "module_id": module_id,
                "path": str(target),
                "status": (
                    "Still pending. Apollo should rerun validation and continue "
                    "repairing until it passes."
                )
            }

        raise KeyError(action)
