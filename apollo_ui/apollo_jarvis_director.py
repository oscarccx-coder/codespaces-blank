"""Apollo JARVIS Director: local-first specialist agent missions.

Runs only local Ollama draft-only Foundry workers. Generated code is staged in a
private workspace, statically checked and NEVER executed or installed. Persistent
budgets, owner actions and immutable-at-runtime mission scope guard autonomy.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import sqlite3
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from apollo_project_workers import (
    ROLE_GUIDES, draft_for_task, model_from_config,
    propose_subtasks, validate_subtask_plan,
)

ROLES = tuple(ROLE_GUIDES)
MAX_CALLS = 60
MAX_AGENT_TASKS = 8
MAX_RESULT = 65000
MIN_INTERVAL = 30
MAX_INTERVAL = 3600
MAX_SOURCE = 12000
MAX_FILES = 8
MAX_FILE_CHARS = 28000
STATE_ACTIVE = "RUNNING"
END_STATES = {"STOPPED", "COMPLETED", "BUDGET_EXHAUSTED", "BLOCKED"}
SAFE_EXTENSIONS = {".py", ".json", ".md", ".txt", ".toml"}
SOURCE_CHOICES = (
    "apollo_project_workers.py",
    "apollo_foundry_checks.py",
    "apollo_foundry_sandbox.py",
    "apollo_runtime.py",
    "apollo_learning_missions.py",
    "modules/self_improvement_lab/module.py",
    "modules/architect_bridge/module.py",
)
DEFAULT_BRIEF = (
    "Inspect and improve Apollo's local reliability first. Investigate actual "
    "Foundry worker handoffs, mission recovery, update preflights, reasoning "
    "benchmarks, source evidence and UI usability. Generate concrete, small "
    "PySide6/Python candidates only in the isolated JARVIS workspace. "
    "Do not modify, run or deploy Apollo core. Tests are proposals until executed "
    "by an owner-approved sandbox. Never claim an improvement is verified "
    "merely because a model produced code."
)
FALLBACK = (
    ("Architecture and root causes", "architect", "Identify narrow source-backed change scope, dependencies, constraints, objective acceptance criteria."),
    ("Candidate implementation", "implementer", "Create working Python code and tests for one isolated improvement, not modifications to installed Apollo."),
    ("Regression specification", "tester", "Describe executable verification steps, failure modes and meaningful baseline comparison."),
    ("Independent critical review", "reviewer", "Critique the implementation, identify missing tests, possible regressions and unsafe assumptions."),
    ("Release readiness handoff", "integrator", "Summarise candidates, test gaps, rollback procedure and required owner approvals."),
)


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def text_limit(value, limit, minimum=1):
    if not isinstance(value, str):
        raise ValueError("Expected text.")
    result = value.strip()
    if not minimum <= len(result) <= limit or "\x00" in result:
        raise ValueError("Text length/characters invalid.")
    return result


def candidate_entries(raw):
    """Validate ALL output before writing. No model-generated path escapes."""
    if len(raw) > MAX_RESULT:
        raise ValueError("Agent response too large.")
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        raise ValueError("Implementer did not return valid JSON.") from None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("files"), list):
        raise ValueError("Expected JSON object containing files array.")
    files = parsed["files"]
    if not 1 <= len(files) <= MAX_FILES:
        raise ValueError("Require one to eight candidate files.")
    entries = []
    seen = set()
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("content"), str):
            raise ValueError("Each file requires path and content.")
        original = item["path"]
        posix = original.replace("\\", "/")
        rel = PurePosixPath(posix)
        if (not posix or len(posix) > 180 or posix.startswith("/") or
                ":" in posix or "\x00" in posix or any(x in ("", ".", "..") for x in posix.split("/")) or
                rel.suffix.lower() not in SAFE_EXTENSIONS or
                any(part.startswith(".") for part in rel.parts)):
            raise PermissionError("Unsafe candidate path.")
        normalized = rel.as_posix()
        if normalized.lower() in seen or len(item["content"]) > MAX_FILE_CHARS:
            raise ValueError("Duplicate path or oversized generated file.")
        seen.add(normalized.lower())
        if rel.suffix.lower() == ".py":
            ast.parse(item["content"], filename=normalized)
        if rel.suffix.lower() == ".json":
            json.loads(item["content"])
        entries.append((normalized, item["content"]))
    return entries


class DirectorStore:
    def __init__(self, base, validation=False):
        self.base = Path(base).resolve()
        self.validation = bool(validation)
        self.temp = tempfile.TemporaryDirectory(prefix="apollo_jarvis_validation_") if validation else None
        self.root = Path(self.temp.name) if self.temp else self.base / "storage" / "databases"
        self.root.mkdir(parents=True, exist_ok=True)
        self.workspace = Path(self.temp.name) / "workspace" if self.temp else self.base / "workspace" / "jarvis_director"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(":memory:" if validation else str(self.root / "apollo_jarvis.db"),
                                  check_same_thread=False, timeout=12)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.db:
            self.db.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS missions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              title TEXT NOT NULL, objective TEXT NOT NULL, mode TEXT NOT NULL,
              model TEXT NOT NULL, state TEXT NOT NULL,
              max_calls INTEGER NOT NULL, calls_used INTEGER NOT NULL DEFAULT 0,
              interval_seconds INTEGER NOT NULL, next_due REAL NOT NULL DEFAULT 0,
              round INTEGER NOT NULL DEFAULT 0,
              last_error TEXT NOT NULL DEFAULT '', created TEXT NOT NULL,
              updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS agent_tasks (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              mission_id INTEGER NOT NULL REFERENCES missions(id),
              round INTEGER NOT NULL, role TEXT NOT NULL, title TEXT NOT NULL,
              brief TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'QUEUED',
              attempts INTEGER NOT NULL DEFAULT 0,
              result TEXT NOT NULL DEFAULT '', candidate_path TEXT NOT NULL DEFAULT '',
              created TEXT NOT NULL, updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              mission_id INTEGER NOT NULL REFERENCES missions(id),
              kind TEXT NOT NULL, detail TEXT NOT NULL, created TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS jarvis_tasks ON agent_tasks(mission_id,round,state);
            CREATE TABLE IF NOT EXISTS sandbox_results(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              mission_id INTEGER NOT NULL REFERENCES missions(id),
              task_id INTEGER NOT NULL REFERENCES agent_tasks(id),
              status TEXT NOT NULL, kind TEXT NOT NULL,
              source_digest TEXT NOT NULL DEFAULT '',
              output TEXT NOT NULL DEFAULT '',
              executed INTEGER NOT NULL DEFAULT 0,
              created TEXT NOT NULL
            );
            """)
            # A previous process may have been killed mid-agent call. The call
            # was already budgeted and is not resumed implicitly or counted twice.
            self.db.execute("UPDATE agent_tasks SET state='QUEUED' WHERE state='RUNNING'")

    def close(self):
        with self.lock:
            self.db.close()
        if self.temp:
            self.temp.cleanup()

    def _event(self, mid, kind, detail=""):
        self.db.execute("INSERT INTO events(mission_id,kind,detail,created) VALUES(?,?,?,?)",
                        (mid, kind, str(detail)[:350], utc()))

    def _mission(self, mid):
        row = self.db.execute("SELECT * FROM missions WHERE id=?", (int(mid),)).fetchone()
        if not row:
            raise KeyError("Unknown JARVIS mission.")
        return dict(row)

    def begin(self, title, objective, *, mode="fixed", max_calls=12, interval_seconds=60,
              owner_confirmed=False):
        if owner_confirmed is not True:
            raise PermissionError("Owner approval required to start agent work.")
        title = text_limit(title, 100, 5)
        objective = text_limit(objective, 2500, 20)
        if mode not in {"fixed", "until_stop"}:
            raise ValueError("Invalid mission mode.")
        limit, interval = int(max_calls), int(interval_seconds)
        if not 2 <= limit <= MAX_CALLS or not MIN_INTERVAL <= interval <= MAX_INTERVAL:
            raise ValueError("Call budget or interval out of bounds.")
        model = model_from_config(self.base)
        with self.lock, self.db:
            current = self.db.execute("SELECT count(*) FROM missions WHERE state='RUNNING'").fetchone()[0]
            if current:
                raise RuntimeError("Pause/stop the current mission before starting another.")
            cursor = self.db.execute(
                "INSERT INTO missions(title,objective,mode,model,state,max_calls,interval_seconds,next_due,created,updated) "
                "VALUES(?,?,?,?,'RUNNING',?,?,?, ?,?)",
                (title, objective, mode, model, limit, interval, time.time(), utc(), utc()))
            mid = cursor.lastrowid
            self._event(mid, "mission_started", "Owner authorised local-only specialist drafting.")
            return self._mission(mid)

    def control(self, mid, action):
        if action not in {"pause", "resume", "stop"}:
            raise ValueError("Unknown control.")
        with self.lock, self.db:
            mission = self._mission(mid)
            state = mission["state"]
            if action == "pause" and state == "RUNNING":
                dest = "PAUSED"
            elif action == "resume" and state in {"PAUSED", "BLOCKED"}:
                dest = "RUNNING"
                # Explicit owner retry resets a blocked draft attempt. No code
                # was executed and prior failure events remain in the ledger.
                if state == "BLOCKED":
                    self.db.execute(
                        "UPDATE agent_tasks SET state='QUEUED',attempts=0,updated=? "
                        "WHERE mission_id=? AND state='BLOCKED'",
                        (utc(), mid))
            elif action == "stop" and state not in {"STOPPED", "COMPLETED"}:
                dest = "STOPPED"
            else:
                raise ValueError("Control not available from state: " + state)
            self.db.execute("UPDATE missions SET state=?, next_due=?, updated=? WHERE id=?",
                            (dest, time.time(), utc(), mid))
            self._event(mid, "owner_" + action, "Owner controlled mission state.")
            return self._mission(mid)

    def request_now(self, mid):
        with self.lock, self.db:
            mission = self._mission(mid)
            if mission["state"] != "RUNNING":
                raise PermissionError("Mission must be running.")
            self.db.execute("UPDATE missions SET next_due=?,updated=? WHERE id=?",
                            (time.time(), utc(), mid))
            self._event(mid, "owner_request_next", "A bounded local step was queued.")
            return {"queued": True, "mission_id": int(mid)}

    def detail(self, mid):
        with self.lock:
            mission = self._mission(mid)
            tasks = [dict(row) for row in self.db.execute(
                "SELECT * FROM agent_tasks WHERE mission_id=? ORDER BY id LIMIT 120", (mid,))]
            events = [dict(row) for row in self.db.execute(
                "SELECT * FROM events WHERE mission_id=? ORDER BY id DESC LIMIT 80", (mid,))]
            tests = [dict(row) for row in self.db.execute(
                "SELECT * FROM sandbox_results WHERE mission_id=? ORDER BY id DESC LIMIT 25", (mid,))]
        for task in tasks:
            task["result_preview"] = task.pop("result")[:2500]
        return {"mission": mission, "agents": tasks, "events": events, "sandbox_results": tests}

    def list(self):
        with self.lock:
            return [dict(r) for r in self.db.execute(
                "SELECT id,title,mode,state,max_calls,calls_used,round,updated,last_error FROM missions ORDER BY id DESC LIMIT 30")]

    def _mark_budget(self, mission):
        if mission["calls_used"] >= mission["max_calls"]:
            self.db.execute("UPDATE missions SET state='BUDGET_EXHAUSTED',updated=? WHERE id=?",
                            (utc(), mission["id"]))
            self._event(mission["id"], "budget_exhausted", "No further model calls until owner authorises a new mission.")
            return True
        return False

    def claim(self):
        """Atomic local checkpoint before exactly one model call."""
        with self.lock, self.db:
            mission_row = self.db.execute(
                "SELECT * FROM missions WHERE state='RUNNING' AND next_due<=? ORDER BY id LIMIT 1",
                (time.time(),)).fetchone()
            if not mission_row:
                return None
            m = dict(mission_row)
            task = self.db.execute(
                "SELECT * FROM agent_tasks WHERE mission_id=? AND round=? AND state='QUEUED' ORDER BY id LIMIT 1",
                (m["id"], m["round"])).fetchone()
            pending = self.db.execute(
                "SELECT count(*) FROM agent_tasks WHERE mission_id=? AND round=? AND state='RUNNING'",
                (m["id"], m["round"])).fetchone()[0]
            if pending:
                return None
            if not task:
                count_now = self.db.execute(
                    "SELECT count(*) FROM agent_tasks WHERE mission_id=? AND round=?",
                    (m["id"], m["round"])).fetchone()[0]
                if count_now and m["mode"] == "fixed":
                    self.db.execute("UPDATE missions SET state='COMPLETED',updated=? WHERE id=?",
                                    (utc(), m["id"]))
                    self._event(m["id"], "drafts_completed", "Drafts finished. Tests and deployments not executed.")
                    return None
            if self._mark_budget(m):
                return None
            if task:
                t = dict(task)
                if t["attempts"] >= 2:
                    self.db.execute("UPDATE agent_tasks SET state='BLOCKED',updated=? WHERE id=?", (utc(), t["id"]))
                    self.db.execute("UPDATE missions SET state='BLOCKED',last_error='Agent failed twice',updated=? WHERE id=?",
                                    (utc(), m["id"]))
                    self._event(m["id"], "blocked", "Specialist retry budget exhausted.")
                    return None
                self.db.execute(
                    "UPDATE agent_tasks SET state='RUNNING',attempts=attempts+1,updated=? WHERE id=?",
                    (utc(), t["id"]))
                kind = "task"
            else:
                count = self.db.execute(
                    "SELECT count(*) FROM agent_tasks WHERE mission_id=? AND round=?",
                    (m["id"], m["round"])).fetchone()[0]
                if count:
                    if m["mode"] == "fixed":
                        self.db.execute("UPDATE missions SET state='COMPLETED',updated=? WHERE id=?",
                                        (utc(), m["id"]))
                        self._event(m["id"], "drafts_completed", "Agent drafts finished. No runtime tests or deployments performed.")
                        return None
                    if m["round"] >= 6:
                        self.db.execute("UPDATE missions SET state='BUDGET_EXHAUSTED',updated=? WHERE id=?",
                                        (utc(), m["id"]))
                        self._event(m["id"], "round_limit", "Maximum rounds reached; owner must start another mission.")
                        return None
                    self.db.execute("UPDATE missions SET round=round+1 WHERE id=?", (m["id"],))
                    m["round"] += 1
                kind = "plan"
                t = None
            self.db.execute("UPDATE missions SET calls_used=calls_used+1,next_due=?,updated=? WHERE id=?",
                            (time.time() + m["interval_seconds"], utc(), m["id"]))
            self._event(m["id"], "agent_call", kind if kind == "plan" else t["role"])
            return {"kind": kind, "mission": {**m, "calls_used": m["calls_used"] + 1}, "task": t}

    def save_plan(self, mid, round_number, plan, *, plan_source="local_model"):
        with self.lock, self.db:
            m = self._mission(mid)
            if m["round"] != round_number:
                return False
            # This is one bounded round of agent profiles. A model can propose
            # specialists, but only known Foundry role contracts are allowed.
            for item in plan:
                self.db.execute(
                    "INSERT INTO agent_tasks(mission_id,round,role,title,brief,state,created,updated) "
                    "VALUES(?,?,?,?,?,'QUEUED',?,?)",
                    (mid, round_number, item["role"], item["title"], item["brief"], utc(), utc()))
            self._event(mid, "agents_created", "%s bounded specialists (%s)." % (len(plan), plan_source))
            return True

    def finish(self, mid, task_id, result, candidate_path=""):
        with self.lock, self.db:
            self.db.execute("UPDATE agent_tasks SET state='DONE',result=?,candidate_path=?,updated=? "
                            "WHERE id=? AND mission_id=? AND state='RUNNING'",
                            (result[:MAX_RESULT], candidate_path[:350], utc(), task_id, mid))
            self._event(mid, "agent_draft_saved", "Candidate is UNTESTED. Owner approval required for sandbox/runtime tests.")

    def fail(self, mid, task_id, error, *, planning=False):
        reason = type(error).__name__  # no secrets or network error bodies in ledger
        with self.lock, self.db:
            m = self._mission(mid)
            if not planning and task_id is not None:
                row = self.db.execute("SELECT attempts FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
                exhausted = not row or row["attempts"] >= 2
                self.db.execute("UPDATE agent_tasks SET state=?,updated=? WHERE id=?",
                                ("BLOCKED" if exhausted else "QUEUED", utc(), task_id))
            else:
                exhausted = True
            if exhausted:
                self.db.execute("UPDATE missions SET state='BLOCKED',last_error=?,updated=? WHERE id=?",
                                (reason + " (review local diagnostics)", utc(), mid))
            self._event(mid, "agent_error", reason + "; no execution or installation.")
            return m["state"]

    def stage(self, mid, task_id, raw):
        entries = candidate_entries(raw)
        root = self.workspace / ("mission_%d" % int(mid)) / ("task_%d" % int(task_id)) / "candidate"
        # stage an isolated, never executed candidate tree
        for rel, content in entries:
            target = root.joinpath(*PurePosixPath(rel).parts)
            if root.resolve() not in target.resolve().parents:
                raise PermissionError("Candidate escaped workspace.")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        sha = [{"path": path, "sha256": hashlib.sha256(content.encode()).hexdigest()}
               for path, content in entries]
        meta = root.parent / "candidate_manifest.json"
        meta.write_text(json.dumps({"mission_id": mid, "task_id": task_id,
                                    "files": sha, "status": "STATIC_ONLY_UNTESTED",
                                    "requires": ["owner sandbox approval", "runtime tests",
                                                 "review", "human-approved integration"]}, indent=2),
                        encoding="utf-8")
        return str(root.relative_to(self.base)) if self.base in root.parents else str(root)

    def owner_test_candidate(self, mid, task_id, *, owner_confirmed=False, kind="unit"):
        """ONLY after GUI confirmation. Existing Foundry Docker sandbox, never host Python."""
        if owner_confirmed is not True:
            raise PermissionError("Owner approval required for any executable test.")
        if kind not in {"unit", "ui", "gui"}:
            raise ValueError("Unknown Docker test kind.")
        with self.lock:
            self._mission(mid)
            task = self.db.execute(
                "SELECT * FROM agent_tasks WHERE id=? AND mission_id=?",
                (int(task_id), int(mid))).fetchone()
            if not task or task["state"] != "DONE" or task["role"] != "implementer" or not task["candidate_path"]:
                raise ValueError("Select a completed implementer with staged candidate files.")
        root = self.workspace.resolve()
        folder = (root / ("mission_%d" % int(mid)) / ("task_%d" % int(task_id)) / "candidate").resolve()
        if root not in folder.parents or folder.is_symlink() or not folder.is_dir():
            raise PermissionError("Candidate folder invalid.")
        manifest = folder.parent / "candidate_manifest.json"
        if not manifest.is_file() or manifest.is_symlink():
            raise ValueError("Candidate manifest missing.")
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        if payload.get("mission_id") != int(mid) or payload.get("task_id") != int(task_id):
            raise ValueError("Candidate identity mismatch.")
        entries = payload.get("files", [])
        if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_FILES:
            raise ValueError("Invalid candidate fingerprint manifest.")
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("Invalid fingerprint entry.")
            rel = entry.get("path")
            try:
                if not isinstance(rel, str):
                    raise ValueError("Invalid manifest path.")
                probe = "{}" if rel.lower().endswith(".json") else "pass"
                validated = candidate_entries(json.dumps({
                    "files": [{"path": rel, "content": probe}]}))
            except (PermissionError, ValueError) as error:
                raise ValueError("Unsafe file in candidate manifest.") from error
            dest = folder.joinpath(*PurePosixPath(validated[0][0]).parts)
            if dest.is_symlink() or not dest.is_file() or folder not in dest.resolve().parents:
                raise PermissionError("Missing or escaped candidate file.")
            if hashlib.sha256(dest.read_bytes()).hexdigest() != entry.get("sha256"):
                raise ValueError("Candidate modified since review; revalidate before testing.")
        # The Foundry runner itself uses a separate read-only snapshot,
        # --network=none, resource caps and no mount of Apollo credentials.
        from apollo_foundry_sandbox import run_sandbox
        result = run_sandbox(folder, kind)
        with self.lock, self.db:
            self.db.execute(
                "INSERT INTO sandbox_results(mission_id,task_id,status,kind,source_digest,output,executed,created)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (mid, task_id, str(result.get("status", "unavailable"))[:40], kind,
                 str(result.get("source_digest", ""))[:128],
                 str(result.get("output", ""))[-8000:],
                 int(bool(result.get("executed_project_code"))), utc()))
            self._event(mid, "sandbox_result", "Docker %s: %s; actually ran code=%s" %
                        (kind, result.get("status"), bool(result.get("executed_project_code"))))
        return result

    def source_context(self):
        """Read only fixed, public source files. Never access private memory/logs."""
        parts = []
        for name in SOURCE_CHOICES:
            source = self.base / name
            if not source.is_file() or source.is_symlink():
                continue
            try:
                content = source.read_text(encoding="utf-8")
            except (UnicodeError, OSError):
                continue
            parts.append("FILE " + name + " (truncated excerpt):\n" + content[:1550])
            if sum(len(x) for x in parts) >= MAX_SOURCE:
                break
        return "\n\n".join(parts)[:MAX_SOURCE]


