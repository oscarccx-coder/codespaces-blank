"""Local, opt-in Apollo data backups. No model weights, code or secrets in archives."""
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile

# Backup user memory, research, voice profiles and their selected work projects.
# Deliberately excludes models, updater trust keys, cache, logs, and recursive backups.
ROOTS = ("storage/databases", "storage/state", "storage/training",
         "storage/media/voice_imprint", "workspace")
MAX_FILES = 15000
MAX_BYTES = 4 * 1024**3
ARCHIVE_PREFIX = "files/"


def _allowed(relative):
    path = PurePosixPath(relative)
    if (not relative or path.is_absolute() or "\\" in relative
            or any(part in ("", ".", "..") for part in relative.split("/"))):
        return False
    if not any(relative == p or relative.startswith(p + "/") for p in ROOTS):
        return False
    if any(part.startswith(".") and part not in (".apollo_project.json",) for part in path.parts):
        return False
    if any(part.lower() in ("__pycache__", ".git", "backups", "cache", "models", ".venv", "node_modules")
           for part in path.parts):
        return False
    if path.name in ("apollo_running.flag", "release_private.pem", "release_public.pem"):
        return False
    return True


def list_backup_files(root):
    root = Path(root).resolve()
    rows = []
    total = 0
    for name in ROOTS:
        folder = root / name
        if not folder.is_dir():
            continue
        for file in sorted(folder.rglob("*")):
            if file.is_symlink() or not file.is_file():
                continue
            rel = file.relative_to(root).as_posix()
            if not _allowed(rel):
                continue
            size = file.stat().st_size
            total += size
            rows.append((rel, file, size))
            if total > MAX_BYTES or len(rows) > MAX_FILES:
                raise ValueError("Backup too large. Move bulky projects out of workspace first.")
    return rows


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def make_backup(root, destination):
    root = Path(root).resolve()
    path = Path(destination).expanduser().resolve()
    if path.exists():
        raise FileExistsError("Choose a new backup filename; existing files are not overwritten")
    rows = list_backup_files(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Database copies use SQLite's backup API so a running DB isn't copied mid-write.
    with tempfile.TemporaryDirectory(prefix="apollo_backup_") as tmp:
        with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=5) as archive:
            entries = []
            for rel, file, size in rows:
                source = file
                if file.suffix.lower() in (".db", ".sqlite", ".sqlite3"):
                    try:
                        source = Path(tmp) / (str(len(entries)) + ".db")
                        with sqlite3.connect("file:" + str(file) + "?mode=ro", uri=True) as current:
                            with sqlite3.connect(source) as snapshot:
                                current.backup(snapshot)
                    except (sqlite3.Error, OSError) as exc:
                        raise RuntimeError("Could not snapshot database " + rel) from exc
                data = source.read_bytes()
                entries.append({"path": rel, "bytes": len(data), "sha256": _hash(data)})
                archive.writestr(ARCHIVE_PREFIX + rel, data)
            archive.writestr("manifest.json", json.dumps({
                "product": "Apollo", "format": 1,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "entries": entries,
                "note": "Local unencrypted backup. Keep private.",
            }, indent=2))
    return {"file": str(path), "files": len(rows), "bytes": sum(x["bytes"] for x in entries)}


def inspect_backup(source):
    source = Path(source).expanduser().resolve()
    with zipfile.ZipFile(source) as archive:
        members = archive.namelist()
        if not members or len(members) > MAX_FILES + 1 or len(set(members)) != len(members):
            raise ValueError("Invalid backup member count or duplicates")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("product") != "Apollo" or manifest.get("format") != 1:
            raise ValueError("Not a supported Apollo backup")
        entries = manifest.get("entries")
        if not isinstance(entries, list) or len(entries) > MAX_FILES:
            raise ValueError("Malformed Apollo backup")
        seen = set()
        total = 0
        for entry in entries:
            if not isinstance(entry, dict) or not _allowed(entry.get("path", "")):
                raise ValueError("Unsafe backup path")
            rel = entry["path"]
            key = rel.casefold()
            if key in seen:
                raise ValueError("Duplicate backup destination")
            seen.add(key)
            member = ARCHIVE_PREFIX + rel
            info = archive.getinfo(member)
            if (info.is_dir() or (info.external_attr >> 16) & 0o170000 == 0o120000
                    or info.file_size != entry.get("bytes")):
                raise ValueError("Unsafe backup entry")
            total += info.file_size
            if total > MAX_BYTES:
                raise ValueError("Expanded backup too large")
            if not isinstance(entry.get("sha256"), str) or len(entry["sha256"]) != 64:
                raise ValueError("Missing backup checksum")
        if set(members) != {"manifest.json"} | {ARCHIVE_PREFIX + x["path"] for x in entries}:
            raise ValueError("Archive contains unexpected files")
        return {"files": len(entries), "bytes": total, "entries": entries}


def restore_backup(root, source, confirmed=False):
    if not confirmed:
        raise PermissionError("Restore needs explicit confirmation and Apollo must be closed")
    root = Path(root).resolve()
    preview = inspect_backup(source)
    # Stage everything and check SHA256 before touching live files.
    with tempfile.TemporaryDirectory(prefix="apollo_restore_") as tmp:
        staged = Path(tmp) / "new"
        previous = Path(tmp) / "previous"
        staged.mkdir()
        previous.mkdir()
        with zipfile.ZipFile(source) as archive:
            for entry in preview["entries"]:
                rel = entry["path"]
                target = staged / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(ARCHIVE_PREFIX + rel) as inp, target.open("wb") as out:
                    shutil.copyfileobj(inp, out, length=1024 * 1024)
                if _hash(target.read_bytes()) != entry["sha256"]:
                    raise ValueError("Backup checksum mismatch: " + rel)
        replaced, created = [], []
        try:
            for entry in preview["entries"]:
                rel = entry["path"]
                live = root / rel
                # Never follow user-controlled symlinks, even inside the install.
                if not live.resolve().is_relative_to(root) or live.is_symlink():
                    raise ValueError("Unsafe restore destination: " + rel)
                if live.exists():
                    if not live.is_file():
                        raise ValueError("Restore path is not a file: " + rel)
                    old = previous / rel
                    old.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(live, old)
                    replaced.append((live, old))
                else:
                    created.append(live)
                live.parent.mkdir(parents=True, exist_ok=True)
                tmp_target = live.with_name(live.name + ".apollo-restore-tmp")
                shutil.copy2(staged / rel, tmp_target)
                os.replace(tmp_target, live)
        except Exception:
            for live in created:
                live.unlink(missing_ok=True)
            for live, old in reversed(replaced):
                shutil.copy2(old, live)
            raise
    return {"ok": True, "restored": preview["files"], "bytes": preview["bytes"]}
