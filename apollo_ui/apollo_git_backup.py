"""Verified, external, private-data snapshots for owner-approved Apollo Git updates.

No backups are created inside the Git checkout; no backup is auto-deleted.
Only ALLOWLISTED *untracked* legacy recovery launchers may be relocated, after
a complete verified snapshot. This never resets, stashes or overwrites code.
Restore copies only missing protected files, never replacing existing files.
The backup is local and unencrypted: keep it on a trusted drive.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

_RECOVERY_EXTRAS = (
    "apollo_ui/Setup/RUN_APOLLO_UPDATER_RECOVERY.bat",
    "apollo_ui/Setup/apollo_git_source_update.py",
)
_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
              ".mypy_cache", ".ruff_cache", "dist", "build"}
_CHUNK = 1024 * 1024
_MANIFEST = "apollo-backup-manifest.json"


def default_backup_parent(root: Path) -> Path:
    return Path(root).resolve().parent / "Apollo-Private-Backups"


def _within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _root_and_parent(root, backup_parent=None):
    root = Path(root).resolve()
    if not root.is_dir():
        raise FileNotFoundError("Apollo Git directory not found.")
    parent = (Path(backup_parent).expanduser() if backup_parent else
              default_backup_parent(root)).resolve()
    if _within(parent, root) or parent == root:
        raise ValueError("Private backup location must be outside the Git checkout.")
    if parent.is_file() or parent.is_symlink():
        raise ValueError("Backup destination must be a real directory, not a file/link.")
    return root, parent


def _private(relative: str) -> bool:
    # Import lazily so the source updater and snapshot can be tested separately.
    from apollo_git_source_update import protected
    return protected(relative)


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _files(root: Path):
    """Inventory private data without following symlinks or build environments."""
    result = []
    for directory, names, files in os.walk(root, topdown=True, followlinks=False):
        here = Path(directory)
        kept = []
        for name in sorted(names):
            child = here / name
            rel = child.relative_to(root).as_posix()
            if name in _SKIP_DIRS and not _private(rel):
                continue
            if child.is_symlink():
                if _private(rel):
                    raise ValueError("Private symlink/junction needs manual review: " + rel)
                continue
            if name in _SKIP_DIRS:
                continue
            kept.append(name)
        names[:] = kept
        for name in sorted(files):
            path = here / name
            rel = path.relative_to(root).as_posix()
            if not _private(rel):
                continue
            if path.is_symlink() or not path.is_file():
                raise ValueError("Unsupported private file/link: " + rel)
            result.append((rel, path, path.stat().st_size))
    return sorted(result)


def _is_untracked(root: Path, rel: str) -> bool:
    status = subprocess.run(["git", "-C", str(root), "status", "--porcelain=v1",
                             "--untracked-files=all", "--", rel],
                            capture_output=True, check=False, timeout=30)
    return status.returncode == 0 and status.stdout.startswith(b"?? ")


def preview_backup(root: Path, backup_parent=None) -> dict:
    """Read-only preview. Never touches disk beyond listing and stat calls."""
    root, parent = _root_and_parent(root, backup_parent)
    files = _files(root)
    recoveries = [
        rel for rel in _RECOVERY_EXTRAS
        if (root / rel).is_file() and not (root / rel).is_symlink()
        and _is_untracked(root, rel)
    ]
    extra_bytes = sum((root / rel).stat().st_size for rel in recoveries)
    return {
        "backup_parent": str(parent), "private_files": len(files),
        "private_bytes": sum(row[2] for row in files),
        "recovery_files": recoveries,
        "estimated_bytes": sum(row[2] for row in files) + extra_bytes,
        "local_unencrypted": True,
        "notice": "Backup stays outside Git; nothing is moved or restored during preview.",
    }


def _copy_verified(source: Path, destination: Path) -> dict:
    if source.is_symlink() or not source.is_file():
        raise ValueError("Backup source is not a regular file: " + str(source))
    before = _hash(source)
    size = source.stat().st_size
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Never overwrite a previous backup.
    with source.open("rb") as inp, destination.open("xb") as out:
        for chunk in iter(lambda: inp.read(_CHUNK), b""):
            out.write(chunk)
        out.flush()
        os.fsync(out.fileno())
    if _hash(destination) != before or _hash(source) != before:
        raise RuntimeError("File changed during backup, or SHA256 verification failed: " + str(source))
    return {"sha256": before, "size": size}


def _manifest_write(path: Path, manifest: dict):
    temp = path.with_suffix(".tmp")
    with temp.open("x", encoding="utf-8") as out:
        json.dump(manifest, out, indent=2, sort_keys=True)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())
    os.replace(temp, path)


def snapshot(root: Path, backup_parent=None, *, relocate_recovery=False,
             emit=print) -> dict:
    """Create a verified copy of all private runtime files before any Git merge.

    relocate_recovery=True additionally moves only the TWO specifically reviewed
    legacy untracked helper files out of the checkout, after copying and hashing.
    """
    root, parent = _root_and_parent(root, backup_parent)
    items = _files(root)
    extras = [
        rel for rel in _RECOVERY_EXTRAS
        if (root / rel).is_file() and not (root / rel).is_symlink()
        and _is_untracked(root, rel)
    ] if relocate_recovery else []
    needed = sum(item[2] for item in items) + sum((root / rel).stat().st_size for rel in extras)
    disk = parent if parent.is_dir() else parent.parent
    if not disk.is_dir():
        raise FileNotFoundError("Backup destination's parent folder does not exist: " + str(disk))
    if shutil.disk_usage(disk).free < needed + 32 * 1024 * 1024:
        raise RuntimeError("Not enough free space for verified private backup: need at least "
                           + str(needed + 32 * 1024 * 1024) + " bytes.")
    parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    destination = parent / ("apollo-" + stamp + "-" + uuid4().hex[:8])
    destination.mkdir(mode=0o700)
    manifest = {
        "schema": 1, "checkout": str(root),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "private_files": {}, "recovery_files": {}, "local_unencrypted": True,
    }
    emit("[BACKUP] Writing SHA256-verified private snapshot outside Git...")
    try:
        for rel, source, _ in items:
            manifest["private_files"][rel] = _copy_verified(source, destination / "files" / rel)
        for rel in extras:
            manifest["recovery_files"][rel] = {
                **_copy_verified(root / rel, destination / "relocated" / rel),
                "moved": False,
            }
        _manifest_write(destination / _MANIFEST, manifest)
    except Exception:
        # Leave any partial backup for review, but DO NOT remove originals.
        emit("[STOPPED] Backup incomplete. No recovery files moved. Originals kept.")
        raise
    if relocate_recovery:
        for rel in extras:
            source = root / rel
            info = manifest["recovery_files"][rel]
            if not _is_untracked(root, rel) or source.is_symlink() or _hash(source) != info["sha256"]:
                raise RuntimeError("Recovery file changed during backup; nothing else will be moved: " + rel)
            # The file already has two SHA256-verified copies at this point.
            # Only these two allowlisted, Git-untracked launchers can be removed.
            source.unlink()
            info["moved"] = True
            emit("[RELOCATED] Previously untracked helper saved outside Git: " + rel)
            _manifest_write(destination / _MANIFEST, manifest)
    emit("[BACKUP VERIFIED] " + str(destination))
    emit("[BACKUP] " + str(len(items)) + " private file(s) preserved; "
         + str(len(extras)) + " obsolete recovery helper(s) archived.")
    return {"path": str(destination), "private_files": len(items),
            "relocated": len(extras), "total_bytes": needed}


def restore_missing(root: Path, backup_dir: Path, *, emit=print) -> dict:
    """Restore missing, unchanged private paths only; never overwrite any file."""
    root = Path(root).resolve()
    backup_dir = Path(backup_dir).resolve()
    if _within(backup_dir, root):
        raise ValueError("Refusing to restore from inside the Git checkout.")
    manifest_path = backup_dir / _MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != 1 or manifest.get("checkout") != str(root):
        raise ValueError("Backup is not a verified snapshot for this checkout.")
    restored = 0
    already_present = 0
    for rel, entry in manifest.get("private_files", {}).items():
        if not isinstance(rel, str) or not _private(rel):
            raise ValueError("Unexpected path in backup manifest.")
        destination = root / rel
        if _within(destination, root) is False:
            raise ValueError("Backup contains a path outside Apollo checkout.")
        if destination.exists() or destination.is_symlink():
            already_present += 1
            continue
        source = backup_dir / "files" / rel
        if not source.is_file() or source.is_symlink() or _hash(source) != entry["sha256"]:
            raise RuntimeError("Backup SHA256 check failed for: " + rel)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not _within(destination.parent, root):
            raise ValueError("Restore target directory escaped checkout.")
        try:
            with source.open("rb") as inp, destination.open("xb") as out:
                for chunk in iter(lambda: inp.read(_CHUNK), b""):
                    out.write(chunk)
                out.flush()
                os.fsync(out.fileno())
        except FileExistsError:
            already_present += 1
            continue
        if _hash(destination) != entry["sha256"]:
            raise RuntimeError("Restored file hash mismatch, inspect manually: " + rel)
        restored += 1
        emit("[RESTORED] Missing private file: " + rel)
    emit("[RESTORE CHECK] " + str(restored) + " missing file(s) recovered; "
         + str(already_present) + " existing file(s) left untouched.")
    return {"restored": restored, "unchanged": already_present,
            "backup": str(backup_dir)}


__all__ = ["preview_backup", "snapshot", "restore_missing", "default_backup_parent"]
