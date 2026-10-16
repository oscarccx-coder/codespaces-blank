"""Apollo Foundry: opt-in, container-only runtime tests for untrusted project code.

Refuse to run when Docker or an owner-installed image is unavailable.
Never run generated code through host Python, shell=True, or in Apollo's venv.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import os
import secrets
import shutil
import subprocess
import tempfile
import time

PYTHON_IMAGE = "python:3.13-slim"
QT_IMAGE = "apollo-foundry-qt:phase1"
SANDBOX_KINDS = {"unit": QT_IMAGE, "gui": QT_IMAGE}
MAX_FILE_COUNT = 100
MAX_FILE_BYTES = 512 * 1024
MAX_TOTAL_BYTES = 5 * 1024 * 1024
ALLOWED_EXTENSIONS = {".py", ".json", ".toml", ".txt", ".md", ".yaml", ".yml", ".qss", ".png", ".svg", ".ico"}
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "node_modules", ".mypy_cache", "storage", "secrets"}
OUTPUT_LIMIT = 15000
MAX_LOG_BYTES = 256 * 1024
RUN_TIMEOUTS = {"unit": 45, "gui": 18}

# Only launch.py from the private project snapshot is started, by the Docker image.
# A process that remains alive for 3 seconds passes the *startup survival*
# smoke test, NOT a claim that any widget actually works.
_GUI_SMOKE = r"""
import subprocess, sys, time
p = subprocess.Popen([sys.executable, "-B", "launch.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
try:
    time.sleep(3)
    rc = p.poll()
    if rc is not None:
        out, err = p.communicate(timeout=1)
        print("GUI exited before smoke window. Code:", rc)
        print((err or out).decode("utf-8", "replace")[-4000:])
        sys.exit(1)
    print("GUI STARTUP SURVIVED 3s. This does NOT verify widget events.")
finally:
    if p.poll() is None:
        p.terminate()
        try:
            p.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            p.kill()
            p.communicate()
"""


class SandboxUnavailable(RuntimeError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat()


def availability(kind, *, docker_bin=None):
    if kind not in SANDBOX_KINDS:
        raise ValueError("Unknown Foundry sandbox test kind")
    binary = docker_bin or shutil.which("docker")
    if not binary:
        return {"ok": False, "reason": "Docker is not installed or is not on PATH.", "image": SANDBOX_KINDS[kind]}
    try:
        proc = subprocess.run(
            [binary, "image", "inspect", SANDBOX_KINDS[kind]],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            text=True, timeout=12, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"ok": False, "reason": f"Docker not responding: {type(error).__name__}", "image": SANDBOX_KINDS[kind]}
    if proc.returncode != 0:
        return {"ok": False, "reason": f"Required trusted image not installed: {SANDBOX_KINDS[kind]}. No automatic pulls.", "image": SANDBOX_KINDS[kind]}
    return {"ok": True, "image": SANDBOX_KINDS[kind], "reason": "Container image installed"}


def _make_snapshot(src: Path, dest: Path):
    src = Path(src)
    if src.is_symlink():
        raise ValueError("Symlinked app projects cannot run.")
    src = src.resolve()
    if not src.is_dir():
        raise ValueError("Selected app project folder is missing.")
    count = 0
    total = 0
    dest.mkdir(mode=0o755)
    for current, dirs, files in os.walk(src, followlinks=False):
        current_dir = Path(current)
        if current_dir.is_symlink():
            raise ValueError("Symlinked project directory is forbidden.")
        for name in list(dirs):
            p = current_dir / name
            if p.is_symlink():
                raise ValueError("Symlinked project paths are forbidden.")
            if name.startswith(".") or name in SKIP_DIRS:
                dirs.remove(name)
        for name in files:
            f = current_dir / name
            if f.is_symlink():
                raise ValueError("Symlinked source files cannot run.")
            if name.startswith(".") or f.suffix.lower() not in ALLOWED_EXTENSIONS:
                continue
            stat = f.stat()
            count += 1
            total += stat.st_size
            if count > MAX_FILE_COUNT or total > MAX_TOTAL_BYTES or stat.st_size > MAX_FILE_BYTES:
                raise ValueError("App source exceeds Foundry sandbox file or size limits.")
            relative = f.relative_to(src)
            out = dest / relative
            out.parent.mkdir(parents=True, exist_ok=True)
            with f.open("rb") as read, out.open("xb") as write:
                payload = read.read(MAX_FILE_BYTES + 1)
                if len(payload) > MAX_FILE_BYTES:
                    raise ValueError("Project file changed or grew beyond snapshot budget")
                write.write(payload)
            out.chmod(0o644)
    return count


def snapshot_fingerprint(snapshot):
    """Hash exactly the files copied into the container's read-only /work."""
    root = Path(snapshot).resolve()
    digest = hashlib.sha256()
    for item in sorted(root.rglob("*")):
        if not item.is_file() or item.is_symlink():
            continue
        data = item.read_bytes()
        name = item.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(name).to_bytes(4, "big"))
        digest.update(name)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def project_fingerprint(folder):
    """Bounded current-source fingerprint without running generated code."""
    with tempfile.TemporaryDirectory(prefix="apollo-foundry-fingerprint-") as temp:
        target = Path(temp) / "project"
        _make_snapshot(folder, target)
        return snapshot_fingerprint(target)


def _container_args(binary, container_name, snapshot, kind):
    # Restrict both writable paths and Linux capabilities. No socket,
    # Apollo storage, user home, environment secrets or network is mounted.
    args = [
        binary, "run", "--rm", "--pull=never", "--name", container_name,
        "--network=none", "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true",
        "--pids-limit=64", "--cpus=1", "--memory=768m", "--memory-swap=768m",
        "--user=65534:65534",
        "--tmpfs=/tmp:rw,nosuid,nodev,size=64m,mode=1777",
        "--env=PYTHONDONTWRITEBYTECODE=1", "--env=PYTHONNOUSERSITE=1",
        "--env=QT_QPA_PLATFORM=offscreen", "--env=HOME=/tmp",
        "--workdir=/work",
        "--mount", f"type=bind,source={snapshot},target=/work,readonly",
        SANDBOX_KINDS[kind],
    ]
    if kind == "unit":
        args.extend(["python", "-B", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"])
    else:
        args.extend(["python", "-B", "-c", _GUI_SMOKE])
    return args


def _force_remove(binary, name):
    """Only remove the exact randomly named Foundry container."""
    try:
        command = subprocess.run(
            [binary, "rm", "-f", name], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=8, check=False,
        )
        return command.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _execute_bounded(argv, binary, name, timeout):
    """Run Docker with capped on-disk output, never an unlimited RAM pipe."""
    with tempfile.TemporaryFile() as output:
        proc = subprocess.Popen(
            argv, stdin=subprocess.DEVNULL,
            stdout=output, stderr=subprocess.STDOUT,
        )
        expires = time.monotonic() + timeout
        timed_out = False
        overflow = False
        cleanup_ok = None
        try:
            while proc.poll() is None:
                size = os.fstat(output.fileno()).st_size
                if size > MAX_LOG_BYTES:
                    overflow = True
                    break
                if time.monotonic() >= expires:
                    timed_out = True
                    break
                time.sleep(0.05)
            if os.fstat(output.fileno()).st_size > MAX_LOG_BYTES:
                overflow = True
            if timed_out or overflow:
                cleanup_ok = _force_remove(binary, name)
                if proc.poll() is None:
                    proc.kill()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
        finally:
            if proc.poll() is None:
                cleanup_ok = _force_remove(binary, name)
                proc.kill()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
        size = os.fstat(output.fileno()).st_size
        output.seek(max(0, size - OUTPUT_LIMIT))
        text = output.read(OUTPUT_LIMIT).decode("utf-8", "replace")
        return {
            "returncode": proc.returncode,
            "output": text,
            "timeout": timed_out,
            "overflow": overflow,
            "cleanup_ok": cleanup_ok,
        }


def run_sandbox(project_folder, kind, *, docker_bin=None):
    """Attempt Docker-only testing; return an auditable structured result.

    Caller must show a human confirmation first. This method will never
    execute project code outside a container, even when Docker is missing.
    """
    if kind not in SANDBOX_KINDS:
        raise ValueError("Invalid sandbox test kind")
    start = time.monotonic()
    base = {"kind": f"docker-{kind}", "phase": "Foundry Sandbox",
            "created_at": _now(), "executed_project_code": False,
            "passed_ui_interactions": False, "status": "unavailable",
            "output": "", "reason": "", "image": SANDBOX_KINDS[kind]}
    check = availability(kind, docker_bin=docker_bin)
    if not check["ok"]:
        return {**base, "reason": check["reason"], "duration_seconds": round(time.monotonic()-start, 2)}
    binary = docker_bin or shutil.which("docker")
    if not binary:
        return {**base, "reason": "Docker executable disappeared."}
    src = Path(project_folder)
    if kind == "unit" and not (src / "tests").is_dir():
        return {**base, "status": "incomplete", "reason": "Add a tests/ folder with test_*.py files."}
    if kind == "unit" and not any((src / "tests").rglob("test_*.py")):
        return {**base, "status": "incomplete", "reason": "No tests/test_*.py files found; refusing false-green zero-test run."}
    if kind == "gui" and not (src / "launch.py").is_file():
        return {**base, "status": "incomplete", "reason": "Add launch.py to start the app GUI."}

    with tempfile.TemporaryDirectory(prefix="apollo-foundry-") as temp:
        snapshot = Path(temp) / "project"
        _make_snapshot(src, snapshot)
        source_digest = snapshot_fingerprint(snapshot)
        name = "apollo-foundry-" + secrets.token_hex(7)
        argv = _container_args(binary, name, str(snapshot.resolve()), kind)
        # A file-backed log is polled while Docker runs. A generated app
        # cannot consume unlimited Apollo RAM by flooding stdout.
        try:
            proc = _execute_bounded(argv, binary, name, RUN_TIMEOUTS[kind])
            code = proc["returncode"]
            if proc["timeout"]:
                status, reason = "timeout", "Container exceeded its time limit"
            elif proc["overflow"]:
                status, reason = "failed", "Test log output exceeded the bounded output quota"
            elif code == 0:
                status, reason = "passed", "Docker test process completed successfully"
            elif code in (125, 126, 127):
                status, reason = "unavailable", f"Docker could not start the test (exit {code})"
            else:
                status, reason = "failed", f"Isolated test exited with code {code}"
            if kind == "unit" and "Ran 0 tests" in proc["output"]:
                status, reason = "incomplete", "No tests were discovered"
            if proc["cleanup_ok"] is False:
                reason += ". Warning: Docker container cleanup could not be confirmed."
            return {
                **base, "status": status, "reason": reason,
                "source_digest": source_digest,
                "executed_project_code": code not in (125, 126, 127)
                and (code is not None or proc["timeout"] or proc["overflow"]),
                "output": proc["output"],
                "duration_seconds": round(time.monotonic()-start, 2),
            }
        except OSError as error:
            return {
                **base, "status": "unavailable",
                "reason": f"Docker could not be started: {type(error).__name__}: {error}",
                "duration_seconds": round(time.monotonic()-start, 2),
            }
