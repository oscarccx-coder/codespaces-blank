"""Apollo Coding Team candidate: human-reviewed, turn-based agent task tracking.

This module deliberately does NOT execute generated code, run shell commands,
install modules or approve its own output. Approval exists only as a UI callback
after all roles have submitted review evidence.
"""
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

ROLES = ("architect", "implementer", "tester", "reviewer", "integrator")


def now():
    return datetime.now(timezone.utc).isoformat()


class Module:
    def __init__(self, context=None):
        context = context or {}
        self.validation = bool(context.get("validation", False))
        self.base = Path(context.get("base_dir", ".")).resolve()
        if self.validation:
            self.db_path = ":memory:"
        else:
            folder = self.base / "storage" / "databases"
            folder.mkdir(parents=True, exist_ok=True)
            self.db_path = str(folder / "coding_team.db")
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL, brief TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'working',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                approved_at TEXT
            );
            CREATE TABLE IF NOT EXISTS assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT, team_id INTEGER NOT NULL,
                position INTEGER NOT NULL, role TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'pending',
                iteration INTEGER NOT NULL DEFAULT 0,
                submission TEXT NOT NULL DEFAULT '',
                evidence TEXT NOT NULL DEFAULT '',
                review TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                FOREIGN KEY(team_id) REFERENCES teams(id)
            );
        """)
        self.conn.commit()

    def tools(self):
        integer = {"type": "integer"}
        string = {"type": "string"}
        return [
            {"name":"create_coding_team", "description":"Plan a safe five-role coding team; this never executes code.",
             "parameters":{"type":"object","properties":{"title":string,"brief":string},
                           "required":["title","brief"]}},
            {"name":"coding_team_status","description":"Show team assignments and evidence status.",
             "parameters":{"type":"object","properties":{"team_id":integer},"required":["team_id"]}},
            {"name":"next_coding_assignment","description":"Return the next assignable role.",
             "parameters":{"type":"object","properties":{"team_id":integer},"required":["team_id"]}},
            {"name":"start_coding_assignment","description":"Start the next role's turn (no code execution).",
             "parameters":{"type":"object","properties":{"assignment_id":integer},"required":["assignment_id"]}},
            {"name":"submit_coding_assignment","description":"Submit result and evidence reference for manager review.",
             "parameters":{"type":"object","properties":{"assignment_id":integer,"submission":string,"evidence":string},
                           "required":["assignment_id","submission","evidence"]}},
            {"name":"review_coding_assignment","description":"Record a review, accept or send back for another turn. Does not imply tests actually ran.",
             "parameters":{"type":"object","properties":{"assignment_id":integer,"accepted":{"type":"boolean"},
                                                      "notes":string},"required":["assignment_id","accepted","notes"]}},
            {"name":"list_coding_teams","description":"List recent coding-team projects.",
             "parameters":{"type":"object","properties":{}}},
        ]

    def _assignment(self, assignment_id):
        row = self.conn.execute("SELECT * FROM assignments WHERE id=?",
                                (int(assignment_id),)).fetchone()
        if row is None:
            raise KeyError("Assignment not found.")
        return row

    def status(self, team_id):
        with self.lock:
            row = self.conn.execute("SELECT * FROM teams WHERE id=?",
                                    (int(team_id),)).fetchone()
            if row is None:
                raise KeyError("Coding team not found.")
            assignments = self.conn.execute(
                "SELECT * FROM assignments WHERE team_id=? ORDER BY position",
                (int(team_id),)
            ).fetchall()
            return {"team": dict(row), "assignments": [dict(q) for q in assignments]}

    def _next(self, team_id):
        data = self.status(team_id)
        if data["team"]["state"] != "working":
            return None
        for item in data["assignments"]:
            if item["state"] != "accepted":
                return item
        return None

    def run(self, action, arguments):
        x = arguments or {}
        with self.lock:
            if action == "create_coding_team":
                title = " ".join(str(x.get("title", "")).split())[:120]
                brief = str(x.get("brief", "")).strip()[:4000]
                if not title or not brief:
                    raise ValueError("Title and project brief are required.")
                timestamp = now()
                cur = self.conn.execute(
                    "INSERT INTO teams(title,brief,created_at,updated_at) VALUES(?,?,?,?)",
                    (title, brief, timestamp, timestamp)
                )
                team_id = cur.lastrowid
                for position, role in enumerate(ROLES, 1):
                    self.conn.execute(
                        "INSERT INTO assignments(team_id,position,role,updated_at) VALUES(?,?,?,?)",
                        (team_id, position, role, timestamp)
                    )
                self.conn.commit()
                return self.status(team_id)
            if action == "coding_team_status":
                return self.status(x["team_id"])
            if action == "list_coding_teams":
                rows = self.conn.execute(
                    "SELECT * FROM teams ORDER BY id DESC LIMIT 50"
                ).fetchall()
                return {"teams": [dict(row) for row in rows]}
            if action == "next_coding_assignment":
                return {"assignment": self._next(x["team_id"])}
            if action == "start_coding_assignment":
                row = self._assignment(x["assignment_id"])
                next_step = self._next(row["team_id"])
                if next_step is None or next_step["id"] != row["id"] or row["state"] != "pending":
                    raise ValueError("Assignments must run in manager-approved order.")
                self.conn.execute(
                    "UPDATE assignments SET state='running',updated_at=? WHERE id=?",
                    (now(), row["id"])
                )
                self.conn.commit()
                return {"started": True, "assignment_id": row["id"], "role": row["role"]}
            if action == "submit_coding_assignment":
                row = self._assignment(x["assignment_id"])
                if row["state"] != "running":
                    raise ValueError("Start this assignment before submitting.")
                submission = str(x.get("submission", "")).strip()[:8000]
                evidence = str(x.get("evidence", "")).strip()[:2000]
                if not submission or not evidence:
                    raise ValueError("Submission and evidence reference are required.")
                self.conn.execute(
                    "UPDATE assignments SET state='submitted',submission=?,evidence=?,"
                    "iteration=iteration+1,updated_at=? WHERE id=?",
                    (submission, evidence, now(), row["id"])
                )
                self.conn.commit()
                return {"submitted": True, "assignment_id": row["id"], "review_required": True}
            if action == "review_coding_assignment":
                row = self._assignment(x["assignment_id"])
                if row["state"] != "submitted":
                    raise ValueError("Only submitted work can be reviewed.")
                notes = str(x.get("notes", "")).strip()[:4000]
                if not notes:
                    raise ValueError("Review notes are required.")
                accepted = x.get("accepted") is True
                self.conn.execute(
                    "UPDATE assignments SET state=?,review=?,updated_at=? WHERE id=?",
                    ("accepted" if accepted else "pending", notes, now(), row["id"])
                )
                self.conn.commit()
                return {"reviewed": True, "accepted": accepted, "assignment_id": row["id"],
                        "requires_user_approval": True}
        raise KeyError(action)

    def approve_release_from_ui(self, team_id):
        """Never exposed as an AI callable tool. Only explicit UI action may call."""
        with self.lock:
            state = self.status(team_id)
            if state["team"]["state"] != "working":
                raise ValueError("Team is already closed.")
            if not all(x["state"] == "accepted" for x in state["assignments"]):
                raise ValueError("Every role must be accepted before human approval.")
            self.conn.execute(
                "UPDATE teams SET state='approved',approved_at=?,updated_at=? WHERE id=?",
                (now(), now(), int(team_id))
            )
            self.conn.commit()
            return {"approved": True, "team_id": int(team_id),
                    "note": "Workflow approved. No code has been installed or executed."}

    def self_test(self):
        if not self.validation:
            # Production self-test must not insert synthetic tasks in user storage.
            return "Coding Team schema ready. No autonomous core edits."
        team = self.run("create_coding_team", {"title": "Test", "brief": "Synthetic"})
        aid = team["assignments"][0]["id"]
        try:
            self.run("submit_coding_assignment", {"assignment_id": aid,
                                                  "submission": "test", "evidence": "test"})
        except ValueError:
            pass
        else:
            raise AssertionError("Submission before start was wrongly allowed.")
        self.run("start_coding_assignment", {"assignment_id": aid})
        self.run("submit_coding_assignment", {"assignment_id": aid,
                                              "submission": "design", "evidence": "review note"})
        self.run("review_coding_assignment", {"assignment_id": aid,
                                              "accepted": True, "notes": "reviewed"})
        assert self._next(team["team"]["id"])["role"] == "implementer"
        try:
            self.approve_release_from_ui(team["team"]["id"])
        except ValueError:
            pass
        else:
            raise AssertionError("Early approval was wrongly allowed.")
        return "Role ordering, submission review and approval guard passed."

    def build_ui(self, parent=None, ui_context=None):
        from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QListWidget,
                                       QPushButton, QMessageBox, QInputDialog)
        from PySide6.QtCore import Qt
        page = QWidget(parent)
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("Coding Team: reviewable specialist turns"))
        layout.addWidget(QLabel("This planner does NOT run, install or ship generated code."))
        teams = QListWidget()
        layout.addWidget(teams, 1)
        details = QLabel("Select a team to see its assignments.")
        details.setWordWrap(True)
        layout.addWidget(details)
        def refresh():
            teams.clear()
            for item in self.run("list_coding_teams", {})["teams"]:
                from PySide6.QtWidgets import QListWidgetItem
                row = QListWidgetItem(f"#{item['id']} {item['title']} [{item['state']}]")
                row.setData(Qt.UserRole, item["id"])
                teams.addItem(row)
        def selected():
            row = teams.currentItem()
            return row.data(Qt.UserRole) if row else None
        def describe():
            ident = selected()
            if ident is None: return
            state = self.status(ident)
            details.setText("\n".join(
                f"{item['position']}. {item['role']}: {item['state']}"
                for item in state["assignments"]
            ))
        def create():
            title, ok = QInputDialog.getText(page, "New Coding Team", "Project name:")
            if not ok or not title.strip(): return
            brief, ok = QInputDialog.getMultiLineText(page, "New Coding Team", "Project goal:")
            if not ok or not brief.strip(): return
            self.run("create_coding_team", {"title": title, "brief": brief})
            refresh()
        def approve():
            ident = selected()
            if ident is None: return
            if QMessageBox.question(page, "Approve Workflow",
                 "Approve these reviewed role results? This does not install any code.",
                 QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            try:
                self.approve_release_from_ui(ident)
                refresh()
            except (ValueError, KeyError) as exc:
                QMessageBox.warning(page, "Cannot approve", str(exc))
        add = QPushButton("Create Team")
        approve_btn = QPushButton("Approve Reviewed Workflow")
        add.clicked.connect(create)
        approve_btn.clicked.connect(approve)
        teams.itemSelectionChanged.connect(describe)
        layout.addWidget(add)
        layout.addWidget(approve_btn)
        refresh()
        return page

    def close(self):
        with self.lock:
            self.conn.close()
