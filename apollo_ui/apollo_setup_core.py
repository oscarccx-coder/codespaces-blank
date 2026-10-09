"""Apollo setup checks, device preferences and XTTS diagnostics. No heavy imports at startup."""
from pathlib import Path
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone

from apollo_xtts_paths import chosen_xtts_folder, XTTS_FILES

PROFILES = {
    "desktop": {"title": "Desktop / Gaming PC", "model_hint": "qwen2.5-coder:7b", "voice": True, "description": "Full Windows GUI, Ollama and optional NVIDIA XTTS."},
    "laptop": {"title": "Lightweight laptop", "model_hint": "qwen2.5:3b", "voice": False, "description": "Smaller local model; avoid GPU-intensive voice by default."},
    "pi": {"title": "Raspberry Pi 5 (headless)", "model_hint": "qwen2.5:3b", "voice": False, "description": "Headless API only; use pi/install_pi.sh on ARM64."},
}


def _read_json(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def profile_path(root):
    return Path(root).resolve() / "storage" / "state" / "device_profile.json"


def read_profile(root):
    data = _read_json(profile_path(root))
    name = data.get("profile", "desktop")
    return name if name in PROFILES else "desktop"


def save_profile(root, name):
    if name not in PROFILES:
        raise ValueError("Unknown device profile")
    path = profile_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    value = {"profile": name, "updated_at": datetime.now(timezone.utc).isoformat()}
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return value


def package_version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return ""


def check_ollama(url="http://127.0.0.1:11434"):
    # Only localhost; diagnostics must never submit personal data to arbitrary URLs.
    if not (url.startswith("http://127.0.0.1:") or url.startswith("http://localhost:")):
        return {"ok": False, "detail": "Only local Ollama is checked"}
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/tags", timeout=2) as response:
            data = json.loads(response.read(200000).decode("utf-8"))
        return {"ok": True, "models": [x.get("name", "") for x in data.get("models", [])][:20]}
    except Exception as exc:
        return {"ok": False, "detail": type(exc).__name__ + ": Ollama not responding locally"}


def xtts_diagnostic(root, deep=False):
    root = Path(root).resolve()
    settings = _read_json(root / "storage" / "media" / "voice_imprint" / "settings.json")
    selected = settings.get("model_dir")
    model_dir = Path(selected).expanduser() if selected else chosen_xtts_folder(root)
    missing = [name for name in XTTS_FILES if not (model_dir / name).is_file()]
    pins = {"torch": "2.11.0", "torchvision": "0.26.0", "torchaudio": "2.11.0",
            "torchcodec": "0.16.0", "coqui-tts": "0.27.5", "transformers": "4.57.6"}
    packages = {name: package_version(name) for name in pins}
    mismatches = [name for name, expected in pins.items()
                  if packages[name].split("+")[0] != expected]
    issues = []
    if missing:
        issues.append("XTTS model incomplete: " + ", ".join(missing))
    if mismatches:
        issues.append("Wrong or missing Python packages: " + ", ".join(mismatches))
    if package_version("TTS") and package_version("coqui-tts"):
        issues.append("Conflicting legacy TTS and coqui-tts distributions detected")
    if sys.prefix == sys.base_prefix and os.name == "nt":
        issues.append("Apollo is using system Python instead of its private .venv")
    if not shutil.which("ffmpeg") and not settings.get("ffmpeg_shared_bin"):
        issues.append("FFmpeg not found on PATH or configured as a shared DLL folder")
    worker_log = root / "storage" / "logs" / "xtts_worker.log"
    recent_error = ""
    if worker_log.is_file():
        try:
            lines = worker_log.read_text(encoding="utf-8", errors="replace").splitlines()
            recent_error = "\n".join(lines[-12:])[-1400:]
        except OSError:
            pass
    check = {"model_dir": str(model_dir), "missing_model_files": missing,
             "package_versions": packages, "package_mismatches": mismatches,
             "issues": issues, "worker_log": str(worker_log), "recent_log": recent_error,
             "deep_import": "skipped"}
    if deep and not missing and not mismatches:
        # Heavy CUDA/XTTS imports must be outside the responsive GUI, with a deadline.
        command = [sys.executable, "-c",
                   "import torch; from TTS.tts.configs.xtts_config import XttsConfig; "
                   "print('XTTS_IMPORT_OK'); print('CUDA_AVAILABLE=' + str(torch.cuda.is_available()))"]
        try:
            run = subprocess.run(command, cwd=str(root), capture_output=True,
                                 text=True, timeout=30, check=False)
            check["deep_import"] = (run.stdout + "\n" + run.stderr)[-2000:]
            if run.returncode:
                check["issues"].append("XTTS import failed; inspect deep_import output")
        except subprocess.TimeoutExpired:
            check["deep_import"] = "XTTS import exceeded 30 seconds"
            check["issues"].append("XTTS import timed out; check GPU drivers and Python dependencies")
    check["ok"] = not check["issues"]
    check["recommendation"] = ("Ready for a short synthesis test" if check["ok"]
            else "Run Setup/04_REPAIR_VOICE.bat, then recheck. Existing model files are preserved.")
    return check


def system_checks(root, deep_voice=False):
    root = Path(root).resolve()
    profile = read_profile(root)
    profile_data = PROFILES[profile]
    config = _read_json(root / "config.json")
    user_config = _read_json(root / "storage" / "state" / "user_config.json")
    ollama = check_ollama(str(user_config.get("ollama_url") or config.get("ollama_url") or "http://127.0.0.1:11434"))
    imports = {name: package_version(name) for name in ("PySide6", "numpy", "psutil", "cryptography")}
    venv_python = root / ".venv" / "Scripts" / "python.exe"
    if os.name != "nt":
        venv_python = root / ".venv" / "bin" / "python"
    reports = {"python": sys.executable, "python_version": platform.python_version(),
               "virtual_environment": sys.prefix != sys.base_prefix,
               "venv_exists": venv_python.is_file(), "packages": imports,
               "ollama": ollama, "profile": profile, "profile_info": profile_data,
               "voice": xtts_diagnostic(root, deep=deep_voice)}
    reports["ready_for_chat"] = bool(ollama.get("ok") and
        (profile == "pi" or imports.get("PySide6")))
    reports["next_steps"] = []
    if not reports["virtual_environment"] and profile != "pi":
        reports["next_steps"].append("Run Setup/01_INSTALL.bat")
    if not ollama.get("ok"):
        reports["next_steps"].append("Start Ollama and download a local model")
    if not reports["voice"]["ok"] and profile_data["voice"]:
        reports["next_steps"].append("Open XTTS Diagnostics; use Setup/04_REPAIR_VOICE.bat only if needed")
    return reports
