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
        CREATE TABLE IF NOT EXISTS test_runs(
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,
            status TEXT NOT NULL, kind TEXT NOT NULL, report TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        );
        CREATE TABLE IF NOT EXISTS meetings(
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL,
            topic TEXT NOT NULL, turns TEXT NOT NULL, decisions TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        );
        CREATE INDEX IF NOT EXISTS idx_foundry_meetings_project ON meetings(project_id, id);
        -- Persistent databases created on earlier builds get these indexes
        -- automatically, without destroying or migrating project records.
        CREATE INDEX IF NOT EXISTS idx_foundry_tasks_project ON tasks(project_id, id);
        CREATE INDEX IF NOT EXISTS idx_foundry_tasks_parent ON tasks(parent_id, state);
        CREATE INDEX IF NOT EXISTS idx_foundry_issues_project ON issues(project_id, id);
        CREATE INDEX IF NOT EXISTS idx_foundry_events_project ON events(project_id, id);
        CREATE INDEX IF NOT EXISTS idx_foundry_tests_project_kind ON test_runs(project_id, kind, id);
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
            meeting = self.conn.execute(
                "SELECT decisions FROM meetings WHERE project_id=? ORDER BY id DESC LIMIT 1",
                (project["id"],)).fetchone()
            recent_tests = self.conn.execute(
                "SELECT kind,status,report FROM test_runs WHERE project_id=? "
                "AND kind IN ('docker-unit','docker-gui') ORDER BY id DESC LIMIT 2",
                (project["id"],)
            ).fetchall()
            test_context = []
            for item in recent_tests:
                try:
                    report = json.loads(item["report"])
                except (ValueError, TypeError):
                    report = {}
                if not isinstance(report, dict):
                    report = {}
                test_context.append(
                    f"{item['kind']} status={item['status']} "
                    f"reason={str(report.get('reason', ''))[:300]} "
                    f"output={str(report.get('output', ''))[-800:]}"
                )
            return {"project": project, "tasks": tasks, "issues": issues,
                    "meeting_context": meeting["decisions"] if meeting else "",
                    "test_context": "\n".join(test_context)[:2200]}

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
            project_folder = None
            folder_created = False
            try:
                # Keep the project row and initial workspace creation in a
                # single transaction. A disk/path error cannot leave a phantom
                # app in the user's project list.
                with self.conn:
                    cur = self.conn.execute(
                        "INSERT INTO projects(title,brief,created_at,updated_at) VALUES(?,?,?,?)",
                        (title, brief, created, created))
                    pid = cur.lastrowid
                    folder = f"app-{pid:04d}-{safe_slug(title)}"
                    self.conn.execute("UPDATE projects SET folder=? WHERE id=?", (folder, pid))
                    for name, role, detail in PROJECT_TEMPLATE:
                        self._new_task(pid, title=name, brief=detail, role=role)
                    self._event(pid, None, "created", "Project created with five default review stages")
                    if self.db_path != ":memory:":
                        project_folder = self.project_folder(pid)
                        # IDs are unique; never adopt or overwrite an existing
                        # folder even if it looks like a legitimate project.
                        project_folder.mkdir(parents=True, exist_ok=False)
                        folder_created = True
                        with (project_folder / "PROJECT.md").open("x", encoding="utf-8") as output:
                            output.write("# " + title + "\n\n" + brief + "\n")
            except Exception:
                if folder_created and project_folder is not None:
                    (project_folder / "PROJECT.md").unlink(missing_ok=True)
                    try:
                        project_folder.rmdir()
                    except OSError:
                        pass  # Never remove unexpected user files.
                raise
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
            if parent["state"] != "todo":
                raise ValueError("Subtasks may only be added to a not-started parent.")
            if self.conn.execute("SELECT count(*) FROM tasks WHERE project_id=?", (parent["project_id"],)).fetchone()[0] >= MAX_TASKS:
                raise ValueError("Project task limit reached.")
            with self.conn:
                new_id = self._new_task(parent["project_id"], title=title, brief=brief, role=role, parent_id=parent["id"])
                self._event(parent["project_id"], new_id, "subtask", "Assigned to " + role)
            return self._task(new_id)

    def add_subtasks(self, parent_id, proposals):
        """Atomically store a user-approved manager subtask proposal."""
        if not isinstance(proposals, list) or not 1 <= len(proposals) <= 8:
            raise ValueError("A manager proposal requires 1 to 8 subtasks.")
        approved = []
        for entry in proposals:
            if not isinstance(entry, dict) or set(entry) != {"title", "brief", "role"}:
                raise ValueError("Every subtask must have title, brief and role.")
            role = entry["role"]
            if role not in ROLES:
                raise ValueError("Invalid worker role in manager proposal.")
            approved.append({
                "title": clean_text(entry["title"], 120, name="Task title"),
                "brief": clean_text(entry["brief"], 5000, name="Task brief"),
                "role": role,
            })
        if len({item["title"].casefold() for item in approved}) != len(approved):
            raise ValueError("Manager plan contains duplicate subtask names.")
        with self.lock:
            parent = self._task(parent_id)
            if parent["parent_id"] is not None or parent["state"] != "todo":
                raise ValueError("Choose a not-started top-level task for this plan.")
            if self._project(parent["project_id"])["state"] == "approved":
                raise ValueError("Reopen the approved project first.")
            count = self.conn.execute(
                "SELECT count(*) FROM tasks WHERE project_id=?", (parent["project_id"],)
            ).fetchone()[0]
            if count + len(approved) > MAX_TASKS:
                raise ValueError("Project task limit would be exceeded.")
            with self.conn:
                ids = []
                for entry in approved:
                    ident = self._new_task(parent["project_id"], parent_id=parent["id"], **entry)
                    ids.append(ident)
                    self._event(parent["project_id"], ident, "manager-plan",
                                "Owner approved role " + entry["role"])
            return [self._task(tid) for tid in ids]

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
            if self._project(item["project_id"])["state"] == "approved":
                raise ValueError("Reopen the approved project before assigning fixes.")
            if self.conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE project_id=?", (item["project_id"],)
            ).fetchone()[0] >= MAX_TASKS:
                raise ValueError("Project task limit reached; cannot assign another fix.")
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
            if issue["state"] != "in_progress":
                raise ValueError("Only assigned, open issues can be closed.")
            if self._project(issue["project_id"])["state"] == "approved":
                raise ValueError("Reopen the approved project before resolving an issue.")
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

    def save_meeting(self, project_id, meeting):
        """Persist only an actual completed six-speaker meeting, never fake chat."""
        from apollo_foundry_meetings import SPECIALISTS
        if not isinstance(meeting, dict):
            raise ValueError("Invalid meeting")
        turns = meeting.get("turns")
        if not isinstance(turns, list) or len(turns) != 6:
            raise ValueError("A completed meeting needs all six model responses")
        if [x.get("role") for x in turns if isinstance(x, dict)] != [*SPECIALISTS, "manager"]:
            raise ValueError("Meeting roles are missing or out of order")
        for item in turns:
            if not isinstance(item.get("message"), str) or not 1 <= len(item["message"]) <= 3500:
                raise ValueError("Invalid meeting response")
        decisions = clean_text(meeting.get("decisions"), 3500, name="Meeting decisions")
        if decisions != turns[-1]["message"]:
            raise ValueError("Only the manager's actual response may be saved as decisions")
        topic = clean_text(meeting.get("topic"), 220, name="Meeting topic")
        with self.lock:
            self._project(project_id)
            with self.conn:
                cur = self.conn.execute(
                    "INSERT INTO meetings(project_id,topic,turns,decisions,created_at) "
                    "VALUES(?,?,?,?,?)",
                    (int(project_id), topic, json.dumps(turns), decisions, utcnow()))
                self._event(int(project_id), None, "meeting",
                            f"Team meeting #{cur.lastrowid}: {topic}; six real responses recorded")
            return cur.lastrowid

    def meetings(self, project_id, limit=10):
        with self.lock:
            self._project(project_id)
            rows = self.conn.execute(
                "SELECT * FROM meetings WHERE project_id=? ORDER BY id DESC LIMIT ?",
                (int(project_id), max(1, min(30, int(limit)))))
            return [{**dict(row), "turns": json.loads(row["turns"])} for row in rows]

    def record_handoff(self, project_id, from_role, to_role, summary, task_id=None):
        """A factual dispatch/handback event, rather than a fabricated model message."""
        if from_role not in ROLES or to_role not in ROLES:
            raise ValueError("Invalid handoff role")
        summary = clean_text(summary, 600, name="Handoff summary")
        with self.lock:
            self._project(project_id)
            if task_id is not None and self._task(task_id)["project_id"] != int(project_id):
                raise ValueError("Cross-project handoff")
            with self.conn:
                self._event(int(project_id), task_id, "handoff",
                            f"{from_role} → {to_role}: {summary}")
        return True

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

    def project_folder(self, project_id):
        """Resolve only an ID-derived local app folder, never arbitrary DB paths."""
        project = self._project(project_id)
        folder = project["folder"]
        if not re.fullmatch(r"app-\d{4,}-[a-z0-9-]{1,42}", folder):
            raise ValueError("Invalid saved project path; refusing filesystem access.")
        base = self.root / "workspace" / "app_development"
        if any(path.is_symlink() for path in (self.root / "workspace", base, base / folder)):
            raise ValueError("Symlinked project folder is not allowed.")
        target = (base / folder).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("Project path escapes Apollo's private workspace.")
        return target

    def create_starter_ui(self, project_id):
        """Create a tiny trusted, inspectable sample app. Never overwrite files.

        No app is launched. This is a source template to test UI contracts,
        not an autonomous code writer or an execution sandbox.
        """
        with self.lock:
            project = self._project(project_id)
            if project["state"] == "approved":
                raise ValueError("Reopen the project before adding a starter app.")
            folder = self.project_folder(project_id)
            folder.mkdir(parents=True, exist_ok=True)
            sample = {
                "service.py": (
                    "class AppService:\n"
                    "    def __init__(self):\n"
                    "        self.saved = 0\n\n"
                    "    def save(self):\n"
                    "        self.saved += 1\n"
                    "        return self.saved\n"
                ),
                "ui.py": (
                    "from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton\n"
                    "from service import AppService\n\n"
                    "class AppWindow(QWidget):\n"
                    "    def __init__(self, backend=None):\n"
                    "        super().__init__()\n"
                    "        self.backend = backend or AppService()\n"
                    "        self.setWindowTitle('Apollo Foundry Starter App')\n"
                    "        layout = QVBoxLayout(self)\n"
                    "        self.message = QLabel('Ready to save')\n"
                    "        self.save_button = QPushButton('Save')\n"
                    "        self.save_button.clicked.connect(self.on_save)\n"
                    "        layout.addWidget(self.message)\n"
                    "        layout.addWidget(self.save_button)\n\n"
                    "    def on_save(self):\n"
                    "        value = self.backend.save()\n"
                    "        self.message.setText(f'Saved {value} time(s)')\n"
                ),
                "launch.py": (
                    "import sys\n"
                    "from PySide6.QtWidgets import QApplication\n"
                    "from ui import AppWindow\n\n"
                    "if __name__ == '__main__':\n"
                    "    app = QApplication(sys.argv)\n"
                    "    window = AppWindow()\n"
                    "    window.show()\n"
                    "    sys.exit(app.exec())\n"
                ),
                "tests/test_ui.py": (
                    "import unittest\n"
                    "from PySide6.QtWidgets import QApplication\n"
                    "from ui import AppWindow\n\n"
                    "class StarterUITests(unittest.TestCase):\n"
                    "    def test_save_button_reaches_backend_and_updates_label(self):\n"
                    "        app = QApplication.instance() or QApplication([])\n"
                    "        window = AppWindow()\n"
                    "        try:\n"
                    "            window.save_button.click()\n"
                    "            self.assertEqual(window.backend.saved, 1)\n"
                    "            self.assertEqual(window.message.text(), 'Saved 1 time(s)')\n"
                    "        finally:\n"
                    "            window.close()\n"
                ),
                "foundry.json": json.dumps({
                    "schema_version": 1, "ui": {
                        "file": "ui.py", "class": "AppWindow",
                        "bindings": [{
                            "widget": "save_button", "signal": "clicked",
                            "handler": "on_save", "backend_attribute": "backend",
                            "backend_file": "service.py", "backend_class": "AppService",
                            "backend_method": "save",
                        }],
                    },
                }, indent=2) + "\n",
            }
            # Refuse partial overwrites and user-created symlinks.
            if any((folder / name).exists() or (folder / name).is_symlink() for name in sample):
                raise FileExistsError("Starter UI files already exist. Existing project code was not changed.")
            created = []
            try:
                for name, content in sample.items():
                    dest = folder / name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with dest.open("x", encoding="utf-8", newline="\n") as output:
                        output.write(content)
                    created.append(dest)
            except OSError:
                for dest in created:
                    dest.unlink(missing_ok=True)
                raise
            with self.conn:
                self._event(project["id"], None, "starter-created",
                            "Added trusted sample UI, backend, click-through test and launcher; nothing executed")
            return {"project_id": project["id"], "files": list(sample), "executed": False,
                    "note": "Starter source created locally. Run static checks, then test real GUI manually."}

    def run_checks(self, project_id):
        """User-triggered, static only; no generated project code executes."""
        from apollo_foundry_checks import scan_project
        with self.lock:
            project = self._project(project_id)
            report = scan_project(self.project_folder(project_id))
            with self.conn:
                self.conn.execute(
                    "INSERT INTO test_runs(project_id,status,kind,report,created_at) VALUES(?,?,?,?,?)",
                    (project["id"], report["status"], report["kind"],
                     json.dumps(report, ensure_ascii=False), utcnow())
                )
                self._event(project["id"], None, "test",
                            f"Static UI check: {report['status']} (not a runtime GUI test)")
                self.conn.execute(
                    "DELETE FROM test_runs WHERE project_id=? AND kind=? AND id NOT IN "
                    "(SELECT id FROM test_runs WHERE project_id=? AND kind=? ORDER BY id DESC LIMIT 30)",
                    (project["id"], report["kind"], project["id"], report["kind"]),
                )
            return report

    def check_history(self, project_id, limit=10):
        with self.lock:
            self._project(project_id)
            rows = self.conn.execute(
                "SELECT id,status,kind,created_at,report FROM test_runs "
                "WHERE project_id=? AND kind='static-ui-contract' ORDER BY id DESC LIMIT ?",
                (int(project_id), min(30, max(1, int(limit)))),
            ).fetchall()
            return [
                {**{k: row[k] for k in ("id", "status", "kind", "created_at")},
                 "report": json.loads(row["report"])}
                for row in rows
            ]

    def run_sandbox_tests(self, project_id, kind, *, docker_bin=None):
        """Owner-initiated container execution, with persistent auditable report."""
        from apollo_foundry_sandbox import run_sandbox
        if kind not in ("unit", "gui"):
            raise ValueError("Sandbox test type must be unit or gui.")
        with self.lock:
            project = self._project(project_id)
            folder = self.project_folder(project_id)
        # Do NOT keep the DB mutex through a long-running Docker job.
        try:
            report = run_sandbox(folder, kind, docker_bin=docker_bin)
        except (OSError, ValueError, UnicodeError) as error:
            # An unsafe/missing project file should still leave an auditable
            # failed attempt. Never silently report a rejected run as PASS.
            from datetime import datetime, timezone
            from apollo_foundry_sandbox import SANDBOX_KINDS
            report = {
                "kind": f"docker-{kind}", "phase": "Foundry Sandbox",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "executed_project_code": False, "passed_ui_interactions": False,
                "status": "refused", "output": "",
                "reason": f"Input check refused execution: {type(error).__name__}: {str(error)[:350]}",
                "image": SANDBOX_KINDS[kind],
            }
        with self.lock, self.conn:
            self.conn.execute(
                "INSERT INTO test_runs(project_id,status,kind,report,created_at) VALUES(?,?,?,?,?)",
                (project["id"], report["status"], report["kind"],
                 json.dumps(report, ensure_ascii=False), utcnow()),
            )
            self._event(project["id"], None, "sandbox",
                        f"Docker {kind} test: {report['status']} (report saved)")
            self.conn.execute(
                "DELETE FROM test_runs WHERE project_id=? AND kind=? AND id NOT IN "
                "(SELECT id FROM test_runs WHERE project_id=? AND kind=? ORDER BY id DESC LIMIT 30)",
                (project["id"], report["kind"], project["id"], report["kind"]),
            )
        return report

    def sandbox_history(self, project_id, limit=10):
        with self.lock:
            self._project(project_id)
            rows = self.conn.execute(
                "SELECT id,status,kind,created_at,report FROM test_runs "
                "WHERE project_id=? AND kind IN ('docker-unit','docker-gui') "
                "ORDER BY id DESC LIMIT ?",
                (int(project_id), min(30, max(1, int(limit)))),
            ).fetchall()
            return [
                {**{k: row[k] for k in ("id", "status", "kind", "created_at")},
                 "report": json.loads(row["report"])}
                for row in rows
            ]

    def request_change(self, project_id, instructions, task_id=None):
        """Queue 'change this' as a reviewable issue and worker task only."""
        instructions = clean_text(instructions, 5000, name="Requested change")
        with self.lock:
            project = self._project(project_id)
            if project["state"] == "approved":
                raise ValueError("Reopen the approved project in the UI before requesting changes.")
            if self.conn.execute(
                "SELECT count(*) FROM tasks WHERE project_id=?", (project["id"],)
            ).fetchone()[0] >= MAX_TASKS:
                raise ValueError("Task limit reached; cannot queue the change.")
            target = None
            if task_id is not None:
                target = self._task(task_id)
                if target["project_id"] != project["id"]:
                    raise ValueError("Selected task does not belong to this project.")
            focus = f" to {target['title']}" if target else ""
            title = ("Change" + focus)[:120]
            brief = (f"Owner requested a revision{focus}.\n"
                     f"Original task ID: {target['id'] if target else 'project-wide'}\n"
                     f"Change requested:\n{instructions}\n"
                     "Prepare a proposed fix and explain what to test. "
                     "Do not claim code was executed or any test passed.")
            now = utcnow()
            with self.conn:
                issue_cur = self.conn.execute(
                    "INSERT INTO issues(project_id,title,details,state,created_at,updated_at) "
                    "VALUES(?,?,?,'open',?,?)",
                    (project["id"], title, instructions, now, now),
                )
                iid = issue_cur.lastrowid
                tid = self._new_task(
                    project["id"], title=("Revise" + focus)[:120],
                    brief=brief, role="implementer",
                )
                self.conn.execute(
                    "UPDATE issues SET state='in_progress',assigned_task=?,updated_at=? WHERE id=?",
                    (tid, now, iid),
                )
                self._event(project["id"], tid, "change-request",
                            f"Review requested for task #{target['id']}" if target else "Project-wide revision requested")
            return {"project_id": project["id"], "issue_id": iid, "task_id": tid,
                    "state": "queued_for_human_review", "code_changed": False,
                    "tests_passed": False}

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
