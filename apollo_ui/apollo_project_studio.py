"""Apollo Project Studio: saved app projects, reviewable worker tasks and issues.

This storage/coordination layer never executes generated code, changes Apollo's
trusted core, deploys an app, or approves worker output automatically.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sqlite3
import threading
from datetime import datetime, timezone

ROLES = ("manager", "architect", "implementer", "tester", "reviewer", "integrator")
STATES = ("todo", "running", "review", "accepted", "blocked")
MAX_TASKS = 120
MAX_PROJECTS = 100
PROJECT_TEMPLATE = (
    ("Architect design", "architect", "Write a clear architecture and identify interfaces and dependencies."),
    ("Implementation draft", "implementer", "Propose code and changes in a separate project, not Apollo core."),
    ("Tests and failure modes", "tester", "Define automated tests, startup failures, errors and edge cases."),
    ("Review changes", "reviewer", "Review risks, correctness, test gaps and maintainability."),
    ("Integration handoff", "integrator", "Prepare a user-reviewable release plan and rollback instructions."),
)


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def clean_text(value, max_chars=2000, *, name="text"):
    if not isinstance(value, str):
        raise ValueError(name + " must be text.")
    value = value.strip()
    if not value or len(value) > max_chars:
        raise ValueError(name + f" must contain between 1 and {max_chars} characters.")
    return value


def safe_slug(title):
    value = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:42]
    return value or "project"


class StudioStore:
    """SQLite transactions plus user-local projects outside tracked source code."""

    def __init__(self, base_dir, *, memory=False):
        self.root = Path(base_dir).resolve()
        self.lock = threading.RLock()
        self.db_path = ":memory:" if memory else str(self.root / "storage" / "databases" / "project_studio.db")
        if not memory:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, timeout=10, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL, brief TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'planning',
            folder TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tasks(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL, parent_id INTEGER,
            title TEXT NOT NULL, brief TEXT NOT NULL, role TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'todo', iteration INTEGER NOT NULL DEFAULT 0,
            result TEXT NOT NULL DEFAULT '', evidence TEXT NOT NULL DEFAULT '',
            feedback TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id),
            FOREIGN KEY(parent_id) REFERENCES tasks(id)
        );
        CREATE TABLE IF NOT EXISTS issues(
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,
            title TEXT NOT NULL, details TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'open',
            assigned_task INTEGER, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id),
            FOREIGN KEY(assigned_task) REFERENCES tasks(id)
        );
        CREATE TABLE IF NOT EXISTS events(
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,
            task_id INTEGER, kind TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        );
        """)
        self.conn.commit()

    def close(self):
        with self.lock:
            self.conn.close()

    def _project(self, project_id):
        p = self.conn.execute("SELECT * FROM projects WHERE id=?", (int(project_id),)).fetchone()
        if not p:
            raise KeyError("Project not found")
        return dict(p)

    def _task(self, task_id):
        t = self.conn.execute("SELECT * FROM tasks WHERE id=?", (int(task_id),)).fetchone()
        if not t:
            raise KeyError("Task not found")
        return dict(t)

    def list_projects(self):
        with self.lock:
            return [dict(x) for x in self.conn.execute("SELECT * FROM projects ORDER BY id DESC LIMIT ?", (MAX_PROJECTS,))]

    def details(self, project_id):
        with self.lock:
            project = self._project(project_id)
            tasks = [dict(x) for x in self.conn.execute(
                "SELECT * FROM tasks WHERE project_id=? ORDER BY id", (project["id"],))]
            issues = [dict(x) for x in self.conn.execute(
                "SELECT * FROM issues WHERE project_id=? ORDER BY id DESC", (project["id"],))]
            return {"project": project, "tasks": tasks, "issues": issues}

    def _event(self, project_id, task_id, kind, detail):
        self.conn.execute(
            "INSERT INTO events(project_id,task_id,kind,detail,created_at) VALUES(?,?,?,?,?)",
            (project_id, task_id, kind, detail[:2500], utcnow()))

    def add_project(self, title, brief):
        title = clean_text(title, 100, name="Project title")
        brief = clean_text(brief, 6000, name="Project brief")
        with self.lock:
            if self.conn.execute("SELECT count(*) FROM projects").fetchone()[0] >= MAX_PROJECTS:
                raise ValueError("Project limit reached. Archive work before creating more.")
            created = utcnow()
            with self.conn:
                cur = self.conn.execute(
                    "INSERT INTO projects(title,brief,created_at,updated_at) VALUES(?,?,?,?)",
                    (title, brief, created, created))
                pid = cur.lastrowid
                # Relative paths cannot escape the workspace: ID is SQLite assigned.
                folder = f"app-{pid:04d}-{safe_slug(title)}"
                self.conn.execute("UPDATE projects SET folder=? WHERE id=?", (folder, pid))
                for name, role, text in PROJECT_TEMPLATE:
                    self._new_task(pid, title=name, brief=text, role=role)
                self._event(pid, None, "created", "Project created with five default review stages")
            if self.db_path != ":memory:":
                project_folder = self.root / "workspace" / "app_development" / folder
                project_folder.mkdir(parents=True, exist_ok=True)
                info = project_folder / "PROJECT.md"
                if not info.exists():
                    # Developer project brief is local, never shipped in signed releases.
                    info.write_text("# " + title + "\n\n" + brief + "\n", encoding="utf-8")
            return self.details(pid)

    def _new_task(self, project_id, *, title, brief, role, parent_id=None):
        t = utcnow()
        cur = self.conn.execute(
            "INSERT INTO tasks(project_id,parent_id,title,brief,role,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,?)", (project_id, parent_id, title, brief, role, t, t))
        return int(cur.lastrowid)

    def add_subtask(self, parent_id, title, brief, role):
        title = clean_text(title, 120, name="Task title")
        brief = clean_text(brief, 5000, name="Task instructions")
        if role not in ROLES:
            raise ValueError("Unknown worker role.")
        with self.lock:
            parent = self._task(parent_id)
            if parent["parent_id"] is not None:
                raise ValueError("Maximum one level of subtasks in beta.")
            if parent["state"] == "accepted":
                raise ValueError("Reopen the parent before adding subtasks.")
            if self.conn.execute("SELECT count(*) FROM tasks WHERE project_id=?", (parent["project_id"],)).fetchone()[0] >= MAX_TASKS:
                raise ValueError("Project task limit reached.")
            with self.conn:
                new_id = self._new_task(parent["project_id"], title=title, brief=brief, role=role, parent_id=parent["id"])
                self._event(parent["project_id"], new_id, "subtask", "Assigned to " + role)
            return self._task(new_id)

    def start_task(self, task_id):
        with self.lock:
            task = self._task(task_id)
            if task["state"] != "todo":
                raise ValueError("Only todo tasks can start.")
            project = self._project(task["project_id"])
            if project["state"] == "approved":
                raise ValueError("Approved projects cannot change without reopening.")
            if self.conn.execute("SELECT count(*) FROM tasks WHERE project_id=? AND state='running'", (task["project_id"],)).fetchone()[0]:
                raise ValueError("Only one worker may run per project at a time.")
            with self.conn:
                self.conn.execute("UPDATE tasks SET state='running',updated_at=? WHERE id=?", (utcnow(), task["id"]))
                self._event(task["project_id"], task["id"], "started", "Worker assigned: " + task["role"])
            return self._task(task["id"])

    def submit_task(self, task_id, result, evidence):
        result = clean_text(result, 14000, name="Worker result")
        evidence = clean_text(evidence, 2500, name="Review evidence")
        with self.lock:
            task = self._task(task_id)
            if task["state"] != "running":
                raise ValueError("Start the task before submitting a draft.")
            with self.conn:
                self.conn.execute("UPDATE tasks SET state='review',result=?,evidence=?,iteration=iteration+1,updated_at=? WHERE id=?",
                                  (result, evidence, utcnow(), task["id"]))
                self._event(task["project_id"], task["id"], "submitted", "Draft awaiting human review")
            return self._task(task["id"])

    def review_task(self, task_id, accepted, feedback):
        feedback = clean_text(feedback, 3500, name="Review notes")
        with self.lock:
            task = self._task(task_id)
            if task["state"] != "review":
                raise ValueError("Only submitted work can be reviewed.")
            if accepted and self.conn.execute(
                "SELECT count(*) FROM tasks WHERE parent_id=? AND state!='accepted'", (task["id"],)
            ).fetchone()[0]:
                raise ValueError("All subtasks must be accepted first.")
            with self.conn:
                self.conn.execute(
                    "UPDATE tasks SET state=?,feedback=?,updated_at=? WHERE id=?",
                    ("accepted" if accepted else "todo", feedback, utcnow(), task["id"]))
                self._event(task["project_id"], task["id"], "review",
                            ("accepted: " if accepted else "changes requested: ") + feedback)
            return self._task(task["id"])

    def reopen_task(self, task_id, reason):
        reason = clean_text(reason, 2500, name="Reopen reason")
        with self.lock:
            task = self._task(task_id)
            if self._project(task["project_id"])["state"] == "approved":
                raise ValueError("Reopen the project first.")
            if task["state"] == "running":
                raise ValueError("Wait for worker completion or mark failure.")
            with self.conn:
                self.conn.execute(
                    "UPDATE tasks SET state='todo',feedback=?,updated_at=? WHERE id=?",
                    (reason, utcnow(), task["id"]))
                self._event(task["project_id"], task["id"], "reopened", reason)
            return self._task(task["id"])

    def fail_task(self, task_id, error):
        error = clean_text(error, 2500, name="Failure reason")
        with self.lock:
            task = self._task(task_id)
            if task["state"] != "running":
                raise ValueError("Only running tasks can fail.")
            with self.conn:
                self.conn.execute("UPDATE tasks SET state='blocked',feedback=?,updated_at=? WHERE id=?",
                                  (error, utcnow(), task["id"]))
                self._event(task["project_id"], task["id"], "failed", error)
            return self._task(task["id"])

    def report_issue(self, project_id, title, details):
        title = clean_text(title, 120, name="Issue title")
        details = clean_text(details, 5000, name="Issue details")
        with self.lock:
            project = self._project(project_id)
            if project["state"] == "approved":
                raise ValueError("Reopen the project to report fixes.")
            with self.conn:
                now = utcnow()
                cur = self.conn.execute(
                    "INSERT INTO issues(project_id,title,details,created_at,updated_at) VALUES(?,?,?,?,?)",
                    (project["id"], title, details, now, now))
                self._event(project["id"], None, "issue", "Issue reported: " + title)
                return self.issue(cur.lastrowid)

    def issue(self, issue_id):
        with self.lock:
            row = self.conn.execute("SELECT * FROM issues WHERE id=?", (int(issue_id),)).fetchone()
            if not row:
                raise KeyError("Issue not found")
            return dict(row)

    def assign_issue(self, issue_id):
        with self.lock:
            item = self.issue(issue_id)
            if item["state"] != "open":
                raise ValueError("Only open issues can be assigned to a fix.")
            with self.conn:
                tid = self._new_task(item["project_id"], title="Fix: " + item["title"],
                                      brief=item["details"], role="implementer")
                self.conn.execute("UPDATE issues SET state='in_progress',assigned_task=?,updated_at=? WHERE id=?",
                                  (tid, utcnow(), item["id"]))
                self._event(item["project_id"], tid, "issue-fix", "Issue assigned for rework")
            return self._task(tid)

    def close_issue(self, issue_id):
        with self.lock:
            issue = self.issue(issue_id)
            if issue["assigned_task"] is None or self._task(issue["assigned_task"])["state"] != "accepted":
                raise ValueError("A reviewer must accept the assigned fix before issue closure.")
            with self.conn:
                self.conn.execute("UPDATE issues SET state='closed',updated_at=? WHERE id=?", (utcnow(), issue["id"]))
                self._event(issue["project_id"], issue["assigned_task"], "issue-closed", "Reviewed fix accepted")
            return self.issue(issue_id)

    def audit(self, project_id, limit=60):
        with self.lock:
            self._project(project_id)
            rows = self.conn.execute(
                "SELECT * FROM events WHERE project_id=? ORDER BY id DESC LIMIT ?",
                (int(project_id), min(100, max(1, int(limit)))))
            return [dict(x) for x in rows.fetchall()]

    def recover_interrupted_tasks(self, project_id):
        """Owner-triggered recovery after an app exit or killed model process.

        The UI should confirm no worker is actively drafting before calling.
        It intentionally does NOT auto-retry or pretend a draft succeeded.
        """
        with self.lock:
            self._project(project_id)
            running = self.conn.execute(
                "SELECT id FROM tasks WHERE project_id=? AND state='running'",
                (int(project_id),)).fetchall()
            with self.conn:
                for item in running:
                    self.conn.execute(
                        "UPDATE tasks SET state='blocked',feedback=?,updated_at=? WHERE id=?",
                        ("Worker interrupted before review. Retry requires user action.", utcnow(), item["id"]))
                    self._event(int(project_id), item["id"], "interrupted",
                                "Running worker marked blocked for explicit user review and retry")
            return len(running)

    def approve_project(self, project_id):
        """Must be called only after user clicks explicit UI approval."""
        with self.lock:
            state = self.details(project_id)
            if state["project"]["state"] == "approved":
                raise ValueError("Already approved.")
            if not state["tasks"] or any(t["state"] != "accepted" for t in state["tasks"]):
                raise ValueError("Every worker and subtask needs human acceptance.")
            if any(i["state"] != "closed" for i in state["issues"]):
                raise ValueError("Resolve all reported issues before approving.")
            with self.conn:
                self.conn.execute("UPDATE projects SET state='approved',updated_at=? WHERE id=?",
                                  (utcnow(), int(project_id)))
                self._event(project_id, None, "approved", "Workflow approved by the user; no code executed")
            return self._project(project_id)

    def reopen_project(self, project_id, reason):
        reason = clean_text(reason, 2500, name="Reopen reason")
        with self.lock:
            project = self._project(project_id)
            with self.conn:
                self.conn.execute("UPDATE projects SET state='planning',updated_at=? WHERE id=?", (utcnow(), project["id"]))
                self._event(project["id"], None, "project-reopened", reason)
            return self._project(project["id"])
