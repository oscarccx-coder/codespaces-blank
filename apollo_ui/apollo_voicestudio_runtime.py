"""Owner-operated VoiceStudio backend supervisor.

Only launches an explicitly selected prepared local VoiceStudio checkout.
Apollo never installs VoiceStudio, downloads model weights, or executes code
from an unreviewed remote automatically. VoiceStudio stays in its own venv.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import threading

_OWNER_LOCK = threading.RLock()
_OWNED = None


def _validate_checkout(checkout) -> Path:
    folder = Path(checkout).expanduser().resolve()
    if not folder.is_dir():
        raise FileNotFoundError("Choose the folder containing VoiceStudio's package.json.")
    package = folder / "package.json"
    entry = folder / "scripts" / "dev-backend.mjs"
    if not package.is_file() or not entry.is_file() or not (folder / "backend" / "main.py").is_file():
        raise ValueError("Folder is not a VoiceStudio Git/source checkout.")
    data = json.loads(package.read_text(encoding="utf-8"))
    if data.get("name") != "omnivoice-studio-monorepo" or data.get("scripts", {}).get("dev:api") != "bun scripts/dev-backend.mjs":
        raise ValueError("VoiceStudio source layout/scripts differ from the reviewed upstream version.")
    return folder


def prepare_backend(checkout, logs_dir):
    """Explicit owner-initiated install of VoiceStudio's source dependencies.

    Runs external upstream setup scripts in the chosen checkout, never in
    Apollo's own Python venv. This action must not be model-callable.
    """
    folder = _validate_checkout(checkout)
    bun = shutil.which("bun")
    uv = shutil.which("uv")
    if not bun or not uv:
        raise RuntimeError("Install Bun and uv before preparing VoiceStudio.")
    logs = Path(logs_dir).resolve()
    logs.mkdir(parents=True, exist_ok=True)
    logfile = logs / "voicestudio-setup.log"
    with logfile.open("a", encoding="utf-8") as output:
        for command in ([bun, "install", "--frozen-lockfile"], [bun, "run", "setup:api"]):
            output.write("Running: " + " ".join(command[1:]) + "\n")
            output.flush()
            completed = subprocess.run(command, cwd=str(folder), stdin=subprocess.DEVNULL,
                                       stdout=output, stderr=subprocess.STDOUT, check=False,
                                       timeout=2400)
            if completed.returncode != 0:
                raise RuntimeError(f"VoiceStudio setup failed (exit {completed.returncode}). Check {logfile}")
    return {"ok": True, "prepared": True, "checkout": str(folder),
            "log": str(logfile), "notice": "Choose and install voice models in VoiceStudio before use."}


def backend_status():
    with _OWNER_LOCK:
        proc = _OWNED
        return {"managed": proc is not None,
                "running": proc is not None and proc.poll() is None,
                "pid": proc.pid if proc is not None else None,
                "exit_code": proc.poll() if proc is not None else None}


def start_backend(checkout, logs_dir):
    """Starts VoiceStudio only on an explicit owner click, never as an LLM tool."""
    global _OWNED
    folder = _validate_checkout(checkout)
    bun = shutil.which("bun")
    uv = shutil.which("uv")
    if not bun or not uv:
        raise RuntimeError("Bun and uv must be installed to run VoiceStudio from Git source.")
    python = folder / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file():
        raise RuntimeError("VoiceStudio's Python environment is not installed; run 'bun run setup:api' in its source folder with owner approval.")
    with _OWNER_LOCK:
        if _OWNED is not None and _OWNED.poll() is None:
            return {"ok": True, **backend_status(), "reason": "Already managed by Apollo"}
        logs = Path(logs_dir).resolve()
        logs.mkdir(parents=True, exist_ok=True)
        logfile = logs / "voicestudio-backend.log"
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
        kwargs = {"creationflags": flags} if os.name == "nt" else {"start_new_session": True}
        env = os.environ.copy()
        env["OMNIVOICE_BIND_HOST"] = "127.0.0.1"
        # A separately launched checkout uses its own data and Python runtime.
        with logfile.open("a", encoding="utf-8") as out:
            _OWNED = subprocess.Popen([bun, "run", "dev:api"], cwd=str(folder),
                                      stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                                      env=env, **kwargs)
        return {"ok": True, **backend_status(), "log": str(logfile),
                "notice": "VoiceStudio is launching. Use Test connection after it becomes ready."}


def stop_backend():
    """Only terminates the VoiceStudio process that Apollo itself launched."""
    global _OWNED
    with _OWNER_LOCK:
        proc = _OWNED
        _OWNED = None
    if proc is None or proc.poll() is not None:
        return {"ok": True, "stopped": False, "reason": "No Apollo-owned VoiceStudio process"}
    try:
        if os.name == "nt":
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        # A best-effort kill is scoped to Apollo's owned group.
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           capture_output=True, check=False, timeout=10)
        else:
            try: os.killpg(proc.pid, signal.SIGKILL)
            except OSError: pass
    return {"ok": True, "stopped": proc.poll() is not None}
