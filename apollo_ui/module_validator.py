import importlib.util
import json
import os
import re
import subprocess
import sys
import traceback
from pathlib import Path


VALID_ID = re.compile(r"^[a-zA-Z0-9_-]+$")


def _hidden_subprocess_kwargs():
    """Prevent tests.py from opening a separate console window on Windows."""
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


def fail(message, details=None):
    print(json.dumps({
        "ok": False,
        "error": str(message),
        "details": details or ""
    }, ensure_ascii=False))
    raise SystemExit(1)


def compile_python_files(folder):
    compiled = []
    for path in sorted(folder.glob("*.py")):
        try:
            source = path.read_text(encoding="utf-8")
            compile(source, str(path), "exec")
            compiled.append(path.name)
        except Exception as exc:
            fail(
                f"Python compile failed in {path.name}: "
                f"{type(exc).__name__}: {exc}"
            )
    return compiled


def run_external_tests(folder, env):
    tests_path = folder / "tests.py"
    if not tests_path.exists():
        return {
            "present": False,
            "passed": None,
            "output": "No tests.py supplied."
        }

    try:
        proc = subprocess.run(
            [sys.executable, str(tests_path)],
            cwd=str(folder),
            capture_output=True,
            text=True,
            timeout=12,
            env=env,
            **_hidden_subprocess_kwargs(),
        )
    except subprocess.TimeoutExpired:
        fail("tests.py timed out after 12 seconds.")
    except Exception as exc:
        fail(f"Could not run tests.py: {type(exc).__name__}: {exc}")

    output = "\n".join(
        x for x in [(proc.stdout or "").strip(), (proc.stderr or "").strip()]
        if x
    )

    if proc.returncode != 0:
        fail(
            f"tests.py failed with exit code {proc.returncode}.",
            output[-12000:]
        )

    return {
        "present": True,
        "passed": True,
        "output": output[-12000:] or "tests.py passed."
    }


def main():
    if len(sys.argv) != 2:
        fail("Usage: module_validator.py <module_folder>")

    folder = Path(sys.argv[1]).resolve()
    manifest_path = folder / "manifest.json"

    if not folder.is_dir():
        fail("Module folder does not exist.")
    if not manifest_path.exists():
        fail("Missing manifest.json")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"Invalid manifest.json: {exc}")

    module_id = str(manifest.get("id", folder.name)).strip()
    if not VALID_ID.match(module_id):
        fail("Invalid module id. Use only letters, numbers, _ and -.")

    entrypoint = str(manifest.get("entrypoint", "module.py"))
    class_name = str(manifest.get("class", "Module"))
    module_file = (folder / entrypoint).resolve()

    if folder not in module_file.parents:
        fail("Entrypoint escapes its module folder.")
    if not module_file.exists():
        fail(f"Missing entrypoint: {entrypoint}")

    compiled_files = compile_python_files(folder)

    import_name = f"apollo_validate_{module_id}"

    try:
        spec = importlib.util.spec_from_file_location(import_name, module_file)
        if spec is None or spec.loader is None:
            fail("Could not create module import spec.")

        py_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(py_module)

        cls = getattr(py_module, class_name, None)
        if cls is None:
            fail(f"Entrypoint does not define class '{class_name}'.")

        base_dir = os.environ.get("APOLLO_BASE_DIR", "")
        context = {
            "base_dir": base_dir,
            "validation": True,
        }

        try:
            instance = cls(context)
        except TypeError:
            instance = cls()

        tools = []
        if hasattr(instance, "tools"):
            tools = instance.tools() or []
        elif manifest.get("tools"):
            tools = manifest["tools"]

        if not isinstance(tools, list):
            fail("tools() must return a list.")

        seen = set()
        for tool in tools:
            if not isinstance(tool, dict):
                fail("Every tool definition must be a dict.")

            name = str(tool.get("name", "")).strip()
            if not VALID_ID.match(name):
                fail(f"Invalid tool name: {name!r}")
            if name in seen:
                fail(f"Duplicate tool name: {name}")
            seen.add(name)

            description = tool.get("description", "")
            if not isinstance(description, str):
                fail(f"Tool {name} description must be text.")

            params = tool.get(
                "parameters",
                {"type": "object", "properties": {}}
            )
            if not isinstance(params, dict):
                fail(f"Tool {name} parameters must be an object.")
            if params.get("type", "object") != "object":
                fail(f"Tool {name} parameters.type must be 'object'.")
            if not isinstance(params.get("properties", {}), dict):
                fail(f"Tool {name} parameters.properties must be an object.")

        if tools and not hasattr(instance, "run"):
            fail(
                "Module exposes tools but does not implement "
                "run(action, arguments)."
            )

        self_test_result = None
        if hasattr(instance, "self_test"):
            self_test_result = instance.self_test()
            if self_test_result is False:
                fail("self_test() returned False.")

        env = dict(os.environ)
        env["APOLLO_BASE_DIR"] = base_dir
        # Module tests run from their own folder; expose trusted Apollo core
        # helpers such as apollo_update and apollo_xtts_paths to that subprocess.
        core_root = str(Path(__file__).resolve().parent)
        env["PYTHONPATH"] = core_root + os.pathsep + env.get("PYTHONPATH", "")
        external_tests = run_external_tests(folder, env)

        print(json.dumps({
            "ok": True,
            "id": module_id,
            "name": manifest.get("name", module_id),
            "version": manifest.get("version", "0.0"),
            "tool_count": len(tools),
            "tools": [x.get("name") for x in tools],
            "compiled_files": compiled_files,
            "self_test": self_test_result,
            "external_tests": external_tests,
        }, ensure_ascii=False))

    except SystemExit:
        raise
    except Exception as exc:
        fail(
            f"Validation import/test failed: {type(exc).__name__}: {exc}",
            traceback.format_exc(limit=10)
        )


if __name__ == "__main__":
    main()
