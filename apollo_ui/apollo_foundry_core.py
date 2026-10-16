"""Apollo Core Engineering: bounded local suggestions and no-publish verification.

This module NEVER invokes git, pushes, executes proposed code, installs
dependencies, changes Apollo core files, or merges branches. Suggestions are
evidence-backed and always require explicit human review.
"""
from __future__ import annotations

import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import threading

MAX_SOURCE_FILES = 240
MAX_SOURCE_BYTES = 110_000
MAX_SUGGESTIONS = 100
MAX_CANDIDATE_FILES = 12
MAX_CANDIDATE_BYTES = 160_000
PROTECTED_PARTS = frozenset({
    "storage", "workspace", "models", "venv", ".venv", ".git", "__pycache__",
    "setup", "keys", "secrets", "private", "backups",
})
PROTECTED_NAMES = frozenset({
    "config.json", ".env", "release_private.pem", "modules_state.json",
    "apollo_memory.db", "credentials.json",
})
SUGGESTION_KINDS = ("todo", "fixme", "syntax", "quality", "testing", "maintainability", "proposed")
STATUSES = ("suggested", "review_requested", "dismissed")


def _utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _source_relative(value):
    if not isinstance(value, str) or not value or len(value) > 180 or "\\" in value:
        raise ValueError("Invalid Apollo source path.")
    pure = PurePosixPath(value)
    if (pure.is_absolute() or len(pure.parts) > 6 or pure.suffix != ".py"
            or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", part) or part.startswith(".")
                   or part.casefold() in PROTECTED_PARTS for part in pure.parts)
            or pure.name.casefold() in PROTECTED_NAMES):
        raise ValueError("Apollo core path is outside the permitted source set.")
    return pure


def _inside(base, relative):
    target = base.joinpath(*relative.parts)
    if target.is_symlink() or any(
        part.is_symlink() for part in target.parents if part != base.parent
    ):
        raise ValueError("Symlinked Apollo source paths are not allowed.")
    if not target.resolve().is_relative_to(base):
        raise ValueError("Apollo source path escapes the installation.")
    return target


def _source_files(base):
    """Scan known code directories, never recursively traverse secrets or data."""
    roots = ("modules", "core", "services", "tools", "tests")
    yielded = 0
    for root_name in roots:
        root = base / root_name
        if not root.is_dir() or root.is_symlink():
            continue
        for path in sorted(root.rglob("*.py")):
            if yielded >= MAX_SOURCE_FILES:
                return
            try:
                rel = path.relative_to(base).as_posix()
                target = _inside(base, _source_relative(rel))
                if not target.is_file() or target.stat().st_size > MAX_SOURCE_BYTES:
                    continue
            except (ValueError, OSError):
                continue
            yielded += 1
            yield rel, target


def _read_json(path):
    if path.is_symlink():
        raise ValueError("Suggestion store cannot be a symlink.")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"version": 1, "suggestions": []}
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ValueError("Invalid suggestion store; refusing to overwrite.")
    suggestions = value.get("suggestions")
    if not isinstance(suggestions, list) or len(suggestions) > MAX_SUGGESTIONS:
        raise ValueError("Invalid suggestion list.")
    return value


