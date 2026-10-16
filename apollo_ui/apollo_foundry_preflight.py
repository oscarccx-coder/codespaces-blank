"""Read-only Foundry setup diagnostics. No installers, downloads or code execution."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def _command(argv, timeout=10):
    try:
        result = subprocess.run(
            argv, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, timeout=timeout, check=False,
        )
        return result.returncode == 0, (result.stdout + result.stderr)[:2000]
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, type(exc).__name__


def inspect_foundry(root):
    """Return actionable statuses, never mutate user configuration."""
    root = Path(root).resolve()
    checks = []
    def add(name, ok, detail, required=True):
        checks.append({
            "name": name, "ok": bool(ok), "required": bool(required),
            "detail": str(detail)[:300],
        })
    add("Python", sys.version_info >= (3, 11),
        f"Current Python {sys.version.split()[0]}; 3.11+ recommended.")
    add("PySide6", importlib.util.find_spec("PySide6") is not None,
        "Apollo desktop UI requires PySide6. Run Setup/01_INSTALL_APOLLO.bat if missing.")
    try:
        from apollo_project_workers import model_from_config
        model = model_from_config(root)
    except (ValueError, OSError) as exc:
        model = "qwen2.5-coder:7b"
        add("Model configuration", False, str(exc))
    else:
        add("Model configuration", True, model)
    ollama = shutil.which("ollama")
    if not ollama:
        add("Ollama", False, "Install Ollama, start it and pull the configured coding model.")
    else:
        ok, output = _command([ollama, "list"], timeout=12)
        names = [line.split()[0] for line in output.splitlines()[1:] if line.split()]
        add("Ollama coding model", ok and model in names,
            "Model " + model + (" is installed." if ok and model in names else
                                " not found. Run: ollama pull " + model))
    try:
        from apollo_foundry_sandbox import availability
        docker = availability("unit")
        add("Docker Foundry image", docker["ok"], docker["reason"] +
            ("; Setup/09_SETUP_FOUNDRY_SANDBOX.bat" if not docker["ok"] else ""))
    except (ValueError, OSError) as exc:
        add("Docker Foundry image", False, str(exc))
    wsl = shutil.which("wsl")
    if os.name == "nt" and wsl:
        ok, _ = _command([wsl, "--status"], timeout=12)
        add("WSL 2", ok, "WSL status checked. Docker Desktop uses Linux containers.", required=False)
    elif os.name == "nt":
        add("WSL 2", False, "Install WSL 2 and enable hardware virtualization.", required=False)
    for name in ("numpy", "sympy", "matplotlib"):
        add("Local preview " + name, importlib.util.find_spec(name) is not None,
            "Optional for trusted local preview: Setup/16_INSTALL_FOUNDRY_SCIENCE.bat. "
            "Pinned versions are already in Docker.",
            required=False)
    system_drive = os.environ.get("SystemDrive")
    if system_drive and os.name == "nt":
        try:
            free = shutil.disk_usage(system_drive + "\\").free
            add("Windows system drive space", free >= 15 * 1024**3,
                f"{free / 1024**3:.1f} GiB free. Docker Desktop/WSL images often use C:.",
                required=False)
        except OSError:
            pass
    return {
        "ready": all(item["ok"] for item in checks if item["required"]),
        "checks": checks,
        "note": "Preflight is read-only. Docker must be installed and configured by the owner.",
    }


def main():
    root = Path(__file__).resolve().parent
    result = inspect_foundry(root)
    print("APOLLO FOUNDRY PREREQUISITES")
    print("=" * 52)
    for item in result["checks"]:
        marker = "OK" if item["ok"] else ("MISSING" if item["required"] else "OPTIONAL")
        print(f"[{marker}] {item['name']}: {item['detail']}")
    print("\n" + ("READY for a Foundry session" if result["ready"] else
                  "Prerequisites need attention before continuous Docker testing."))
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