class Director:
    def __init__(self, base, validation=False, *, plan_fn=None, draft_fn=None, clock_seconds=5):
        self.base = Path(base).resolve()
        self.validation = validation
        self.store = DirectorStore(self.base, validation=validation)
        self.plan_fn = plan_fn or propose_subtasks
        self.draft_fn = draft_fn or draft_for_task
        self.stop_event = threading.Event()
        self.wake = threading.Event()
        self._worker = None
        if not validation:
            self._worker = threading.Thread(target=self._loop, args=(clock_seconds,),
                                            daemon=True, name="apollo-jarvis-director")
            self._worker.start()

    def close(self):
        self.stop_event.set()
        self.wake.set()
        if self._worker and self._worker is not threading.current_thread():
            self._worker.join(timeout=2)
        # Do not close the store under an in-flight worker after timeout.
        if not self._worker or not self._worker.is_alive():
            self.store.close()

    def owner_begin(self, title, objective, *, mode="fixed", max_calls=12, interval_seconds=60):
        item = self.store.begin(title, objective, mode=mode, max_calls=max_calls,
                                interval_seconds=interval_seconds, owner_confirmed=True)
        self.wake.set()
        return item

    def owner_control(self, mid, action):
        result = self.store.control(mid, action)
        self.wake.set()
        return result

    def owner_test_candidate(self, mid, task_id, *, kind="unit", approved=False):
        return self.store.owner_test_candidate(mid, task_id, owner_confirmed=approved, kind=kind)

    def request_next(self, mid):
        outcome = self.store.request_now(mid)
        self.wake.set()
        return outcome

    def step(self):
        """One bounded model call; safe to invoke from a background worker."""
        work = self.store.claim()
        if not work:
            return {"status": "idle"}
        m = work["mission"]
        mid = m["id"]
        source = self.store.source_context()
        if work["kind"] == "plan":
            state = {"project": {"title": m["title"], "brief": m["objective"]},
                     "tasks": [{"id": 1, "parent_id": None, "state": "todo",
                                "title": "Plan specialist roles", "brief": m["objective"]}],
                     "meeting_context": "Previous rounds require independent verification.",
                     "source_context": source}
            try:
                proposal = self.plan_fn(state, 1, m["model"], timeout=75)
                plan = validate_subtask_plan({"tasks": proposal})
                essential = {"architect", "implementer", "tester", "reviewer"}
                if not essential.issubset({x["role"] for x in plan}):
                    plan = [{"title": title, "brief": brief, "role": role}
                            for title, role, brief in FALLBACK]
                    source_label = "safe deterministic fallback (model plan incomplete)"
                else:
                    source_label = "validated local Ollama plan"
                if not self.store.save_plan(mid, m["round"], plan, plan_source=source_label):
                    return {"status": "superseded"}
                return {"status": "agents_created", "agents": len(plan), "source": source_label}
            except Exception as exc:
                self.store.fail(mid, None, exc, planning=True)
                return {"status": "blocked", "error_type": type(exc).__name__}
        task = work["task"]
        with self.store.lock:
            previous = [dict(x) for x in self.store.db.execute(
                "SELECT role,title,result FROM agent_tasks WHERE mission_id=? AND round=? AND state='DONE' ORDER BY id",
                (mid, m["round"]))]
        preceding = "\n".join(
            ("Agent %s (%s) draft: %s" % (x["role"], x["title"], x["result"][:900]))
            for x in previous[-4:])[:3600]
        scoped_objective = (
            m["objective"] + "\n\nREQUIRED: You work only in isolated workspace; "
            "you cannot edit, execute or install Apollo core. "
            "Provide genuinely useful implementation candidates, test specifications, "
            "and a concrete independent review. For implementation, include real "
            "tests/test_*.py files that can run in Foundry Docker; source must "
            "remain confined to the isolated candidate. Unexecuted code is NOT a verified fix."
        )
        state = {"project": {"title": m["title"], "brief": scoped_objective},
                 "tasks": [{
                     "id": task["id"], "parent_id": None, "state": "running",
                     "role": task["role"], "title": task["title"],
                     "brief": task["brief"], "feedback": ""
                 }],
                 "issues": [], "source_context": source,
                 "meeting_context": preceding, "test_context": "Not executed; no runtime evidence."}
        try:
            result = self.draft_fn(state, task["id"], m["model"], timeout=90)
            if not isinstance(result, str) or not result.strip() or len(result) > MAX_RESULT:
                raise ValueError("Empty or excessive agent output.")
            location = self.store.stage(mid, task["id"], result) if task["role"] == "implementer" else ""
            self.store.finish(mid, task["id"], result, location)
            return {"status": "draft_saved", "role": task["role"], "candidate": location,
                    "verified": False, "executed": False}
        except Exception as exc:
            self.store.fail(mid, task["id"], exc)
            return {"status": "agent_failed", "role": task["role"], "error_type": type(exc).__name__}

    def _loop(self, clock_seconds):
        while not self.stop_event.is_set():
            try:
                self.step()
            except Exception:
                # Never let one unexpected dispatcher error kill the worker.
                pass
            self.wake.wait(max(1, int(clock_seconds)))
            self.wake.clear()
