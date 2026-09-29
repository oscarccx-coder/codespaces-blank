import json
import shutil
from datetime import datetime
from pathlib import Path


class ModuleRepairError(RuntimeError):
    pass


class ModuleRepairEngine:
    """
    Repairs ONLY pending Apollo modules.

    It never moves a module into modules/ and never modifies Apollo core source.
    A successful repair still requires the user to press Accept Valid Module.
    """

    ALLOWED_EDIT_FILES = {
        "manifest.json",
        "module.py",
        "tests.py",
        "README.md",
    }

    def __init__(self, ollama_client, module_manager, base_dir):
        self.client = ollama_client
        self.manager = module_manager
        self.base_dir = Path(base_dir).resolve()
        self.template_dir = self.base_dir / "modules" / "_template"

    def _template_contract(self):
        manifest = self.template_dir / "manifest.json"
        module = self.template_dir / "module.py"

        return {
            "manifest": (
                manifest.read_text(encoding="utf-8")
                if manifest.exists()
                else "{}"
            ),
            "module": (
                module.read_text(encoding="utf-8")
                if module.exists()
                else ""
            ),
        }

    def _safe_candidate_folder(self, folder):
        folder = Path(folder).resolve()
        pending = self.manager.pending_dir.resolve()

        if pending not in folder.parents:
            raise ModuleRepairError(
                "Repair engine may only modify pending_modules."
            )
        return folder

    def _read_candidate(self, folder):
        folder = self._safe_candidate_folder(folder)
        result = {}

        limits = {
            "manifest.json": 5000,
            "module.py": 15000,
            "tests.py": 7000,
            "README.md": 3000,
        }

        for name in self.ALLOWED_EDIT_FILES:
            path = folder / name
            if path.exists() and path.is_file():
                text = path.read_text(
                    encoding="utf-8",
                    errors="replace"
                )
                limit = limits.get(name, 5000)
                if len(text) > limit:
                    text = (
                        text[:limit]
                        + "\n\n# [Apollo repair input truncated here]"
                    )
                result[name] = text

        return result

    def _snapshot(self, folder, attempt):
        folder = self._safe_candidate_folder(folder)
        history = folder / ".repair_history"
        history.mkdir(exist_ok=True)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snap = history / f"attempt_{attempt:02d}_{stamp}"
        snap.mkdir(parents=True, exist_ok=True)

        for name in self.ALLOWED_EDIT_FILES:
            src = folder / name
            if src.exists() and src.is_file():
                shutil.copy2(src, snap / name)

        return snap

    @staticmethod
    def _extract_json_object(text):
        text = str(text or "").strip()

        # First try the entire response.
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

        # Strip common Markdown fences.
        if text.startswith("```"):
            lines = text.splitlines()
            if lines:
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            stripped = "\n".join(lines).strip()
            try:
                obj = json.loads(stripped)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                text = stripped

        # Robustly scan for any JSON object in the reply.
        decoder = json.JSONDecoder()
        for index, char in enumerate(text):
            if char != "{":
                continue
            try:
                obj, _ = decoder.raw_decode(text[index:])
            except Exception:
                continue
            if isinstance(obj, dict):
                return obj

        raise ModuleRepairError(
            "Ollama did not return a valid repair JSON object."
        )

    def _ask_for_repair(
        self,
        module_id,
        candidate,
        validation,
        attempt,
    ):
        contract = self._template_contract()

        system = """
You are Apollo's pending-module repair compiler.

Your job is NOT to chat with the user. Repair the pending Apollo module so it
conforms to Apollo's module API and passes validation.

HARD RULES:
- Preserve the intended feature whenever possible.
- The entrypoint class MUST normally be named Module.
- A usable Apollo tool module implements tools() and run(action, arguments).
- Add self_test() that actually checks safe internal behavior where practical.
- Add tests.py when practical. tests.py must be non-interactive and exit nonzero
  on failure.
- Prefer Python standard library solutions unless an external dependency is
  essential to the feature.
- Never run pip, installers, shell commands, network downloads, or destructive
  filesystem actions from self_test/tests.py.
- Never modify Apollo core files.
- You are repairing files inside one pending module only.
- Do not install or approve the module.
- Output EXACTLY ONE JSON OBJECT. No Markdown and no commentary.

OUTPUT FORMAT:
{
  "manifest": {complete manifest.json object},
  "module_py": "complete module.py source",
  "tests_py": "complete tests.py source or empty string",
  "readme_md": "optional README text or empty string",
  "reason": "short explanation of what you repaired"
}
""".strip()

        user = (
            f"MODULE ID / FOLDER: {module_id}\n"
            f"REPAIR ATTEMPT: {attempt}\n\n"
            "APOLLO MANIFEST TEMPLATE:\n"
            f"{contract['manifest']}\n\n"
            "APOLLO MODULE TEMPLATE:\n"
            f"{contract['module']}\n\n"
            "CURRENT CANDIDATE FILES:\n"
            f"{json.dumps(candidate, ensure_ascii=False, indent=2)}\n\n"
            "CURRENT VALIDATION RESULT:\n"
            f"{json.dumps(validation, ensure_ascii=False, indent=2)}\n\n"
            "Return the complete corrected files as the required JSON object."
        )

        response = self.client.chat_once([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])

        content = (
            response.get("message", {}).get("content", "")
            if isinstance(response, dict)
            else ""
        )

        return self._extract_json_object(content)

    def _write_repair(self, folder, payload):
        folder = self._safe_candidate_folder(folder)

        manifest = payload.get("manifest")
        module_py = payload.get("module_py")

        if not isinstance(manifest, dict):
            raise ModuleRepairError(
                "Repair payload is missing a manifest object."
            )
        if not isinstance(module_py, str) or not module_py.strip():
            raise ModuleRepairError(
                "Repair payload is missing complete module.py source."
            )

        manifest_text = json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2
        )

        if len(manifest_text.encode("utf-8")) > 100_000:
            raise ModuleRepairError("manifest.json repair is unreasonably large.")
        if len(module_py.encode("utf-8")) > 500_000:
            raise ModuleRepairError("module.py repair is unreasonably large.")

        (folder / "manifest.json").write_text(
            manifest_text + "\n",
            encoding="utf-8"
        )
        (folder / "module.py").write_text(
            module_py.rstrip() + "\n",
            encoding="utf-8"
        )

        tests_py = payload.get("tests_py", "")
        if tests_py is None:
            tests_py = ""
        if not isinstance(tests_py, str):
            raise ModuleRepairError("tests_py must be text.")

        tests_path = folder / "tests.py"
        if tests_py.strip():
            if len(tests_py.encode("utf-8")) > 300_000:
                raise ModuleRepairError("tests.py repair is unreasonably large.")
            tests_path.write_text(
                tests_py.rstrip() + "\n",
                encoding="utf-8"
            )
        elif tests_path.exists():
            tests_path.unlink()

        readme = payload.get("readme_md", "")
        if readme is None:
            readme = ""
        if not isinstance(readme, str):
            raise ModuleRepairError("readme_md must be text.")

        if readme.strip():
            if len(readme.encode("utf-8")) > 200_000:
                raise ModuleRepairError("README repair is unreasonably large.")
            (folder / "README.md").write_text(
                readme.rstrip() + "\n",
                encoding="utf-8"
            )

    def repair_pending(
        self,
        module_id,
        max_attempts=6,
        progress_callback=None,
    ):
        max_attempts = max(1, min(int(max_attempts), 10))

        self.manager.refresh_pending()
        record = self.manager.get_pending(module_id)

        if record is None:
            raise ModuleRepairError(
                f"Pending module '{module_id}' was not found."
            )

        folder = self._safe_candidate_folder(record["folder"])
        history = []

        def progress(message):
            history.append(message)
            if progress_callback:
                progress_callback(message)

        progress(f"Inspecting pending module: {module_id}")

        for attempt in range(0, max_attempts + 1):
            validation = self.manager.validate_folder(
                folder,
                timeout=15
            )

            if validation.get("ok"):
                self.manager.refresh_pending()
                current = self.manager.get_pending(module_id)
                if current is not None:
                    current["validation"] = validation
                progress(
                    "✓ Validation passed. Module remains pending for user approval."
                )
                return {
                    "ok": True,
                    "module_id": module_id,
                    "attempts": attempt,
                    "validation": validation,
                    "history": history,
                    "folder": str(folder),
                }

            if attempt >= max_attempts:
                self.manager.refresh_pending()
                current = self.manager.get_pending(module_id)
                if current is not None:
                    current["validation"] = validation
                progress(
                    f"✗ Repair stopped after {max_attempts} repair attempts."
                )
                return {
                    "ok": False,
                    "module_id": module_id,
                    "attempts": attempt,
                    "validation": validation,
                    "history": history,
                    "folder": str(folder),
                }

            error = validation.get("error", "Unknown validation error")
            progress(
                f"Attempt {attempt + 1}/{max_attempts}: validator failed: "
                f"{error.splitlines()[0]}"
            )

            candidate = self._read_candidate(folder)
            self._snapshot(folder, attempt + 1)

            repair_payload = self._ask_for_repair(
                module_id=module_id,
                candidate=candidate,
                validation=validation,
                attempt=attempt + 1,
            )

            reason = str(
                repair_payload.get("reason", "Apollo generated a repair.")
            )
            progress(f"Rewriting candidate files: {reason}")

            self._write_repair(folder, repair_payload)
            self.manager.refresh_pending()

        raise ModuleRepairError("Unexpected repair-loop termination.")
