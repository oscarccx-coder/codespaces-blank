"""Conservative Apollo source updater for Git checkouts.

Runtime data in early Apollo versions was accidentally committed to Git. A
normal git status --porcelain check therefore blocks source updates after
Apollo uses its databases or voice files. Permit ONLY those mutable files to
be dirty, while forbidding any incoming Git change to a protected data path.

An update that could affect private data is refused, never auto-stashed or
reset. This program does not handle signed binary releases.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

PRIVATE_PARTS = {"storage", "recordings", "audio", "workspace", "models"}
DATA_FILES = {"apollo_ui/config.local.json", "apollo_ui/config.json",
              "apollo_ui/settings.json"}
DATA_SUFFIXES = (".db", ".sqlite", ".sqlite3", ".db-wal", ".db-shm", ".db-journal",
                 ".sqlite-wal", ".sqlite-shm", ".sqlite-journal",
                 ".sqlite3-wal", ".sqlite3-shm", ".sqlite3-journal",
                 ".log", ".wav", ".mp3", ".m4a", ".flac", ".ogg", ".pcm",
                 ".key", ".pem", ".p12", ".pfx")


def protected(path: str) -> bool:
    """Protect nested per-module runtime files, not only top-level storage.

    This must include all files that a future security-hygiene commit can
    remove, or a fast-forward could discard workstation-specific data.
    """
    value = path.replace("\\", "/").lower()
    while value.startswith("./"):
        value = value[2:]
    parts = tuple(part for part in value.split("/") if part)
    if not parts:
        return False
    name = parts[-1]
    return (bool(set(parts) & PRIVATE_PARTS)
            or name.endswith(DATA_SUFFIXES)
            or name == ".env" or name.startswith(".env.")
            or value in DATA_FILES)

def git(root: Path, *args: str, timeout: int = 180) -> bytes:
    result = subprocess.run(["git", "-C", str(root), *args],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            check=False, timeout=timeout)
    if result.returncode:
        err = result.stderr.decode("utf-8", errors="replace").strip()
        out = result.stdout.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed ({result.returncode}): {err or out}")
    return result.stdout


def _generated_bytecode(path: str) -> bool:
    """Python's compiled import cache is neither source code nor user state."""
    normalized = path.replace("\\", "/").lower()
    parts = normalized.split("/")
    return "__pycache__" in parts and normalized.endswith((".pyc", ".pyo"))


def changed_worktree_paths(root: Path) -> list[str]:
    """Parse Git's NUL-delimited porcelain status, including renames."""
    data = git(root, "status", "--porcelain=v1", "--untracked-files=all", "-z")
    rows = data.decode("utf-8", errors="surrogateescape").split("\0")
    paths = []
    idx = 0
    while idx < len(rows):
        row = rows[idx]
        idx += 1
        if not row:
            continue
        if len(row) < 4 or row[2] != " ":
            raise ValueError("Unexpected Git status output; update stopped.")
        status = row[:2]
        paths.append(row[3:])
        if "R" in status or "C" in status:
            if idx >= len(rows) or not rows[idx]:
                raise ValueError("Truncated Git rename status; update stopped.")
            paths.append(rows[idx])
            idx += 1
    return [path for path in paths if not _generated_bytecode(path)]


def incoming_paths(root: Path) -> list[str]:
    # --no-renames includes both old and new names in renames, avoiding
    # accidentally authorising a rename of private data.
    data = git(root, "diff", "--name-only", "--no-renames", "-z", "HEAD", "FETCH_HEAD")
    return [part for part in data.decode("utf-8", errors="surrogateescape").split("\0") if part]


