from pathlib import Path, PureWindowsPath
from datetime import datetime
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

from apollo_storage import StorageLayout
from apollo_update import sha256_file, verify_manifest_signature


PROTECTED_TOP_LEVEL = {"storage", "workspace", "pending_modules", "config.json", "Audio", "models", "venv", ".venv", ".git"}


def wait_for_pid(pid, timeout=90):
    if not pid:
        return True
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            os.kill(int(pid), 0)
        except OSError:
            return True
        time.sleep(0.25)
    return False


def safe_relative(value):
    """Reject traversal and Windows device/drive paths on every host platform."""
    if not isinstance(value, str) or not value.strip() or "\\x00" in value:
        raise ValueError("Unsafe empty or binary update path")
    value = value.replace("\\\\", "/").replace("\\", "/")
    windows = PureWindowsPath(value)
    if value.startswith("/") or windows.drive or windows.root or value.endswith("/"):
        raise ValueError(f"Unsafe update path: {value}")
    parts = value.split("/")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    if any(not p or p in {".", ".."} or ":" in p or p.endswith((" ", ".")) or p.split(".")[0].upper() in reserved for p in parts):
        raise ValueError(f"Unsafe update path: {value}")
    if parts[0].casefold() in {p.casefold() for p in PROTECTED_TOP_LEVEL}:
        raise ValueError(f"Protected update path: {value}")
    return Path(*parts)


def ensure_inside(root, rel):
    """Also reject symlinked directories that escape the signed update root."""
    root = Path(root).resolve()
    candidate = (root / rel).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError(f"Update path escapes expected directory: {rel}")
    return candidate


def preflight_manifest(stage, target, manifest):
    """Validate all signed entries and staged hashes BEFORE touching live files."""
    if not isinstance(manifest.get("files"), list) or not isinstance(manifest.get("remove", []), list):
        raise ValueError("Malformed update manifest lists")
    checked, paths = [], set()
    for entry in manifest["files"]:
        if not isinstance(entry, dict):
            raise ValueError("Malformed update entry")
        rel = safe_relative(entry.get("path"))
        key = str(rel).casefold()
        if key in paths:
            raise ValueError(f"Duplicate update path: {rel}")
        paths.add(key)
        source = ensure_inside(Path(stage) / "payload", rel)
        dest = ensure_inside(target, rel)
        if not source.is_file() or dest.is_dir():
            raise ValueError(f"Missing or invalid staged file: {rel}")
        if sha256_file(source) != str(entry.get("sha256")):
            raise ValueError(f"Staged hash mismatch: {rel}")
        checked.append((rel, source))
    removed = []
    for value in manifest.get("remove", []):
        rel = safe_relative(value)
        key = str(rel).casefold()
        if key in paths:
            raise ValueError(f"Conflicting update/remove path: {rel}")
        paths.add(key)
        ensure_inside(target, rel)
        removed.append(rel)
    return checked, removed


def apply_update(target, stage, restart=False, wait_pid=None):
    target = Path(target).resolve()
    stage = Path(stage).resolve()
    manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
    storage = StorageLayout(target)
    storage.ensure_layout()
    public_key = storage.updates / "trust" / "release_public.pem"
    ok, detail = verify_manifest_signature(manifest, public_key)
    if not ok:
        return {"ok": False, "stage": "signature", "error": detail}

    # Validate all files before creating a backup or changing a single byte.
    try:
        update_files, remove_files = preflight_manifest(stage, target, manifest)
    except (OSError, ValueError) as exc:
        return {"ok": False, "stage": "preflight", "error": str(exc)}

    if wait_pid and not wait_for_pid(wait_pid):
        return {"ok": False, "stage": "wait", "error": "Apollo did not exit before updater timeout."}

    version = str(manifest.get("version", "unknown"))
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = storage.backups / "core_updates" / f"before-{version}-{stamp}"
    backup.mkdir(parents=True, exist_ok=True)
    transaction = {"version": version, "created": [], "replaced": [], "removed": []}

    config_path = target / "config.json"
    if config_path.exists():
        shutil.copy2(config_path, backup / "config.json")

    def backup_existing(rel):
        dest = target / rel
        if not dest.exists():
            transaction["created"].append(str(rel).replace("\\", "/"))
            return
        backup_path = backup / "files" / rel
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dest, backup_path)
        transaction["replaced"].append(str(rel).replace("\\", "/"))

    try:
        for rel, source in update_files:
            backup_existing(rel)
            destination = target / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            temp = destination.with_name(destination.name + ".apollo-update-tmp")
            shutil.copy2(source, temp)
            os.replace(temp, destination)

        for rel in remove_files:
            destination = target / rel
            if destination.exists() and destination.is_file():
                backup_existing(rel)
                destination.unlink()
                transaction["removed"].append(str(rel).replace("\\", "/"))

        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["version"] = version
        temp_config = config_path.with_suffix(".json.apollo-update-tmp")
        temp_config.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        os.replace(temp_config, config_path)

        health = subprocess.run(
            [sys.executable, str(target / "apollo_health_check.py"), "--root", str(target)],
            cwd=str(target), capture_output=True, text=True, timeout=120,
        )
        if health.returncode != 0:
            raise RuntimeError("Health check failed: " + (health.stdout + health.stderr)[-4000:])

        log_dir = storage.updates / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / f"installed-{version}-{stamp}.json").write_text(json.dumps({
            "ok": True, "transaction": transaction, "backup": str(backup),
            "health": health.stdout[-4000:],
        }, indent=2) + "\n", encoding="utf-8")

        if restart:
            launcher = target / "launch_apollo.pyw"
            subprocess.Popen([sys.executable, str(launcher)], cwd=str(target), close_fds=True)
        return {"ok": True, "version": version, "backup": str(backup)}

    except Exception as exc:
        rollback_errors = []
        for rel_text in transaction["created"]:
            path = target / Path(rel_text)
            try:
                if path.exists() and path.is_file():
                    path.unlink()
            except Exception as rollback_exc:
                rollback_errors.append(str(rollback_exc))
        for rel_text in transaction["replaced"]:
            rel = Path(rel_text)
            source = backup / "files" / rel
            destination = target / rel
            if source.exists():
                try:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
                except OSError as rollback_exc:
                    rollback_errors.append(str(rollback_exc))
        if (backup / "config.json").exists():
            try:
                shutil.copy2(backup / "config.json", config_path)
            except OSError as rollback_exc:
                rollback_errors.append(str(rollback_exc))
        log_dir = storage.updates / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / f"rollback-{version}-{stamp}.json").write_text(json.dumps({
            "ok": False, "error": f"{type(exc).__name__}: {exc}",
            "transaction": transaction, "backup": str(backup),
        }, indent=2) + "\n", encoding="utf-8")
        return {"ok": False, "stage": "rollback", "error": f"{type(exc).__name__}: {exc}", "restored": not rollback_errors, "rollback_errors": rollback_errors}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply a staged signed Apollo update.")
    parser.add_argument("--target", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--wait-pid", type=int, default=0)
    parser.add_argument("--restart", action="store_true")
    args = parser.parse_args()
    result = apply_update(args.target, args.stage, restart=args.restart, wait_pid=args.wait_pid or None)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result.get("ok") else 1)
