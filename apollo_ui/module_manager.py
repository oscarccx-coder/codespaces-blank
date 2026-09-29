import importlib.util
import json
import re
import shutil
import subprocess
import sys
import threading
import traceback
from pathlib import Path


VALID_ID = re.compile(r"^[a-zA-Z0-9_-]+$")


def _hidden_subprocess_kwargs():
    """Prevent validator child processes from opening console windows on Windows."""
    if sys.platform != "win32":
        return {}

    kwargs = {}

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if creationflags:
        kwargs["creationflags"] = creationflags

    startupinfo_cls = getattr(subprocess, "STARTUPINFO", None)
    startf_use_showwindow = getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
    sw_hide = getattr(subprocess, "SW_HIDE", 0)

    if startupinfo_cls is not None:
        startupinfo = startupinfo_cls()
        startupinfo.dwFlags |= startf_use_showwindow
        startupinfo.wShowWindow = sw_hide
        kwargs["startupinfo"] = startupinfo

    return kwargs


class ModuleLoadError(RuntimeError):
    pass


class ModuleManager:
    """
    Apollo module manager.

    Accepted modules:
        modules/<module_id>/

    Candidate modules:
        pending_modules/<module_id>/

    Every accepted module is validated in a separate Python process before it is
    imported into Apollo. Candidate modules must pass validation before the UI
    will allow them to be accepted.
    """

    def __init__(
        self,
        modules_dir,
        state_path,
        context=None,
        pending_dir=None,
        validator_path=None,
    ):
        self.modules_dir = Path(modules_dir).resolve()
        self.state_path = Path(state_path).resolve()
        self.context = context or {}
        self.base_dir = Path(self.context.get("base_dir", self.modules_dir.parent)).resolve()

        self.pending_dir = Path(
            pending_dir or (self.modules_dir.parent / "pending_modules")
        ).resolve()

        self.validator_path = Path(
            validator_path or (self.modules_dir.parent / "module_validator.py")
        ).resolve()

        self.modules_dir.mkdir(parents=True, exist_ok=True)
        self.pending_dir.mkdir(parents=True, exist_ok=True)

        self._lock = threading.RLock()
        self.runtime = self.context.get("runtime")
        self._loaded = {}
        self._errors = {}
        self._pending = {}
        self._state = self._load_state()

    def _load_state(self):
        if not self.state_path.exists():
            return {"disabled": [], "ui_placement": {}, "ui_surfaces": {}}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {"disabled": [], "ui_placement": {}, "ui_surfaces": {}}
            data.setdefault("disabled", [])
            data.setdefault("ui_placement", {})
            data.setdefault("ui_surfaces", {})
            return data
        except Exception:
            return {"disabled": [], "ui_placement": {}, "ui_surfaces": {}}

    def _save_state(self):
        # Atomic replace so a crash/power loss cannot leave half-written UI/module state.
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temp_path.write_text(
            json.dumps(self._state, indent=2),
            encoding="utf-8"
        )
        temp_path.replace(self.state_path)

    def is_enabled(self, module_id):
        return module_id not in set(self._state.get("disabled", []))

    def set_enabled(self, module_id, enabled):
        disabled = set(self._state.get("disabled", []))
        if enabled:
            disabled.discard(module_id)
        else:
            disabled.add(module_id)
        self._state["disabled"] = sorted(disabled)
        self._save_state()
        self.reload()

    def get_ui_surfaces(self, module_id):
        """Return additive UI surfaces for future Apollo OS routing.

        Current accepted surfaces are `apps` and `sidebar`. Hub/Home pinning is
        intentionally stored by ApolloShell because it is a user layout choice,
        not a module installation property.
        """
        surfaces_state = self._state.setdefault("ui_surfaces", {})
        raw = surfaces_state.get(module_id)
        if isinstance(raw, list):
            cleaned = []
            for value in raw:
                value = str(value).lower().strip()
                if value in {"apps", "sidebar"} and value not in cleaned:
                    cleaned.append(value)
            return cleaned

        # One-time behavioural migration from the legacy mutually-exclusive field.
        placements = self._state.setdefault("ui_placement", {})
        if module_id in placements:
            legacy = str(placements[module_id]).lower().strip()
            if legacy in {"apps", "sidebar"}:
                return [legacy]
            if legacy == "none":
                return []

        record = self._loaded.get(module_id)
        manifest = record.get("manifest", {}) if record else {}
        ui = manifest.get("ui", {}) if isinstance(manifest, dict) else {}
        default = str(ui.get("default_placement", "apps")).lower().strip()
        if default in {"apps", "sidebar"}:
            return [default]
        return []

    def activate_certified_pending(
        self,
        module_id,
        approved=False,
        replace_existing=False,
    ):
        """Validate and immediately activate a pending module after approval.

        Certification = isolated validator PASS.
        Activation still requires an explicit approval signal from the caller.

        For a new module this installs and loads it immediately.
        For an upgrade, replace_existing=True performs a backup -> swap -> reload
        transaction and restores the previous module if the new version fails to load.
        """
        with self._lock:
            module_id = str(module_id or "").strip()
            if not VALID_ID.match(module_id):
                raise ValueError("Invalid module id.")

            if not bool(approved):
                return {
                    "ok": False,
                    "module_id": module_id,
                    "stage": "approval",
                    "error": "Certified activation requires explicit approval.",
                }

            validation = self.validate_pending(module_id)
            if not validation.get("ok"):
                return {
                    "ok": False,
                    "module_id": module_id,
                    "stage": "validation",
                    "validation": validation,
                    "error": validation.get("error", "Validation failed."),
                }

            installed = (self.modules_dir / module_id).resolve()

            if not installed.exists():
                accepted = self.accept_pending(module_id)
                return {
                    "ok": True,
                    "module_id": module_id,
                    "stage": "activated",
                    "upgrade": False,
                    "validation": validation,
                    "loaded": bool(
                        accepted
                        and accepted.get("instance") is not None
                    ),
                    "record": accepted,
                }

            if not replace_existing:
                return {
                    "ok": False,
                    "module_id": module_id,
                    "stage": "existing_module",
                    "error": (
                        "An installed module with this id already exists. "
                        "Set replace_existing=True for an approved upgrade."
                    ),
                    "validation": validation,
                }

            self.refresh_pending()
            pending = self._pending.get(module_id)
            if not pending:
                return {
                    "ok": False,
                    "module_id": module_id,
                    "stage": "pending",
                    "error": "Pending candidate disappeared before activation.",
                }

            candidate = Path(pending["folder"]).resolve()
            backup_root = self.base_dir / "storage" / "backups" / "module_upgrades"
            backup_root.mkdir(parents=True, exist_ok=True)
            backup = backup_root / f"{module_id}.previous"

            if backup.exists():
                shutil.rmtree(backup)

            self._unload_record(module_id)

            try:
                shutil.copytree(installed, backup)
                shutil.rmtree(installed)
                shutil.move(str(candidate), str(installed))

                self.reload()
                record = self._loaded.get(module_id)

                if (
                    record is None
                    or not record.get("enabled")
                    or record.get("instance") is None
                ):
                    raise ModuleLoadError(
                        "Upgraded module did not become live after reload."
                    )

                if backup.exists():
                    shutil.rmtree(backup)

                self.refresh_pending()
                return {
                    "ok": True,
                    "module_id": module_id,
                    "stage": "activated",
                    "upgrade": True,
                    "validation": validation,
                    "loaded": True,
                    "record": record,
                }

            except Exception as exc:
                try:
                    if installed.exists():
                        shutil.rmtree(installed)
                    if backup.exists():
                        shutil.copytree(backup, installed)
                    self.reload()
                finally:
                    if backup.exists():
                        shutil.rmtree(backup, ignore_errors=True)

                return {
                    "ok": False,
                    "module_id": module_id,
                    "stage": "rollback",
                    "upgrade": True,
                    "validation": validation,
                    "error": f"{type(exc).__name__}: {exc}",
                    "restored_previous": (
                        self._loaded.get(module_id, {}).get("instance")
                        is not None
                    ),
                }

    def set_ui_surfaces(self, module_id, surfaces):
        record = self._loaded.get(module_id)
        if record is None:
            raise KeyError(f"Module '{module_id}' is not installed.")
        manifest = record.get("manifest", {})
        ui = manifest.get("ui", {}) if isinstance(manifest, dict) else {}
        if not isinstance(ui, dict) or not bool(ui.get("enabled")):
            raise RuntimeError(f"Module '{module_id}' does not declare a UI page.")
        if not isinstance(surfaces, (list, tuple, set)):
            raise TypeError("surfaces must be a list, tuple, or set")
        cleaned = []
        for value in surfaces:
            value = str(value).lower().strip()
            if value not in {"apps", "sidebar"}:
                raise ValueError("UI surfaces may only contain apps and sidebar.")
            if value not in cleaned:
                cleaned.append(value)
        self._state.setdefault("ui_surfaces", {})[module_id] = cleaned
        # Keep the legacy field coherent for older code/plugins.
        legacy = "sidebar" if "sidebar" in cleaned else ("apps" if "apps" in cleaned else "none")
        self._state.setdefault("ui_placement", {})[module_id] = legacy
        self._save_state()

    def get_ui_placement(self, module_id):
        """Compatibility view of additive UI surfaces: sidebar > apps > none."""
        surfaces = self.get_ui_surfaces(module_id)
        if "sidebar" in surfaces:
            return "sidebar"
        if "apps" in surfaces:
            return "apps"
        return "none"

    def set_ui_placement(self, module_id, placement):
        """Legacy placement setter kept for the current Modules UI."""
        placement = str(placement or "").lower().strip()
        if placement not in {"none", "apps", "sidebar"}:
            raise ValueError("UI placement must be none, apps, or sidebar.")
        surfaces = [] if placement == "none" else [placement]
        self.set_ui_surfaces(module_id, surfaces)

    def module_has_ui(self, module_id):
        record = self._loaded.get(module_id)
        if not record:
            return False

        manifest = record.get("manifest", {})
        ui = manifest.get("ui", {}) if isinstance(manifest, dict) else {}
        instance = record.get("instance")

        # A manifest can request UI support, but Apollo can only actually render
        # the module if its live instance implements build_ui().
        return bool(
            isinstance(ui, dict)
            and bool(ui.get("enabled"))
            and instance is not None
            and hasattr(instance, "build_ui")
        )

    def ui_modules(self):
        output = []

        for module_id, record in sorted(self._loaded.items()):
            if not record.get("enabled"):
                continue
            if record.get("instance") is None:
                continue
            if not self.module_has_ui(module_id):
                continue

            manifest = record.get("manifest", {})
            ui = manifest.get("ui", {})
            if not isinstance(ui, dict):
                ui = {}

            output.append({
                "id": module_id,
                "name": manifest.get("name", module_id),
                "description": manifest.get("description", ""),
                "title": ui.get("title", manifest.get("name", module_id)),
                "placement": self.get_ui_placement(module_id),
                "instance": record.get("instance"),
                "manifest": manifest,
            })

        return output

    def _read_manifest(self, folder):
        manifest_path = folder / "manifest.json"
        if not manifest_path.exists():
            raise ModuleLoadError("Missing manifest.json")

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ModuleLoadError(f"Invalid manifest.json: {exc}") from exc

        module_id = str(manifest.get("id", folder.name)).strip()
        if not VALID_ID.match(module_id):
            raise ModuleLoadError(
                f"Invalid module id '{module_id}'. Use letters, numbers, _ or -."
            )

        return module_id, manifest

    def validate_folder(self, folder, timeout=10):
        """
        Validate in a completely separate Python process.

        This catches:
          - bad JSON manifest
          - invalid IDs
          - syntax errors
          - import errors
          - missing Module class
          - invalid tool definitions
          - missing run()
          - failing optional self_test()
          - validator timeout
        """
        folder = Path(folder).resolve()

        try:
            module_id, manifest = self._read_manifest(folder)
        except Exception as exc:
            return {
                "ok": False,
                "id": folder.name,
                "error": f"{type(exc).__name__}: {exc}",
            }

        if not self.validator_path.exists():
            return {
                "ok": False,
                "id": module_id,
                "error": f"Missing validator: {self.validator_path}",
            }

        env = dict(**__import__("os").environ)
        env["APOLLO_BASE_DIR"] = str(self.base_dir)

        try:
            proc = subprocess.run(
                [sys.executable, str(self.validator_path), str(folder)],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                **_hidden_subprocess_kwargs(),
            )
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "id": module_id,
                "error": f"Validation timed out after {timeout} seconds.",
            }
        except Exception as exc:
            return {
                "ok": False,
                "id": module_id,
                "error": f"Could not run validator: {type(exc).__name__}: {exc}",
            }

        lines = [x.strip() for x in (proc.stdout or "").splitlines() if x.strip()]
        payload = None
        if lines:
            try:
                payload = json.loads(lines[-1])
            except Exception:
                payload = None

        if proc.returncode != 0 or not payload or not payload.get("ok"):
            if payload:
                error = payload.get("error", "Validation failed.")
                details = payload.get("details", "")
                if details:
                    error += "\n" + details
            else:
                error = (
                    (proc.stderr or proc.stdout or "Validation failed.")
                    .strip()
                )
            return {
                "ok": False,
                "id": module_id,
                "name": manifest.get("name", module_id),
                "error": error,
            }

        payload["manifest"] = manifest
        return payload

    def _cleanup_module_state(self, module_id, keep_ui_placement=False):
        """Remove stale persistent state for a module."""
        disabled = set(self._state.get("disabled", []))
        disabled.discard(module_id)
        self._state["disabled"] = sorted(disabled)

        if not keep_ui_placement:
            placements = self._state.setdefault("ui_placement", {})
            placements.pop(module_id, None)

        self._save_state()

    def _unload_record(self, module_id):
        """
        Best-effort unload of one live module.

        close() is called when provided so SQLite handles, files, sockets, etc. can
        be released before Windows tries to move/delete the module folder.
        """
        record = self._loaded.get(module_id)
        if record is None:
            return

        instance = record.get("instance")
        if instance is not None and hasattr(instance, "close"):
            try:
                instance.close()
            except Exception:
                pass

        import_name = record.get("import_name")
        if import_name:
            sys.modules.pop(import_name, None)

        record["instance"] = None
        record["import_name"] = None
        record["tools"] = []

    def move_to_pending(self, module_id):
        """
        Move an installed/accepted module folder back to pending_modules.

        This is a development operation: Apollo unloads the module first, moves
        the complete folder, clears disabled state so it can later be reaccepted,
        preserves the user's UI placement preference, and validates the moved
        candidate in pending.
        """
        with self._lock:
            module_id = str(module_id or "").strip()
            if not VALID_ID.match(module_id):
                raise ValueError("Invalid module id.")

            src = (self.modules_dir / module_id).resolve()
            dest = (self.pending_dir / module_id).resolve()

            if self.modules_dir not in src.parents:
                raise ModuleLoadError("Source escaped modules directory.")
            if self.pending_dir not in dest.parents:
                raise ModuleLoadError("Destination escaped pending_modules directory.")
            if not src.exists() or not src.is_dir():
                raise FileNotFoundError(
                    f"Installed module folder '{module_id}' was not found."
                )
            if dest.exists():
                raise FileExistsError(
                    f"A pending module named '{module_id}' already exists. "
                    "Remove or rename that pending candidate first."
                )

            self._unload_record(module_id)

            try:
                shutil.move(str(src), str(dest))
            except Exception:
                # Rescan whatever state is left after a failed filesystem move.
                self.reload()
                raise

            # A previously-disabled state would prevent accept_pending() from
            # loading an instance. Clear it; keep UI placement so reaccepting the
            # module restores where the user wanted its page.
            self._cleanup_module_state(
                module_id,
                keep_ui_placement=True,
            )

            self.reload()

            result = self.validate_pending(module_id)
            return {
                "moved": True,
                "module_id": module_id,
                "folder": str(dest),
                "validation": result,
            }

    def remove_installed(self, module_id):
        """Permanently delete an installed module folder after the UI confirms."""
        with self._lock:
            module_id = str(module_id or "").strip()
            if not VALID_ID.match(module_id):
                raise ValueError("Invalid module id.")

            folder = (self.modules_dir / module_id).resolve()
            if self.modules_dir not in folder.parents:
                raise ModuleLoadError("Module path escaped modules directory.")
            if not folder.exists() or not folder.is_dir():
                raise FileNotFoundError(
                    f"Installed module folder '{module_id}' was not found."
                )

            self._unload_record(module_id)

            try:
                shutil.rmtree(folder)
            except Exception:
                self.reload()
                raise

            self._cleanup_module_state(
                module_id,
                keep_ui_placement=False,
            )
            self.reload()

            return {
                "removed": True,
                "module_id": module_id,
                "folder": str(folder),
            }

    def remove_pending(self, module_id):
        """Permanently delete a pending candidate folder."""
        with self._lock:
            self.refresh_pending()

            record = self._pending.get(module_id)
            if record is None:
                raise KeyError(
                    f"Pending module '{module_id}' was not found."
                )

            folder = Path(record["folder"]).resolve()
            if self.pending_dir not in folder.parents:
                raise ModuleLoadError(
                    "Pending module path escaped pending_modules directory."
                )

            if folder.exists():
                shutil.rmtree(folder)

            self._pending.pop(module_id, None)
            self.refresh_pending()

            return {
                "removed": True,
                "module_id": module_id,
                "folder": str(folder),
            }

    def _fast_validate_accepted(self, folder):
        """Fast startup check for already-accepted modules.

        Pending modules still receive the full isolated validator + tests before
        acceptance. Accepted modules are syntax-checked here and then imported by
        _load_module(). This avoids launching dozens of nested validator/test
        subprocesses on every Apollo startup while still catching edited/broken
        Python before import.
        """
        folder = Path(folder).resolve()
        try:
            module_id, manifest = self._read_manifest(folder)
            compiled = []
            for path in sorted(folder.glob("*.py")):
                source = path.read_text(encoding="utf-8")
                compile(source, str(path), "exec")
                compiled.append(path.name)
            return {
                "ok": True,
                "id": module_id,
                "name": manifest.get("name", module_id),
                "compiled_files": compiled,
                "mode": "accepted_fast_startup_check",
            }
        except Exception as exc:
            return {
                "ok": False,
                "id": folder.name,
                "error": f"{type(exc).__name__}: {exc}",
                "mode": "accepted_fast_startup_check",
            }

    def reload(self):
        with self._lock:
            for module_id in list(self._loaded):
                self._unload_record(module_id)

            self._loaded = {}
            self._errors = {}

            # Accepted modules are STILL revalidated before loading.
            for folder in sorted(self.modules_dir.iterdir()):
                if not folder.is_dir() or folder.name.startswith("_"):
                    continue

                try:
                    module_id, manifest = self._read_manifest(folder)
                    # Full subprocess validation is reserved for pending/accept.
                    # Re-running tests for every installed module on every startup
                    # caused long stalls once Apollo grew into an OS-style system.
                    validation = self._fast_validate_accepted(folder)

                    if not validation.get("ok"):
                        raise ModuleLoadError(
                            "Pre-load validation failed:\n"
                            + validation.get("error", "Unknown validation error")
                        )

                    record = {
                        "id": module_id,
                        "folder": folder,
                        "manifest": manifest,
                        "enabled": (
                            self.is_enabled(module_id)
                            and not (
                                self.runtime is not None
                                and hasattr(self.runtime, "is_module_quarantined")
                                and self.runtime.is_module_quarantined(module_id)
                                and module_id not in {
                                    "core_services", "self_awareness", "memory_bank",
                                    "module_factory", "file_builder", "system_info",
                                    "text_to_speech", "file_manager",
                                }
                            )
                            and (
                                not bool(self.context.get("safe_mode", False))
                                or module_id in {
                                    "core_services", "self_awareness", "memory_bank",
                                    "module_factory", "file_builder", "system_info",
                                    "text_to_speech", "file_manager",
                                }
                            )
                        ),
                        "instance": None,
                        "import_name": None,
                        "tools": [],
                        "validation": validation,
                    }

                    if record["enabled"]:
                        self._load_module(record)

                    self._loaded[module_id] = record

                    if self.runtime is not None and record.get("instance") is not None:
                        try:
                            self.runtime.clear_module_failure(module_id)
                        except Exception:
                            pass

                except Exception as exc:
                    if self.runtime is not None:
                        try:
                            self.runtime.record_module_failure(folder.name, f"{type(exc).__name__}: {exc}")
                        except Exception:
                            pass
                    self._errors[folder.name] = (
                        f"{type(exc).__name__}: {exc}\n"
                        + traceback.format_exc(limit=4)
                    )

            self.refresh_pending()
            if self.runtime is not None:
                try:
                    self.runtime.refresh_capabilities(self)
                except Exception:
                    pass
            return self.list_modules()

    def refresh_pending(self):
        # Preserve the last validation result while rescanning the folder.
        # Without this, the UI would forget a PASS immediately after refresh.
        previous = dict(self._pending)
        pending = {}
        for folder in sorted(self.pending_dir.iterdir()):
            if not folder.is_dir() or folder.name.startswith("_"):
                continue

            try:
                module_id, manifest = self._read_manifest(folder)
                pending[module_id] = {
                    "id": module_id,
                    "name": manifest.get("name", module_id),
                    "version": manifest.get("version", "0.0"),
                    "description": manifest.get("description", ""),
                    "folder": str(folder),
                    "validation": (
                        previous.get(module_id, {}).get("validation")
                    ),
                }
            except Exception as exc:
                pending[folder.name] = {
                    "id": folder.name,
                    "name": folder.name,
                    "version": "?",
                    "description": "Invalid pending module",
                    "folder": str(folder),
                    "validation": {
                        "ok": False,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                }

        self._pending = pending
        return self.list_pending()

    def validate_pending(self, module_id):
        self.refresh_pending()
        record = self._pending.get(module_id)
        if not record:
            raise KeyError(f"Pending module '{module_id}' was not found.")

        result = self.validate_folder(record["folder"])
        record["validation"] = result
        self._pending[module_id] = record
        return result

    def accept_pending(self, module_id):
        """
        Validate again immediately before acceptance, then move into modules/.
        This method never accepts a failed module.
        """
        result = self.validate_pending(module_id)
        if not result.get("ok"):
            raise ModuleLoadError(
                "Module failed validation and was NOT accepted:\n"
                + result.get("error", "Unknown validation error")
            )

        record = self._pending[module_id]
        src = Path(record["folder"]).resolve()
        dest = (self.modules_dir / module_id).resolve()

        if self.modules_dir not in dest.parents:
            raise ModuleLoadError("Destination escaped modules directory.")
        if dest.exists():
            raise ModuleLoadError(
                f"An accepted module named '{module_id}' already exists."
            )

        shutil.move(str(src), str(dest))
        self.reload()

        accepted = self._loaded.get(module_id)
        if accepted is None or accepted.get("instance") is None:
            # Should be rare because we validated first. Move back if load failed.
            fallback = self.pending_dir / module_id
            if dest.exists() and not fallback.exists():
                shutil.move(str(dest), str(fallback))
            self.reload()
            raise ModuleLoadError(
                "Module passed validation but failed during final Apollo load. "
                "It was returned to pending_modules."
            )

        return accepted

    def _load_module(self, record):
        manifest = record["manifest"]
        folder = record["folder"]
        entrypoint = manifest.get("entrypoint", "module.py")
        class_name = manifest.get("class", "Module")
        module_file = (folder / entrypoint).resolve()

        if folder.resolve() not in module_file.parents:
            raise ModuleLoadError("Entrypoint escapes the module directory.")
        if not module_file.exists():
            raise ModuleLoadError(f"Missing entrypoint: {entrypoint}")

        import_name = f"apollo_ext_{record['id']}"
        spec = importlib.util.spec_from_file_location(import_name, module_file)
        if spec is None or spec.loader is None:
            raise ModuleLoadError("Could not create Python import spec.")

        py_module = importlib.util.module_from_spec(spec)
        sys.modules[import_name] = py_module
        spec.loader.exec_module(py_module)

        cls = getattr(py_module, class_name, None)
        if cls is None:
            raise ModuleLoadError(
                f"Entrypoint does not define class '{class_name}'."
            )

        try:
            instance = cls(dict(self.context))
        except TypeError:
            instance = cls()

        tools = []
        if hasattr(instance, "tools"):
            tools = instance.tools() or []
        elif manifest.get("tools"):
            tools = manifest.get("tools", [])

        if not isinstance(tools, list):
            raise ModuleLoadError("Module tools() must return a list.")

        cleaned = []
        for tool in tools:
            if not isinstance(tool, dict):
                raise ModuleLoadError("Tool definitions must be objects.")
            name = str(tool.get("name", "")).strip()
            if not VALID_ID.match(name):
                raise ModuleLoadError(
                    f"Invalid tool name '{name}' in module {record['id']}."
                )
            cleaned.append(tool)

        if cleaned and not hasattr(instance, "run"):
            raise ModuleLoadError("Module exposes tools but has no run() method.")

        record["instance"] = instance
        record["import_name"] = import_name
        record["tools"] = cleaned

    def list_modules(self):
        with self._lock:
            result = []

            for module_id, record in sorted(self._loaded.items()):
                manifest = record["manifest"]
                result.append({
                    "id": module_id,
                    "name": manifest.get("name", module_id),
                    "version": manifest.get("version", "0.0"),
                    "description": manifest.get("description", ""),
                    "enabled": record["enabled"],
                    "loaded": record["instance"] is not None,
                    "tool_count": len(record["tools"]),
                    "folder": str(record["folder"]),
                    "validated": bool(record.get("validation", {}).get("ok")),
                    "has_ui": self.module_has_ui(module_id),
                    "ui_placement": self.get_ui_placement(module_id),
                    "ui_surfaces": self.get_ui_surfaces(module_id),
                })

            for folder_name, error in sorted(self._errors.items()):
                result.append({
                    "id": folder_name,
                    "name": folder_name,
                    "version": "?",
                    "description": error.splitlines()[0] if error else "Load error",
                    "enabled": False,
                    "loaded": False,
                    "tool_count": 0,
                    "folder": str(self.modules_dir / folder_name),
                    "error": error,
                    "validated": False,
                })

            return result

    def list_pending(self):
        with self._lock:
            return [dict(x) for _, x in sorted(self._pending.items())]

    def get_module(self, module_id):
        with self._lock:
            return self._loaded.get(module_id)

    def get_pending(self, module_id):
        with self._lock:
            return self._pending.get(module_id)

    def errors(self):
        with self._lock:
            return dict(self._errors)

    def tool_catalog_text(self):
        lines = []
        with self._lock:
            for module_id, record in sorted(self._loaded.items()):
                if not record["enabled"] or record["instance"] is None:
                    continue
                for tool in record["tools"]:
                    lines.append(
                        f"- {module_id}.{tool['name']}: "
                        + str(tool.get("description", ""))
                    )
        return "\n".join(lines)

    def ollama_tools(self, raw=False):
        tools = []
        with self._lock:
            for module_id, record in sorted(self._loaded.items()):
                if not record["enabled"] or record["instance"] is None:
                    continue

                for tool in record["tools"]:
                    fn_name = f"{module_id}__{tool['name']}"
                    description = (
                        f"Apollo module "
                        f"{record['manifest'].get('name', module_id)}. "
                        + str(tool.get("description", ""))
                    ).strip()
                    if self.runtime is not None and not raw:
                        try:
                            risk = self.runtime.risk_for(fn_name)
                            decision = self.runtime.get_permission(fn_name)
                            description += f" [risk={risk}; permission={decision}]"
                        except Exception:
                            pass
                    tools.append({
                        "type": "function",
                        "function": {
                            "name": fn_name,
                            "description": description,
                            "parameters": tool.get(
                                "parameters",
                                {"type": "object", "properties": {}}
                            ),
                        },
                    })

        return tools

    def execute_tool(self, function_name, arguments=None):
        if "__" not in function_name:
            raise KeyError(f"Unknown module tool: {function_name}")
        if self.runtime is not None:
            return self.runtime.execute_tool(
                self, function_name, arguments or {}, actor="apollo"
            )
        return self._execute_tool_direct(function_name, arguments or {})

    def _execute_tool_direct(self, function_name, arguments=None):
        if "__" not in function_name:
            raise KeyError(f"Unknown module tool: {function_name}")
        module_id, action = function_name.split("__", 1)
        return self._execute_direct(module_id, action, arguments or {})

    def execute(self, module_id, action, arguments=None):
        function_name = f"{module_id}__{action}"
        if self.runtime is not None:
            return self.runtime.execute_tool(
                self, function_name, arguments or {}, actor="apollo"
            )
        return self._execute_direct(module_id, action, arguments or {})

    def _execute_direct(self, module_id, action, arguments=None):
        arguments = arguments or {}
        if not isinstance(arguments, dict):
            raise TypeError("Module arguments must be a JSON object/dict.")

        with self._lock:
            record = self._loaded.get(module_id)
            if record is None:
                raise KeyError(f"Module '{module_id}' is not installed.")
            if not record["enabled"]:
                raise RuntimeError(f"Module '{module_id}' is disabled.")

            instance = record["instance"]
            if instance is None:
                raise RuntimeError(f"Module '{module_id}' did not load.")

            valid_actions = {x.get("name") for x in record["tools"]}
            if action not in valid_actions:
                raise KeyError(
                    f"Module '{module_id}' has no exposed action '{action}'."
                )

            return instance.run(action, dict(arguments))
