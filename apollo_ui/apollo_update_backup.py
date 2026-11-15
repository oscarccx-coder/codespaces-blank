"""Small critical-user-state checkpoint for an assessed Apollo install.

Only SQLite databases and bounded JSON/JSONL state are copied; never voices,
models, user projects or arbitrary private media. These are not overwritten
by a signed release, but a checkpoint permits manual recovery from later
incompatible migrations. DB copying uses SQLite's consistent online backup.
"""
from __future__ import annotations

import hashlib
from contextlib import closing
from pathlib import Path
import shutil
import sqlite3

MAX_ENTRIES = 240
MAX_BYTES = 1024 * 1024 * 1024
STATE_SUFFIXES = {".json", ".jsonl"}


class PersonalCheckpointError(OSError):
    pass


def sources(root):
    root = Path(root).resolve()
    personal = root / "storage"
    entries = []
    for folder, glob_pattern in ((personal / "databases", "*.db"),
                                 (personal / "state", "**/*")):
        if not folder.exists():
            continue
        for path in sorted(folder.glob(glob_pattern)):
            if path.is_symlink():
                raise PersonalCheckpointError("Cannot safely back up a symlinked state file.")
            if not path.is_file():
                continue
            if folder.name == "state" and path.suffix.lower() not in STATE_SUFFIXES:
                continue
            rel = path.relative_to(personal)
            if len(entries) >= MAX_ENTRIES:
                raise PersonalCheckpointError("Too many state files for this checkpoint.")
            entries.append((path, rel))
    total = sum(path.stat().st_size for path, _ in entries)
    if total > MAX_BYTES:
        raise PersonalCheckpointError("Critical state exceeds 1 GiB checkpoint limit; back up separately first.")
    return entries, total


def checkpoint(root, backup_folder):
    """Create copies before code replacement. Never modify personal source."""
    entries, total = sources(root)
    destination_root = Path(backup_folder).resolve() / "personal_state"
    created = []
    for src, rel in entries:
        destination = destination_root / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        if rel.parts[0] == "databases" and src.suffix.lower() == ".db":
            try:
                # The Apollo GUI should already be closed; sqlite backup still
                # creates a consistent copy if another reader remains.
                with closing(sqlite3.connect(src.resolve().as_uri() + "?mode=ro",
                                             uri=True, timeout=10)) as original:
                    with closing(sqlite3.connect(str(destination), timeout=10)) as copy:
                        original.backup(copy, pages=64, sleep=0.02)
                        status = copy.execute("PRAGMA quick_check").fetchone()[0]
                        if status != "ok":
                            raise PersonalCheckpointError("SQLite checkpoint integrity check failed.")
            except sqlite3.Error as exc:
                raise PersonalCheckpointError(
                    "Cannot create consistent SQLite checkpoint: " + type(exc).__name__) from None
        else:
            shutil.copy2(src, destination)
            if hashlib.sha256(src.read_bytes()).digest() != hashlib.sha256(destination.read_bytes()).digest():
                raise PersonalCheckpointError("State checkpoint content hash mismatch.")
        created.append(rel.as_posix())
    return {"files": len(created), "estimated_bytes": total,
            "folder": str(destination_root), "paths": created}
