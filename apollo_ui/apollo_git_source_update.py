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

DATA_DIRECTORIES = (
    "apollo_ui/storage/", "apollo_ui/audio/", "apollo_ui/workspace/",
    "apollo_ui/models/",
)
DATA_FILES = {"apollo_ui/config.local.json"}
DATA_SUFFIXES = (".db", ".sqlite", ".sqlite3", ".log")


def protected(path: str) -> bool:
    path = path.replace("\\", "/").lower().lstrip("./")
    return (path in DATA_FILES or path.startswith(DATA_DIRECTORIES)
            or (path.startswith("apollo_ui/") and "/" not in path[len("apollo_ui/"):]
                and path.endswith(DATA_SUFFIXES)))


def git(root: Path, *args: str, timeout: int = 180) -> bytes:
    result = subprocess.run(["git", "-C", str(root), *args],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            check=False, timeout=timeout)
    if result.returncode:
        err = result.stderr.decode("utf-8", errors="replace").strip()
        out = result.stdout.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed ({result.returncode}): {err or out}")
    return result.stdout


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
    return paths


def incoming_paths(root: Path) -> list[str]:
    # --no-renames includes both old and new names in renames, avoiding
    # accidentally authorising a rename of private data.
    data = git(root, "diff", "--name-only", "--no-renames", "-z", "HEAD", "FETCH_HEAD")
    return [part for part in data.decode("utf-8", errors="surrogateescape").split("\0") if part]


def run_update(root: Path, *, check_only: bool = False, check_remote: bool = False, emit=print) -> int:
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
        paths = changed_worktree_paths(root)
        blocked = [path for path in paths if not protected(path)]
        data = [path for path in paths if protected(path)]
        if blocked:
            emit(f"[STOPPED] {len(blocked)} modified or untracked code file(s). No files changed.")
            for path in blocked[:12]:
                emit(f"  [CODE] {path}")
            emit("[FIX] Commit, stash or manually move CODE edits before updating. Do not reset user data.")
            return 2
        if data:
            emit(f"[SAFE] {len(data)} changed runtime data file(s) will be preserved.")
        if check_only:
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
        if not changed:
            emit("[UP-TO-DATE] Apollo source is already up to date.")
            return 0
        if check_remote:
            emit(f"[AVAILABLE] {len(changed)} code path(s) can be fast-forwarded from origin/main.")
            emit("[CHECK] This fetched upstream changes for comparison but did not merge them.")
            return 0
        emit(f"[UPDATE] Fast-forwarding {len(changed)} code path(s)...")
        git(root, "merge", "--ff-only", "FETCH_HEAD", timeout=360)
        after = git(root, "rev-parse", "HEAD").decode().strip()
        if before == after:
            raise RuntimeError("Git reported success but HEAD did not advance.")
        emit(f"[UPDATED] Source advanced from {before[:12]} to {after[:12]}.")
        emit("[NEXT] Restart Apollo to load the updated code. User data was not reset.")
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
        result = run_update(args.root, check_only=args.check, check_remote=args.check_remote, emit=emit)
        emit(f"[RESULT] Git update result code {result}.")
        emit(f"[LOG] {log}")
    return result


if __name__ == "__main__":
    sys.exit(main())
