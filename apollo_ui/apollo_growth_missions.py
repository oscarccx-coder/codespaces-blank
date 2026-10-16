"""Opt-in growth missions: concrete deliverables through the existing Foundry.

A normal-chat request may create an OFFER. Only an explicit follow-up command
starts a project and spends Ollama compute. Generated code lives solely in
Foundry's private project folder and requires independent Docker/runtime tests
and human review before any external delivery or commercial action.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import time
import uuid

OFFER_LIFETIME = 24 * 60 * 60
CHOOSE = re.compile(
    r"^\s*(?:yes[,.]?\s*)?(?:begin|start|build|go ahead with)\s+"
    r"(?:the\s+)?(?:apollo\s+(?:growth\s+)?project\s+|option\s+|project\s+)"
    r"([1-3])\s*[.!]?\s*$", re.I,
)
PAUSE = re.compile(r"^\s*(?:pause|stop)\s+(?:the\s+)?apollo\s+(?:growth\s+)?project\s*[.!]?\s*$", re.I)
CONTINUE = re.compile(r"^\s*(?:continue|resume|retry)\s+(?:the\s+)?apollo\s+(?:growth\s+)?project\s*[.!]?\s*$", re.I)
STATUS = re.compile(
    r"^\s*(?:status(?:\s+of)?|progress(?:\s+of)?|show(?:\s+me)?\s+progress(?:\s+of)?)"
    r"\s+(?:the\s+)?(?:apollo\s+)?(?:growth\s+)?project\s*[?!]?\s*$", re.I,
)

# These are implementable local software demos, not invented clients, jobs,
# prices, market demand, projected revenue or automatic external publishing.
PROJECTS = (
    {
        "title": "Hospitality Pre-order Desktop Tool",
        "category": "Business automation",
        "deliverable": "Offline Windows-friendly Python/PySide6 sample app for meal pre-orders, steak cooking choices, allergy notes and CSV kitchen summaries.",
        "buyer": "Independent hospitality venues after independent demand research",
        "scope": "Use fictional data only. Build a working offline pre-order app, data validation, safe export, tests and a clear user guide. No personal data collection or cloud sync.",
        "acceptance": "Working local UI connected to tested logic; sample orders, correct totals, CSV export, no real guests; Foundry static and sandbox GUI tests.",
    },
    {
        "title": "Small Business Quote Builder",
        "category": "Business automation",
        "deliverable": "Offline quote and invoice-preview app that calculates totals, stores draft quotes locally and exports a clearly labelled PDF/CSV preview.",
        "buyer": "Small service businesses after independent demand research",
        "scope": "Build an offline Python/PySide6 prototype with configurable rates, tax rules and example client data, documentation and tests. No billing, real payments or sending messages.",
        "acceptance": "Accurate price calculations, reproducible unit tests, fictional customer examples, local-only storage and separate human approval before any real invoice.",
    },
    {
        "title": "Stock and Reorder Tracker",
        "category": "Business automation",
        "deliverable": "Local desktop stock inventory tracker with low-stock alerts, CSV import/export, editable reorder thresholds and tested example inventory.",
        "buyer": "Independent retailers and restaurants after independent demand research",
        "scope": "Build an offline Python/PySide6 prototype with stock add/remove controls, deterministic business rules and test fixtures. Never order products or connect to supplier accounts.",
        "acceptance": "Working UI, unit-tested stock arithmetic, robust validation and CSV handling, documented demo, no purchasing or external network calls.",
    },
)


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def intent(text):
    """Return the only permitted normal chat commands; no fuzzy assent."""
    t = str(text or "")[:300]
    choose = CHOOSE.fullmatch(t)
    if choose:
        return ("begin", int(choose.group(1)))
    if PAUSE.fullmatch(t):
        return ("pause", None)
    if CONTINUE.fullmatch(t):
        return ("continue", None)
    if STATUS.fullmatch(t):
        return ("status", None)
    return None


class GrowthMissionStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        database = self.root / "storage" / "databases"
        database.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(database / "apollo_growth_missions.db"), timeout=15)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS offers(
                id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
                expiry REAL NOT NULL, state TEXT NOT NULL DEFAULT 'OFFERED',
                option INTEGER, mission_id TEXT
            );
            CREATE TABLE IF NOT EXISTS missions(
                id TEXT PRIMARY KEY, offer_id TEXT UNIQUE NOT NULL,
                option INTEGER NOT NULL, title TEXT NOT NULL,
                state TEXT NOT NULL, project_id INTEGER, work_id INTEGER,
                task_id INTEGER, output TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS mission_events(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mission_id TEXT NOT NULL, event TEXT NOT NULL,
                detail TEXT NOT NULL, at TEXT NOT NULL
            );
        """)
        self.db.commit()

    def close(self):
        self.db.close()

    def offer(self):
        """Offer choices only. No Growth Lab proposal or Foundry side effects."""
        offer_id = uuid.uuid4().hex
        with self.db:
            self.db.execute(
                "INSERT INTO offers(id,created_at,expiry,state) VALUES(?,?,?,'OFFERED')",
                (offer_id, utc(), time.time() + OFFER_LIFETIME),
            )
            # Expired unused offers can be discarded, but never mission evidence.
            self.db.execute(
                "DELETE FROM offers WHERE state='OFFERED' AND expiry<?",
                (time.time() - 7 * 86400,),
            )
        return self.offer_text()

    def offer_text(self):
        lines = [
            "I can **build a product prototype**, test it in Foundry and prepare "
            "a portfolio/demo that you could choose to offer to paying customers.",
            "I cannot promise revenue, find real customers without research, "
            "take payments, contact people or buy hardware without your approval.",
            "",
            "**Three projects I can actually start building:**",
        ]
        for i, project in enumerate(PROJECTS, 1):
            lines.append(f"{i}. **{project['title']}**: {project['deliverable']}")
        lines.extend([
            "",
            "**To start:** reply **begin Apollo project 1**, "
            "**begin Apollo project 2**, or **begin Apollo project 3**.",
            "I'll create a draft opportunity in Growth Lab, open a matching Foundry "
            "project, and generate the first implementation draft using local Ollama. "
            "I'll report the files and static checks, including any failures.",
            "Then use Foundry's **Start Continuous Session** for repeated agent work, "
            "meetings and isolated Docker testing. That session needs its own "
            "explicit authorization and working Docker; projects and external "
            "deliveries are never automatically approved.",
            "You can ask **status Apollo project**, **pause Apollo project** "
            "or **continue Apollo project** for a bounded next step.",
        ])
        return "\n".join(lines)

    def _latest(self):
        return self.db.execute(
            "SELECT * FROM missions ORDER BY created_at DESC, rowid DESC LIMIT 1"
        ).fetchone()

    def _event(self, identifier, event, detail=""):
        self.db.execute(
            "INSERT INTO mission_events(mission_id,event,detail,at) VALUES(?,?,?,?)",
            (identifier, event, str(detail)[:850], utc()),
        )

    def begin(self, choice, *, owner_confirmed=False):
        if owner_confirmed is not True:
            raise PermissionError("Explicit owner confirmation is required to begin an Apollo growth project.")
        if type(choice) is not int or choice not in range(1, len(PROJECTS)+1):
            raise ValueError("Choose project 1, 2 or 3.")
        # Reserve the most recent eligible offer exactly once. No concurrent
        # confirmation may create two projects from the same offer.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            offer = self.db.execute(
                "SELECT * FROM offers WHERE state='OFFERED' AND expiry>=?"
                " ORDER BY created_at DESC,rowid DESC LIMIT 1", (time.time(),)
            ).fetchone()
            if not offer:
                self.db.rollback()
                raise PermissionError(
                    "No pending Apollo growth offer. Ask me how I can earn upgrade money first."
                )
            project = PROJECTS[choice-1]
            ident = uuid.uuid4().hex
            self.db.execute(
                "INSERT INTO missions(id,offer_id,option,title,state,created_at,updated_at)"
                " VALUES(?,?,?,?,?,?,?)",
                (ident, offer["id"], choice, project["title"], "PREPARING", utc(), utc()),
            )
            self.db.execute(
                "UPDATE offers SET state='ACCEPTED',option=?,mission_id=? WHERE id=?",
                (choice, ident, offer["id"]),
            )
            self._event(ident, "owner_authorized", f"Selected project {choice}; local demo only")
            self.db.commit()
        except Exception:
            if self.db.in_transaction:
                self.db.rollback()
            raise

        from apollo_project_studio import StudioStore
        from apollo_growth import GrowthStore
        studio = StudioStore(self.root)
        growth = GrowthStore(self.root)
        try:
            brief = (
                f"PRODUCT DEMO; OWNER-APPROVED SCOPE, NO EXTERNAL ACTIONS.\n"
                f"Intended deliverable: {project['deliverable']}\n"
                f"Target user hypothesis: {project['buyer']}. This is NOT verified market demand.\n"
                f"Implementation: {project['scope']}\n"
                f"Acceptance criteria: {project['acceptance']}\n"
                "Foundry may draft project-local source, run static checks, and, "
                "after separately authorised Docker isolation, run tests and review. "
                "Never access real client data, modify Apollo core, publish content, "
                "send messages, take payments, spend money or install upgrades."
            )
            created = studio.add_project(project["title"], brief)
            pid = created["project"]["id"]
            with self.db:
                self.db.execute(
                    "UPDATE missions SET project_id=?, state='PROJECT_CREATED', updated_at=? WHERE id=?",
                    (pid, utc(), ident),
                )
                self._event(ident, "foundry_project_created", f"Project {pid}; initial review stages queued")
            proposed = growth.propose(
                project["title"], project["deliverable"] + " " + project["scope"],
                project["category"], "0",
            )
            with self.db:
                self.db.execute(
                    "UPDATE missions SET work_id=?,state='READY_TO_DRAFT',updated_at=? WHERE id=?",
                    (proposed["id"], utc(), ident),
                )
                self._event(ident, "growth_draft_created",
                            f"Growth Lab draft {proposed['id']}; zero earnings claimed")
        except Exception as exc:
            with self.db:
                self.db.execute(
                    "UPDATE missions SET state='BLOCKED',error=?,updated_at=? WHERE id=?",
                    (str(exc)[:800], utc(), ident),
                )
                self._event(ident, "preparation_failed", str(exc)[:600])
            raise RuntimeError(
                f"Mission {ident[:8]} was authorised but preparation failed: "
                f"{type(exc).__name__}: {exc}. Inspect Foundry/Growth Lab; "
                "existing partial records have not been deleted."
            ) from exc
        finally:
            studio.close()
            growth.close()
        return self.snapshot()

    def snapshot(self):
        item = self._latest()
        if not item:
            return {"exists": False, "message": "No Apollo growth project has started."}
        result = dict(item)
        events = self.db.execute(
            "SELECT event,detail,at FROM mission_events WHERE mission_id=?"
            " ORDER BY id DESC LIMIT 12", (item["id"],)
        ).fetchall()
        result["events"] = [dict(e) for e in events]
        if item["project_id"]:
            from apollo_project_studio import StudioStore
            store = StudioStore(self.root)
            try:
                project = store.details(item["project_id"])
                result["tasks"] = {
                    state: len([t for t in project["tasks"] if t["state"] == state])
                    for state in ("todo", "running", "review", "accepted", "blocked")
                }
                result["workspace"] = str(store.project_folder(item["project_id"]))
            finally:
                store.close()
        return result

    def pause(self):
        item = self._latest()
        if not item:
            return {"exists": False}
        with self.db:
            if item["state"] in ("RUNNING", "READY_TO_DRAFT", "PROJECT_CREATED"):
                self.db.execute(
                    "UPDATE missions SET state='PAUSED',updated_at=? WHERE id=?",
                    (utc(), item["id"]),
                )
                self._event(item["id"], "paused", "New chat-driven work disabled")
        return self.snapshot()

    def run_one_step(self, *, owner_confirmed=False, model=None, draft=None):
        """One authorized bounded coding step, never an indefinite daemon.

        Tests may inject a fake draft. Real execution calls local Ollama only;
        generated code is NEVER executed by this method.
        """
        if owner_confirmed is not True:
            raise PermissionError("Explicit authorization required for local compute.")
        item = self._latest()
        if not item or not item["project_id"]:
            raise ValueError("No ready Foundry growth project.")
        if item["state"] not in ("READY_TO_DRAFT", "BLOCKED", "PAUSED"):
            raise ValueError("No ready coding step. Check mission status and Foundry reviews.")
        if item["state"] == "PAUSED":
            raise PermissionError("Mission is paused. Explicitly resume in Foundry or retry with the continue command.")
        from apollo_project_studio import StudioStore
        from apollo_foundry_artifacts import save_bundle
        from apollo_project_workers import draft_for_task, model_from_config

        studio = StudioStore(self.root)
        try:
            state = studio.details(item["project_id"])
            eligible = [t for t in state["tasks"] if t["role"] == "implementer"
                        and t["parent_id"] is None and t["state"] == "todo"]
            if not eligible:
                return self.snapshot()
            task = eligible[0]
            tid = task["id"]
            studio.start_task(tid)
            with self.db:
                self.db.execute(
                    "UPDATE missions SET state='RUNNING',task_id=?,error='',updated_at=? WHERE id=?",
                    (tid, utc(), item["id"]),
                )
                self._event(item["id"], "implementer_started", f"Local Ollama task {tid}")
            # No separate process, unrestricted tools, or network beyond local Ollama.
            raw = (draft(studio.worker_state(item["project_id"]), tid) if draft is not None
                   else draft_for_task(
                       studio.worker_state(item["project_id"]), tid,
                       model or model_from_config(self.root),
                   ))
            # Re-check state BEFORE writing any model-generated source.
            refreshed = self._latest()
            if refreshed["id"] != item["id"] or refreshed["state"] != "RUNNING":
                try:
                    studio.fail_task(tid, "Paused before result was saved")
                except (ValueError, OSError):
                    pass
                return self.snapshot()
            saved = save_bundle(studio.project_folder(item["project_id"]), raw)
            checks = studio.run_checks(item["project_id"])
            detail = ", ".join(saved["files"])
            if checks["status"] != "passed":
                raise RuntimeError(
                    "Source staged, but static checks did not pass: "
                    + str(checks.get("status", "unknown"))
                )
            evidence = (
                "Local Ollama draft. Generated files saved only in Foundry project folder; "
                "static checks passed. No project code executed. Docker runtime/GUI "
                "tests, independent review, commercial approval and delivery pending."
            )
            studio.submit_task(tid, (detail + " | " + saved["summary"])[:9000], evidence)
            studio.record_handoff(item["project_id"], "implementer", "manager",
                                  "Local source drafted; static checks passed; awaiting tests", tid)
            with self.db:
                self.db.execute(
                    "UPDATE missions SET state='REVIEW_REQUIRED',output=?,error='',updated_at=? WHERE id=?",
                    (detail[:1000], utc(), item["id"]),
                )
                self._event(item["id"], "static_checks_passed",
                            "Files: " + detail[:450] + "; NO runtime test or deployment")
            return self.snapshot()
        except Exception as exc:
            if "tid" in locals():
                try:
                    studio.fail_task(tid, f"Chat-driven implementer stopped: {type(exc).__name__}: {exc}"[:1600])
                except (ValueError, OSError):
                    pass
            with self.db:
                # Never overrule a pause or stop requested while Ollama was busy.
                if self._latest() and self._latest()["state"] == "RUNNING":
                    self.db.execute(
                        "UPDATE missions SET state='BLOCKED',error=?,updated_at=? WHERE id=?",
                        (f"{type(exc).__name__}: {exc}"[:800], utc(), item["id"]),
                    )
                    self._event(item["id"], "blocked", str(exc)[:550])
            return self.snapshot()
        finally:
            studio.close()

    def report(self):
        state = self.snapshot()
        if not state["exists"] if "exists" in state else False:
            return state["message"]
        title = state["title"]
        message = (
            f"**Apollo growth mission:** {title}\n"
            f"**Actual state:** {state['state']}\n"
            f"Foundry project: {state.get('project_id') or 'not created'}; "
            f"Growth Lab work proposal: {state.get('work_id') or 'not created'}.\n"
        )
        if state.get("output"):
            message += "Generated project files: " + state["output"] + ".\n"
        if state.get("error"):
            message += "**Blocker:** " + state["error"] + "\n"
        if state.get("tasks"):
            message += "Foundry task counts: " + ", ".join(
                f"{key}={value}" for key,value in state["tasks"].items()
            ) + ".\n"
        message += (
            "Project workspace: " + str(state.get("workspace", "not available")) + ".\n"
            "**No revenue has been earned or verified.** Nothing was published, "
            "sold, emailed or installed. To continue automated coding and isolated "
            "runtime tests, open the project in Foundry and explicitly authorize "
            "**Start Continuous Session** once Docker is ready. Generated code "
            "and any eventual commercial delivery still require human review."
        )
        return message
