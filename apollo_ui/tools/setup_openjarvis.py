"""Set up the pinned framework on Apollo's drive, without changing its venv."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import venv
import zipfile
import tempfile

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from apollo_openjarvis import PIN, atomic_json


def run(argv, **kwargs):
    print("Running:", " ".join(map(str, argv)), flush=True)
    subprocess.run(list(map(str, argv)), check=True, **kwargs)


def source_ready(base):
    source = base / "vendor/openjarvis"
    lock = json.loads((base / "vendor/openjarvis.lock.json").read_text(encoding="utf-8"))
    def verified():
        return all((source / name).is_file() and hashlib.sha256((source / name).read_bytes()).hexdigest() == digest
                   for name, digest in lock["verification_files"].items())
    if verified(): return source
    if (base.parent / ".git").exists() and shutil.which("git"):
        run(["git", "-C", base.parent, "submodule", "update", "--init", "--recursive", "--depth", "1", "--", "apollo_ui/vendor/openjarvis"])
        if verified(): return source
    archive_url = f"https://github.com/open-jarvis/OpenJarvis/archive/{PIN}.zip"
    print("Downloading pinned OpenJarvis source", PIN, flush=True)
    with tempfile.TemporaryDirectory(prefix="apollo-openjarvis-") as temporary:
        bundle = Path(temporary) / "source.zip"
        request = urllib.request.Request(archive_url, headers={"User-Agent": "Apollo-OpenJarvis-Setup"})
        with urllib.request.urlopen(request, timeout=90) as response, bundle.open("wb") as target:
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > 100 * 1024 * 1024: raise ValueError("Source archive exceeds limit")
                target.write(chunk)
        stage = Path(temporary) / "source"; stage.mkdir()
        with zipfile.ZipFile(bundle) as archive:
            total = 0
            for member in archive.infolist():
                parts = Path(member.filename).parts
                if len(parts) < 2 or member.is_dir(): continue
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Source archive contains a symbolic link")
                relative = Path(*parts[1:]); target = (stage / relative).resolve()
                if not target.is_relative_to(stage.resolve()): raise ValueError("Unsafe archive member")
                total += member.file_size
                if total > 200 * 1024 * 1024: raise ValueError("Unpacked source exceeds limit")
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as src, target.open("wb") as dst: shutil.copyfileobj(src, dst)
        for name, digest in lock["verification_files"].items():
            if hashlib.sha256((stage / name).read_bytes()).hexdigest() != digest:
                raise ValueError("Pinned source verification failed: " + name)
        source.parent.mkdir(parents=True, exist_ok=True)
        if source.exists():
            # Do not destroy an owner's modified framework checkout.
            if any(source.iterdir()): raise RuntimeError("Existing OpenJarvis source differs from the pin; preserve or back it up before repair")
            source.rmdir()
        shutil.copytree(stage, source)
    return source


def interpreter():
    if not getattr(sys, "frozen", False) and (3, 10) <= sys.version_info[:2] < (3, 14):
        return sys.executable
    launcher = shutil.which("py")
    if launcher:
        for version in ("-3.13", "-3.12", "-3.11"):
            result = subprocess.run([launcher, version, "-c", "import sys; print(sys.executable)"], capture_output=True, text=True)
            if result.returncode == 0: return result.stdout.strip()
    raise RuntimeError("Install Python 3.13 or 3.12, then rerun this setup. Apollo's current environment is preserved.")


def install(base=BASE, *, full=False, native=False):
    source = source_ready(base)
    env = base / "storage/environments/openjarvis"
    python = env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file(): run([interpreter(), "-m", "venv", env])
    dependencies = ["httpx>=0.27,<1", "PyYAML>=6,<7", "psutil>=5,<8", "croniter>=2,<7", "tomlkit>=0.12,<1", "rich>=13,<15"]
    run([python, "-m", "pip", "install", *dependencies])
    if full:
        # Optional backend packages do not cause account connections or model downloads.
        run([python, "-m", "pip", "install", str(source) + "[server,memory-bm25,memory-pdf,security-signing,sandbox-docker,tools-search,learning-dspy,learning-gepa]"])
    if native:
        run([python, "-m", "pip", "install", source / "rust/crates/openjarvis-python"])
    envvars = dict(os.environ)
    envvars["PYTHONPATH"] = str(source / "src")
    envvars["OPENJARVIS_HOME"] = str(base / "storage/openjarvis/framework")
    code = "from openjarvis.agents.orchestrator import OrchestratorAgent; from openjarvis.skills.executor import SkillExecutor; from openjarvis.learning.routing.router import HeuristicRouter; from openjarvis.traces.store import TraceStore; print('Apollo OpenJarvis core imports passed')"
    run([python, "-c", code], env=envvars)
    atomic_json(base / "storage/openjarvis/installation.json", {"commit": PIN, "core_imports_passed": True,
                "full_dependencies": full, "native_installed": native, "python": str(python)})
    print("OpenJarvis is ready. Open Apollo → Apps → OpenJarvis, or use Chat.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="Also install optional research/learning/server dependencies")
    parser.add_argument("--native", action="store_true", help="Build native backends; requires Rust and a platform C/C++ linker")
    args = parser.parse_args()
    try: install(full=args.full, native=args.native)
    except Exception as exc:
        print(f"Setup failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
