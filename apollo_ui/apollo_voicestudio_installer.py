"""Guided, owner-approved VoiceStudio source-backend installer for Windows.

Uses an EXISTING user-selected checkout and VoiceStudio's own reviewed setup
scripts. It does not install into Apollo's Python environment, change models,
clone new source, alter remote URLs or run an automatic installer on startup.
Third-party scripts can download dependencies and execute code: owner consent
is required by the UI for every installation attempt.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading

from apollo_voicestudio_runtime import _validate_checkout, prepare_backend

_INSTALL_LOCK = threading.Lock()
_WINGET_PACKAGES = {"bun": "Oven-sh.Bun", "uv": "astral-sh.uv"}


def locate_tool(name: str) -> str:
    """Try PATH then documented per-user installation paths after WinGet."""
    installed = shutil.which(name)
    if installed:
        return installed
    if sys.platform != "win32":
        return ""
    home = Path.home()
    local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
    options = {
        "bun": [home / ".bun" / "bin" / "bun.exe",
                local / "Microsoft" / "WinGet" / "Links" / "bun.exe"],
        "uv": [home / ".local" / "bin" / "uv.exe",
               local / "Microsoft" / "WinGet" / "Links" / "uv.exe"],
    }
    for path in options.get(name, []):
        if path.is_file():
            return str(path)
    return ""


def diagnose(checkout: str | Path) -> dict:
    """No changes to PC; report exactly what is missing."""
    folder = _validate_checkout(checkout)
    bun = locate_tool("bun")
    uv = locate_tool("uv")
    py = folder / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    missing = [name for name, installed in (("bun", bun), ("uv", uv)) if not installed]
    return {"ok": True, "checkout": str(folder), "missing": missing,
            "bun": bool(bun), "uv": bool(uv), "backend_venv": py.is_file(),
            "prepared": bool(bun and uv and py.is_file()),
            "can_install_prerequisites": bool(sys.platform == "win32" and shutil.which("winget")),
            "advice": ("Ready to start" if bun and uv and py.is_file()
                       else "Install missing prerequisites, then prepare VoiceStudio's separate Python environment.")}


def install_missing_prerequisites(checkout, logs_dir, *, approved: bool = False) -> dict:
    """WinGet-only, fixed package IDs; no pipe-to-shell or surprise installs."""
    if not approved:
        raise PermissionError("Installing third-party tools requires explicit approval.")
    if sys.platform != "win32":
        raise RuntimeError("Automatic prerequisite installation is Windows-only.")
    check = diagnose(checkout)
    missing = check["missing"]
    if not missing:
        return {"ok": True, "installed": [], "notice": "Bun and uv already detected."}
    winget = shutil.which("winget")
    if not winget:
        raise RuntimeError("Windows Package Manager is missing. Install Microsoft App Installer first.")
    logs = Path(logs_dir).resolve()
    logs.mkdir(parents=True, exist_ok=True)
    path = logs / "voicestudio-prerequisites.log"
    installed = []
    with path.open("a", encoding="utf-8") as output:
        for name in missing:
            package = _WINGET_PACKAGES[name]
            command = [winget, "install", "--id", package, "--exact", "--source", "winget",
                       "--silent", "--accept-package-agreements", "--accept-source-agreements"]
            output.write("Installing WinGet package: " + package + "\n")
            output.flush()
            try:
                result = subprocess.run(command, check=False, stdin=subprocess.DEVNULL,
                                        cwd=str(Path(check["checkout"])), stdout=output,
                                        stderr=subprocess.STDOUT, timeout=1200)
            except (OSError, subprocess.TimeoutExpired):
                raise RuntimeError("Could not install " + name + "; see " + str(path)) from None
            if result.returncode:
                raise RuntimeError("WinGet failed to install " + name +
                                   " (exit code " + str(result.returncode) + "); see " + str(path))
            installed.append(name)
    unresolved = [name for name in missing if not locate_tool(name)]
    if unresolved:
        raise RuntimeError("Installed " + ", ".join(installed) +
                           " but Apollo cannot yet find: " + ", ".join(unresolved) +
                           ". Restart Apollo or add the tools to PATH before retrying.")
    return {"ok": True, "installed": installed, "log": str(path)}


def guided_install(checkout, logs_dir, *, approved: bool = False,
                   install_missing: bool = False) -> dict:
    """Run one bounded, explicit repair/install operation, never in background."""
    if not approved:
        raise PermissionError("Owner approval is required before VoiceStudio setup.")
    if not _INSTALL_LOCK.acquire(blocking=False):
        raise RuntimeError("A VoiceStudio installer is already running.")
    try:
        check = diagnose(checkout)
        prereq = {"installed": []}
        if check["missing"]:
            if not install_missing:
                raise RuntimeError("Missing " + ", ".join(check["missing"]) +
                                   ". Approve prerequisite installation or install manually.")
            prereq = install_missing_prerequisites(
                checkout, logs_dir, approved=True)
        # Keep upstream setup in its own checkout and own .venv.
        result = prepare_backend(checkout, logs_dir)
        ready = diagnose(checkout)
        if not ready["backend_venv"]:
            raise RuntimeError(
                "VoiceStudio scripts exited successfully, but the separate Python "
                "environment was not created. Check " + str(result.get("log") or "setup log")
            )
        return {"ok": True, "prepared": ready["prepared"],
                "checkout": result.get("checkout"), "installed_tools": prereq["installed"],
                "setup_log": result.get("log"),
                "prerequisite_log": prereq.get("log"),
                "notice": "Setup finished. Start VoiceStudio and test localhost before enabling it for Apollo."}
    finally:
        _INSTALL_LOCK.release()
