from pathlib import Path
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


PROTECTED_TOP_LEVEL = {"storage", "workspace", "pending_modules", "config.json"}


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
    rel = Path(str(value).replace("\\", "/"))
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise ValueError(f"Unsafe update path: {value}")
    if rel.parts[0] in PROTECTED_TOP_LEVEL:
        raise ValueError(f"Protected update path: {value}")
    return rel


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
        for item in manifest.get("files", []):
            rel = safe_relative(item.get("path"))
            source = stage / "payload" / rel
            if sha256_file(source) != str(item.get("sha256")):
                raise ValueError(f"Staged hash mismatch: {rel}")
            backup_existing(rel)
            destination = target / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            temp = destination.with_name(destination.name + ".apollo-update-tmp")
            shutil.copy2(source, temp)
            os.replace(temp, destination)

        for item in manifest.get("remove", []):
            rel = safe_relative(item)
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
        for rel_text in transaction["created"]:
            path = target / Path(rel_text)
            try:
                if path.exists() and path.is_file():
                    path.unlink()
            except Exception:
                pass
        for rel_text in transaction["replaced"]:
            rel = Path(rel_text)
            source = backup / "files" / rel
            destination = target / rel
            if source.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
        if (backup / "config.json").exists():
            shutil.copy2(backup / "config.json", config_path)
        log_dir = storage.updates / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / f"rollback-{version}-{stamp}.json").write_text(json.dumps({
            "ok": False, "error": f"{type(exc).__name__}: {exc}",
            "transaction": transaction, "backup": str(backup),
        }, indent=2) + "\n", encoding="utf-8")
        return {"ok": False, "stage": "rollback", "error": f"{type(exc).__name__}: {exc}", "restored": True}


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