def run_update(root: Path, *, check_only: bool = False, check_remote: bool = False,
               backup_parent=None, repair_recovery: bool = False,
               emit=print) -> int:
    root = root.resolve()
    emit("=========================================================")
    emit(" APOLLO SAFE GIT MAIN UPDATE")
    emit("=========================================================")
    emit(f"[INFO] Source checkout: {root}")
    try:
        if git(root, "rev-parse", "--is-inside-work-tree").strip() != b"true":
            raise RuntimeError("Not inside a Git checkout.")
        if Path(git(root, "rev-parse", "--show-toplevel").decode("utf-8", errors="replace").strip()).resolve() != root:
            raise RuntimeError("Apollo path is not the root of this Git checkout.")
        branch = git(root, "branch", "--show-current").decode().strip()
        if branch != "main":
            raise RuntimeError(f"Current branch is {branch!r}, not main. Switch branches manually.")
        origin = git(root, "remote", "get-url", "origin").decode(errors="replace").strip()
        emit(f"[INFO] Git origin: {origin}")
        from apollo_git_backup import preview_backup, snapshot, restore_missing
        paths = changed_worktree_paths(root)
        blocked = [path for path in paths if not protected(path)]
        data = [path for path in paths if protected(path)]
        backup_plan = None
        if repair_recovery or check_only:
            backup_plan = preview_backup(root, backup_parent)
            allowed = set(backup_plan["recovery_files"]) if repair_recovery else set()
        else:
            allowed = set()
        real_blockers = [path for path in blocked if path not in allowed]
        if real_blockers:
            emit(f"[STOPPED] {len(real_blockers)} modified or untracked code file(s). No files changed.")
            for path in real_blockers[:12]:
                emit(f"  [CODE] {path}")
            if set(blocked) == set(real_blockers) and set(blocked) & {
                "apollo_ui/Setup/RUN_APOLLO_UPDATER_RECOVERY.bat",
                "apollo_ui/Setup/apollo_git_source_update.py",
            }:
                emit("[FIX] These obsolete recovery launchers can be safely archived "
                     "after a verified backup using --repair-recovery.")
            else:
                emit("[FIX] Review, commit or manually move code edits. Never reset user data.")
            return 2
        if allowed:
            emit("[PLAN] " + str(len(allowed)) +
                 " verified untracked legacy recovery launcher(s) will be archived outside Git.")
        if data:
            emit(f"[SAFE] {len(data)} changed runtime data file(s) will be preserved.")
        if check_only:
            if backup_plan is None:
                backup_plan = preview_backup(root, backup_parent)
            emit("[BACKUP PREVIEW] " + str(backup_plan["private_files"]) +
                 " private file(s), " + str(backup_plan["estimated_bytes"]) +
                 " bytes; destination: " + backup_plan["backup_parent"])
            emit("[CHECK] Read-only preflight completed. No Git fetch, pull or file changes.")
            return 0
        before = git(root, "rev-parse", "HEAD").decode().strip()
        emit("[UPDATE] Fetching origin/main...")
        git(root, "fetch", "--progress", "origin", "main", timeout=360)
        ancestor = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", "HEAD", "FETCH_HEAD"],
                                  capture_output=True, check=False)
        if ancestor.returncode != 0:
            raise RuntimeError("origin/main is not a fast-forward of local main. History was not overwritten.")
        changed = incoming_paths(root)
        unsafe = [path for path in changed if protected(path)]
        if unsafe:
            emit(f"[STOPPED] Incoming update modifies {len(unsafe)} private runtime path(s). No files merged.")
            for path in unsafe[:12]:
                emit(f"  [PRIVATE] {path}")
            emit("[FIX] Requires an explicit, reviewed data-preserving migration. No force reset or auto-stash.")
            return 3
        if check_remote:
            if not changed:
                emit("[UP-TO-DATE] Apollo source is already up to date.")
            else:
                emit(f"[AVAILABLE] {len(changed)} code path(s) can be fast-forwarded from origin/main.")
            emit("[CHECK] This fetched upstream changes for comparison but did not merge them.")
            return 0
        if not changed and not allowed:
            emit("[UP-TO-DATE] Apollo source is already up to date.")
            return 0
        # A real update always gets an external SHA256-verified private-data snapshot
        # BEFORE merging source. Only approved, specifically named untracked legacy
        # launchers are relocated, never arbitrary user code or tracked files.
        backup = snapshot(root, backup_parent, relocate_recovery=bool(allowed),
                          emit=emit)
        try:
            if changed:
                emit(f"[UPDATE] Fast-forwarding {len(changed)} code path(s)...")
                git(root, "merge", "--ff-only", "FETCH_HEAD", timeout=360)
                after = git(root, "rev-parse", "HEAD").decode().strip()
                if before == after:
                    raise RuntimeError("Git reported success but HEAD did not advance.")
                emit(f"[UPDATED] Source advanced from {before[:12]} to {after[:12]}.")
            else:
                emit("[UP-TO-DATE] Apollo source is current; obsolete recovery "
                     "launchers were safely archived.")
        finally:
            # Even on a failed merge, recover only missing, previously verified
            # private data. No existing version is ever overwritten.
            restore_missing(root, Path(backup["path"]), emit=emit)
        emit("[BACKUP LOCATION] " + backup["path"])
        emit("[NEXT] Restart Apollo to load updated code if [UPDATED] is present.")
        return 0
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        emit(f"[ERROR] {exc}")
        emit("[SAFE] No reset or destructive cleanup command was performed.")
        return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="Apollo guarded main-branch source updater")
    parser.add_argument("--check", action="store_true", help="Read-only local preflight")
    parser.add_argument("--check-remote", action="store_true", help="Fetch and assess origin/main without installing")
    parser.add_argument("--no-pause", action="store_true", help="Accepted for BAT compatibility")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--backup-parent", type=Path,
                        help="Existing drive/location for external, unencrypted private backup")
    parser.add_argument("--repair-recovery", action="store_true",
                        help="After backup, archive only two known untracked legacy launcher files")
    args = parser.parse_args(argv)
    if args.check and args.check_remote:
        parser.error("--check and --check-remote cannot be combined")
    log = Path(tempfile.gettempdir()) / "Apollo_Git_Main_Update.log"
    with log.open("a", encoding="utf-8", errors="replace") as handle:
        handle.write(f"\nApollo updater {datetime.now(timezone.utc).isoformat()}\n")
        def emit(message):
            print(message, flush=True)
            handle.write(message + "\n")
            handle.flush()
        result = run_update(args.root, check_only=args.check,
                            check_remote=args.check_remote,
                            backup_parent=args.backup_parent,
                            repair_recovery=args.repair_recovery, emit=emit)
        emit(f"[RESULT] Git update result code {result}.")
        emit(f"[LOG] {log}")
    return result


if __name__ == "__main__":
    sys.exit(main())
