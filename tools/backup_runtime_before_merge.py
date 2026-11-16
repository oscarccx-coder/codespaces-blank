"""Owner-run, verified workstation backup before adopting Apollo runtime cleanup.

Never pulls, resets, deletes, uploads or changes any source or runtime file.
Stop Apollo and its device/voice workers before executing --backup.
The archive is an unencrypted directory. Store it offline and privately.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess

PRIVATE_DIRS = {"storage", "recordings", "audio", "workspace", "models"}
PRIVATE_SUFFIXES = (".db", ".sqlite", ".sqlite3", ".db-wal", ".db-shm",
                    ".sqlite-wal", ".sqlite-shm", ".log", ".wav", ".mp3",
                    ".m4a", ".flac", ".ogg", ".pem", ".key", ".pfx", ".p12")
PRIVATE_NAMES = {".env", "config.json", "config.local.json", "settings.json"}
SKIP_DIRS = {".git", ".venv", ".venv-pi", "venv", "node_modules", "__pycache__",
             "build", "dist", ".pytest_cache", "cache"}
MAX_ENTRIES = 60000


def private_path(name: str) -> bool:
    path = PurePosixPath(name)
    parts = [p.casefold() for p in path.parts]
    filename = path.name.casefold()
    return (bool(PRIVATE_DIRS.intersection(parts))
            or filename in PRIVATE_NAMES or filename.startswith(".env.")
            or filename.endswith(PRIVATE_SUFFIXES))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inventory(root: Path) -> list[tuple[str, Path, int]]:
    """Include tracked sensitive files plus untracked private runtime files."""
    root = Path(root).resolve(strict=True)
    proc = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                          check=True, capture_output=True, text=True)
    if Path(proc.stdout.strip()).resolve() != root:
        raise ValueError("Choose the Git repository top-level directory, not a subfolder")
    proc = subprocess.run(["git", "-C", str(root), "ls-files", "-z"],
                          check=True, capture_output=True)
    found: set[str] = set()
    for raw in proc.stdout.split(b"\0"):
        if raw:
            name = os.fsdecode(raw).replace("\\", "/")
            if private_path(name):
                found.add(name)
    # Additional untracked/private data is important for a complete backup.
    for current, directories, filenames in os.walk(root, topdown=True, followlinks=False):
        here = Path(current)
        directories[:] = [d for d in directories if d.casefold() not in SKIP_DIRS]
        for d in directories:
            child = here / d
            if child.is_symlink() and private_path(child.relative_to(root).as_posix()):
                raise ValueError("Refusing a symbolic-link private directory")
        directories[:] = [d for d in directories if not (here / d).is_symlink()]
        for name in filenames:
            file = here / name
            rel = file.relative_to(root).as_posix()
            if private_path(rel):
                found.add(rel)
                if len(found) > MAX_ENTRIES:
                    raise ValueError("Too many runtime files; manual backup review required")
    rows = []
    for rel in sorted(found):
        file = root / rel
        if not file.exists() and not file.is_symlink():
            continue
        if file.is_symlink() or not file.is_file() or not file.resolve().is_relative_to(root):
            raise ValueError("Unsafe private file path detected; review before backup")
        rows.append((rel, file, file.stat().st_size))
    return rows


def backup(root: Path, destination: Path, *, confirmed_stopped: bool = False) -> dict:
    if not confirmed_stopped:
        raise PermissionError("Stop Apollo/device/voice workers and pass --confirm-stopped")
    root = Path(root).resolve(strict=True)
    dest = Path(destination).expanduser().resolve()
    if dest.is_relative_to(root) or root.is_relative_to(dest):
        raise ValueError("Backup destination must be outside the checkout and not contain it")
    if dest.exists():
        raise FileExistsError("Choose a new empty backup directory; never overwrite an earlier backup")
    rows = inventory(root)
    if not rows:
        raise ValueError("No private files found; inspect this installation manually")
    total = sum(size for _, _, size in rows)
    if shutil.disk_usage(dest.parent).free < total + 64 * 1024 * 1024:
        raise OSError("Insufficient free disk space for verified full-size backup")
    dest.mkdir(parents=True, mode=0o700, exist_ok=False)
    marker = dest / "INCOMPLETE-BACKUP.txt"
    marker.write_text("Backup was not verified. Do not adopt the cleanup yet.\n", encoding="utf-8")
    records = []
    for rel, source, size in rows:
        target = dest / "files" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        before = source.stat()
        shutil.copy2(source, target)
        after = source.stat()
        if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
            raise RuntimeError("Runtime file changed during backup; stop Apollo and retry in a NEW directory")
        digest = _sha256(source)
        if target.stat().st_size != size or _sha256(target) != digest:
            raise RuntimeError("Backup verification failed; do not adopt cleanup")
        records.append({"path": rel, "bytes": size, "sha256": digest})
    manifest = {"product": "Apollo", "format": "runtime-cleanup-backup-v1",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "files": len(records), "total_bytes": total, "entries": records,
                "warning": "UNENCRYPTED. Never publish or sync this backup to a public repository."}
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    marker.unlink()
    return {"verified": True, "files": len(records), "total_bytes": total,
            "destination": str(dest)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Apollo Git checkout root")
    parser.add_argument("--destination", type=Path, help="New private directory outside Apollo")
    parser.add_argument("--confirm-stopped", action="store_true")
    parser.add_argument("--check", action="store_true", help="Inventory only; writes nothing")
    args = parser.parse_args(argv)
    try:
        if args.check:
            rows = inventory(args.root)
            print(json.dumps({"checked": True, "files": len(rows),
                              "total_bytes": sum(size for _, _, size in rows)}))
        else:
            if args.destination is None:
                parser.error("--destination is required for a real backup")
            print(json.dumps(backup(args.root, args.destination,
                                    confirmed_stopped=args.confirm_stopped)))
        return 0
    except (OSError, ValueError, PermissionError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"[STOPPED] {type(exc).__name__}: {exc}")
        print("No Apollo source update or cleanup was attempted.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