class ApolloCoreSuggestions:
    """Deterministic, local-only discovery, deduplication and review queue."""

    def __init__(self, base_dir):
        self.base = Path(base_dir).resolve()
        self.store = self.base / "storage" / "state" / "foundry_core_suggestions.json"
        self.lock = threading.RLock()

    def _save(self, value):
        self.store.parent.mkdir(parents=True, exist_ok=True)
        if self.store.parent.is_symlink() or self.store.is_symlink():
            raise ValueError("Suggestion storage path is symlinked.")
        fd, temp = tempfile.mkstemp(prefix=".core-suggestions-", dir=self.store.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                json.dump(value, out, indent=2)
            os.replace(temp, self.store)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def list(self):
        with self.lock:
            return [dict(x) for x in _read_json(self.store)["suggestions"]]

    def scan(self):
        """Inspect syntax and TODO/FIXME markers. No model or source execution."""
        with self.lock:
            state = _read_json(self.store)
            existing = {x["id"]: x for x in state["suggestions"]}
            new = 0
            inspected = 0
            for relative, target in _source_files(self.base):
                inspected += 1
                try:
                    data = target.read_bytes()
                    text = data.decode("utf-8")
                except (UnicodeError, OSError):
                    continue
                observations = []
                try:
                    tree = ast.parse(text, filename=relative)
                except SyntaxError as exc:
                    tree = None
                    observations.append(("syntax", exc.lineno or 1,
                                         "Python syntax error; requires review."))
                if tree is not None:
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ExceptHandler) and node.type is None:
                            observations.append((
                                "quality", node.lineno,
                                "Bare except handler may hide failures; review exception handling."
                            ))
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            length = (node.end_lineno or node.lineno) - node.lineno
                            if length >= 130:
                                observations.append((
                                    "maintainability", node.lineno,
                                    "Long function; consider smaller testable components."
                                ))
                    if relative.endswith("/module.py"):
                        module_classes = [
                            n for n in tree.body if isinstance(n, ast.ClassDef)
                            and n.name == "Module"
                        ]
                        if module_classes and not any(
                            isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                            and n.name == "self_test"
                            for n in module_classes[0].body
                        ):
                            observations.append((
                                "testing", module_classes[0].lineno,
                                "Module has no self_test method; consider adding a regression."
                            ))
                for line_number, line in enumerate(text.splitlines(), 1):
                    # Do not copy raw source lines into suggestion storage.
                    if re.search(r"\bFIXME\b", line):
                        observations.append(("fixme", line_number,
                                             "FIXME marker in source; inspect and propose a fix."))
                    elif re.search(r"\bTODO\b", line):
                        observations.append(("todo", line_number,
                                             "TODO marker in source; evaluate whether work is needed."))
                for kind, line, summary in observations:
                    if len(state["suggestions"]) >= MAX_SUGGESTIONS:
                        break
                    identity = _digest(f"{relative}:{kind}:{line}".encode())[:20]
                    if identity in existing:
                        item = existing[identity]
                        item["last_seen"] = _utc()
                        item["source_sha256"] = _digest(data)
                        continue
                    entry = {
                        "id": identity, "path": relative, "line": line,
                        "kind": kind, "title": summary,
                        "source_sha256": _digest(data), "status": "suggested",
                        "created_at": _utc(), "last_seen": _utc(),
                        "notes": "", "candidate": None,
                    }
                    state["suggestions"].append(entry)
                    existing[identity] = entry
                    new += 1
            self._save(state)
            return {
                "scanned_files": inspected, "new_suggestions": new,
                "total": len(state["suggestions"]),
                "policy": "local_read_only_no_git_no_core_changes",
            }

    def propose(self, title, rationale, source_path):
        """AI may submit an evidence-linked idea, never approve or implement it."""
        if (not isinstance(title, str) or not 8 <= len(title.strip()) <= 160
                or not isinstance(rationale, str) or not 20 <= len(rationale.strip()) <= 1200):
            raise ValueError("A proposal needs a specific title and evidence-based rationale.")
        relative = _source_relative(source_path)
        target = _inside(self.base, relative)
        if not target.is_file() or target.stat().st_size > MAX_SOURCE_BYTES:
            raise ValueError("Suggestion must refer to an existing small Apollo source file.")
        data = target.read_bytes()
        identity = _digest(
            ("proposed:" + relative.as_posix() + ":" + title.strip().casefold()).encode()
        )[:20]
        with self.lock:
            state = _read_json(self.store)
            for item in state["suggestions"]:
                if item["id"] == identity:
                    return {"suggestion": dict(item), "new": False}
            if len(state["suggestions"]) >= MAX_SUGGESTIONS:
                raise ValueError("Suggestion queue full; review existing suggestions first.")
            entry = {
                "id": identity, "path": relative.as_posix(), "line": 1,
                "kind": "proposed", "title": title.strip(),
                "source_sha256": _digest(data), "status": "suggested",
                "created_at": _utc(), "last_seen": _utc(),
                "notes": "", "rationale": rationale.strip(), "candidate": None,
            }
            state["suggestions"].append(entry)
            self._save(state)
            return {"suggestion": dict(entry), "new": True,
                    "applied": False, "pushed": False}

    def set_review(self, suggestion_id, *, request_review, notes=""):
        """A human-facing UI calls this, never the model's suggestion scanner."""
        if not isinstance(notes, str) or len(notes) > 1000:
            raise ValueError("Notes must be at most 1000 characters.")
        with self.lock:
            state = _read_json(self.store)
            for item in state["suggestions"]:
                if item["id"] == suggestion_id:
                    item["status"] = "review_requested" if request_review else "dismissed"
                    item["notes"] = notes
                    item["reviewed_at"] = _utc()
                    self._save(state)
                    return dict(item)
        raise KeyError("Unknown suggestion.")

    def candidate_status(self, suggestion_id, candidate_dir):
        """Inspect a staged candidate; never execute it or publish it.

        Staging may be performed by an explicitly authorised external
        workflow. The candidate is read-only here. Static verification alone
        is never a release or push approval.
        """
        with self.lock:
            records = _read_json(self.store)["suggestions"]
            item = next((x for x in records if x["id"] == suggestion_id), None)
            if item is None or item["status"] != "review_requested":
                raise ValueError("Owner must request review before candidate verification.")
        folder = Path(candidate_dir).resolve()
        staging = (self.base / "workspace" / "self_improvement").resolve()
        if folder == staging or not folder.is_relative_to(staging):
            raise ValueError("Candidate must be in the isolated improvement workspace.")
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError("Candidate folder unavailable or symlinked.")
        proposal = folder / "proposal.json"
        if proposal.is_symlink() or not proposal.is_file():
            raise ValueError("Missing proposal manifest.")
        record = json.loads(proposal.read_text(encoding="utf-8"))
        changes = record.get("changes")
        if not isinstance(changes, list) or not 1 <= len(changes) <= MAX_CANDIDATE_FILES:
            raise ValueError("Candidate must list 1 to 12 changes.")
        candidate_root = folder / "candidate"
        if candidate_root.is_symlink() or not candidate_root.is_dir():
            raise ValueError("Candidate source folder unavailable.")
        reports = []
        total = 0
        seen_paths = set()
        for change in changes:
            if not isinstance(change, dict):
                raise ValueError("Invalid candidate entry.")
            relative = _source_relative(change.get("path"))
            name = relative.as_posix()
            if name in seen_paths:
                raise ValueError("Duplicate file in staged proposal: " + name)
            seen_paths.add(name)
            original = _inside(self.base, relative)
            proposed = _inside(candidate_root.resolve(), relative)
            if not proposed.is_file() or proposed.stat().st_size > MAX_SOURCE_BYTES:
                raise ValueError("Missing or oversized candidate: " + name)
            data = proposed.read_bytes()
            total += len(data)
            if total > MAX_CANDIDATE_BYTES:
                raise ValueError("Candidate exceeds total size limit.")
            expected_candidate = change.get("candidate_sha256")
            expected_original = change.get("original_sha256")
            if expected_candidate != _digest(data):
                raise ValueError("Candidate hash mismatch: " + name)
            current = _digest(original.read_bytes()) if original.is_file() else None
            if current != expected_original:
                raise ValueError("Original source changed; rebase required: " + name)
            if name == item["path"] and current != item["source_sha256"]:
                raise ValueError("Suggestion evidence is stale; rescan and review.")
            try:
                ast.parse(data.decode("utf-8"), filename=name)
                status = "syntax_pass"
            except (SyntaxError, UnicodeError) as exc:
                status = "syntax_failed"
            reports.append({"path": name, "status": status, "sha256": _digest(data)})
        if item["path"] not in seen_paths:
            raise ValueError("Candidate does not change the reviewed suggestion's source file.")
        return {
            "suggestion_id": suggestion_id,
            "candidate_files": reports,
            "static_pass": all(x["status"] == "syntax_pass" for x in reports),
            "runtime_verified": False,
            "ci_verified": False,
            "owner_approved": False,
            "push_allowed": False,
            "merge_allowed": False,
            "applied": False,
            "required_next": "isolated branch, independent CI, owner diff review and explicit approval",
        }
