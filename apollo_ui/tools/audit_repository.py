"""Read-only Git repository privacy and clutter audit.

Usage from apollo_ui:
    python tools/audit_repository.py
    python tools/audit_repository.py --check-new --base origin/main

Does not print, read or delete file contents. Does not rewrite Git history.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys


PRIVATE_TOP_DIRS = ("storage", "Audio", "workspace", "models")
SENSITIVE_SUFFIXES = (".wav", ".mp3", ".flac", ".ogg", ".db", ".sqlite", ".sqlite3", ".pem", ".key", ".gguf", ".safetensors", ".pyc")
SENSITIVE_BASENAMES = {".env", "credentials.json", "secrets.json", "id_rsa"}


def run_git(root, *args):
    proc = subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip()[:400])
    return proc.stdout


def classify(path):
    value = Path(path)
    segments = value.parts
    if not segments:
        return None
    if segments[0].lower() in {x.lower() for x in PRIVATE_TOP_DIRS}:
        return "personal-runtime-data"
    if "__pycache__" in segments or value.suffix.lower() in SENSITIVE_SUFFIXES:
        return "binary-or-sensitive-file"
    if value.name.lower() in SENSITIVE_BASENAMES:
        return "sensitive-filename"
    return None


def scan(root, base=None, changed_only=False):
    root = Path(root).resolve()
    if changed_only:
        if not base:
            raise ValueError("--check-new requires --base")
        # Diff includes all newly added or modified files, not moved-out/deleted ones.
        files = run_git(root, "diff", "--name-only", "--diff-filter=AM",
                        f"{base}...HEAD", "--", "apollo_ui/").splitlines()
        prefix = "apollo_ui/"
        files = [name[len(prefix):] for name in files if name.startswith(prefix)]
    else:
        files = run_git(root, "ls-files", "--", "apollo_ui/").splitlines()
        prefix = "apollo_ui/"
        files = [name[len(prefix):] for name in files if name.startswith(prefix)]
    flagged = [(path, classify(path)) for path in files if classify(path)]
    counts = {}
    for _, reason in flagged:
        counts[reason] = counts.get(reason, 0) + 1
    return {
        "scope": "new-or-modified" if changed_only else "all-tracked",
        "tracked_paths_checked": len(files),
        "flagged_count": len(flagged),
        "categories": counts,
        "examples": [{"path": path, "reason": reason} for path, reason in flagged[:15]],
        "note": ("Previously committed sensitive files remain in Git history. "
                 "gitignore alone cannot erase them. Do not rewrite history "
                 "without backups and explicit coordination."),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-new", action="store_true",
                        help="exit nonzero if changed files introduce sensitive paths")
    parser.add_argument("--base", default=None,
                        help="Git base ref for changed-file audit, e.g. origin/main")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    try:
        report = scan(root, base=args.base, changed_only=args.check_new)
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps(report, indent=2))
    if args.check_new and report["flagged_count"]:
        raise SystemExit(1)
