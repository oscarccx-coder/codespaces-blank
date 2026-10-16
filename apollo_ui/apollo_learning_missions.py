"""Apollo Learning Missions: durable, owner-authorised, bounded research sessions.

One shared service is used by Apollo Chat, Learning Missions, Mission Control
and Research Library. Never executes model-proposed code, auto-installs software,
edits the core, publishes or trusts unverified research as fact.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import tempfile
import threading
import time
from urllib.parse import urlsplit
import weakref

MIN_INTERVAL = 30
MAX_INTERVAL = 3600
MAX_DAILY_CYCLES = 24
MAX_STEPS = 200
MAX_TOPIC = 180
MAX_LENGTH = 1000
SEARCH_TOPICS = (
    "foundational concepts and established evidence",
    "recent scientific research and review papers",
    "competing explanations and limitations",
    "measurable benchmarks and test methodologies",
    "counterexamples and failed approaches",
    "reproducible experiments and next research questions",
    "safety, ethics and practical constraints",
    "implementation approaches and open research problems",
)
TERMINAL = {"COMPLETED", "STOPPED", "BLOCKED"}
ACTIVE = {"RUNNING", "STOP_REQUESTED", "FINALIZING"}
SERVICE_LOCK = threading.RLock()
SERVICES = weakref.WeakValueDictionary()


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean(value, *, max_chars=MAX_TOPIC):
    text = " ".join(str(value or "").split())
    if not 5 <= len(text) <= max_chars or any(ord(c) < 32 for c in text):
        raise ValueError("Enter a descriptive research goal (5-180 characters).")
    return text


def utc_day():
    return datetime.now(timezone.utc).date().isoformat()


def valid_mode(mode):
    if mode not in ("until_stop", "fixed"):
        raise ValueError("Research mode must be fixed or until_stop.")
    return mode


class MissionStore:
    def __init__(self, root, *, memory=False):
        self.root = Path(root).resolve()
        if memory:
            self.database = ":memory:"
        else:
            folder = self.root / "storage" / "databases"
            folder.mkdir(parents=True, exist_ok=True)
            self.database = str(folder / "apollo_learning_missions.db")
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.database, check_same_thread=False, timeout=15)
        self.db.row_factory = sqlite3.Row
        with self.db:
            self.db.executescript("""
              PRAGMA foreign_keys=ON;
              CREATE TABLE IF NOT EXISTS missions(
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  title TEXT NOT NULL, goal TEXT NOT NULL, mode TEXT NOT NULL,
                  state TEXT NOT NULL, web_allowed INTEGER NOT NULL,
                  autorun INTEGER NOT NULL, max_steps INTEGER NOT NULL,
                  interval_seconds INTEGER NOT NULL,
                  completed_steps INTEGER NOT NULL DEFAULT 0,
                  failed_steps INTEGER NOT NULL DEFAULT 0,
                  no_new_steps INTEGER NOT NULL DEFAULT 0,
                  next_due REAL NOT NULL DEFAULT 0,
                  last_error TEXT NOT NULL DEFAULT '',
                  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                  report TEXT NOT NULL DEFAULT ''
              );
              CREATE TABLE IF NOT EXISTS evidence(
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  mission_id INTEGER NOT NULL REFERENCES missions(id),
                  step_no INTEGER NOT NULL, query TEXT NOT NULL,
                  fetched_count INTEGER NOT NULL DEFAULT 0,
                  saved_file TEXT NOT NULL DEFAULT '',
                  source_urls TEXT NOT NULL DEFAULT '[]',
                  new_urls TEXT NOT NULL DEFAULT '[]',
                  status TEXT NOT NULL, created_at TEXT NOT NULL,
                  UNIQUE(mission_id,step_no)
              );
              CREATE TABLE IF NOT EXISTS events(
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  mission_id INTEGER NOT NULL REFERENCES missions(id),
                  event TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '',
                  at TEXT NOT NULL
              );
            """)

    def close(self):
        with self.lock:
            self.db.close()

    def _event(self, mid, event, detail=""):
        self.db.execute(
            "INSERT INTO events(mission_id,event,detail,at) VALUES(?,?,?,?)",
            (mid, event, str(detail)[:500], utc()),
        )

    def _mission(self, mid):
        item = self.db.execute("SELECT * FROM missions WHERE id=?", (int(mid),)).fetchone()
        if item is None:
            raise KeyError("Learning mission not found")
        return dict(item)

    def create(self, title, goal, *, mode="until_stop", web_allowed=False,
               steps=8, interval_seconds=120, owner_confirmed=False):
        if owner_confirmed is not True:
            raise PermissionError("Learning mission creation requires explicit owner authorisation.")
        title = clean(title, max_chars=MAX_TOPIC)
        goal = clean(goal, max_chars=MAX_LENGTH)
        mode = valid_mode(mode)
        if type(web_allowed) is not bool:
            raise ValueError("web_allowed must be explicitly true or false.")
        if type(steps) is not int or not 1 <= steps <= MAX_STEPS:
            raise ValueError("Fixed research cycles must be between 1 and 200.")
        if type(interval_seconds) is not int or not MIN_INTERVAL <= interval_seconds <= MAX_INTERVAL:
            raise ValueError("Research frequency must be 30-3600 seconds.")
        if not web_allowed:
            raise ValueError("The research runner needs public-source access; use approved research permission. Offline-only missions will be a separate capability.")
        with self.lock, self.db:
            active = self.db.execute(
                "SELECT count(*) FROM missions WHERE state IN ('RUNNING','STOP_REQUESTED','PAUSED','FINALIZING')"
            ).fetchone()[0]
            if active >= 12:
                raise ValueError("Maximum 12 active/suspended learning missions.")
            stamp = utc()
            cursor = self.db.execute(
                "INSERT INTO missions(title,goal,mode,state,web_allowed,autorun,max_steps,"
                "interval_seconds,next_due,created_at,updated_at) "
                "VALUES(?,?,?,'RUNNING',?,1,?,?,0,?,?)",
                (title, goal, mode, int(web_allowed), steps, interval_seconds, stamp, stamp),
            )
            mid = cursor.lastrowid
            self._event(mid, "authorised",
                        f"Mode {mode}; web permitted; daily limit {MAX_DAILY_CYCLES}; "
                        "one existing Apollo research tool per step. No code execution.")
        return self.status(mid)

    def list(self):
        with self.lock:
            rows = self.db.execute(
                "SELECT * FROM missions ORDER BY id DESC LIMIT 100"
            ).fetchall()
            return [dict(row) for row in rows]

    def status(self, mid):
        with self.lock:
            item = self._mission(mid)
            item["evidence_count"] = self.db.execute(
                "SELECT count(*) FROM evidence WHERE mission_id=? AND status='saved'", (mid,)
            ).fetchone()[0]
            item["new_sources"] = self.db.execute(
                "SELECT new_urls FROM evidence WHERE mission_id=? AND status='saved'", (mid,)
            ).fetchall()
            item["new_sources"] = len(set(u for row in item["new_sources"]
                                         for u in json.loads(row["new_urls"])))
            item["latest"] = [
                dict(row) for row in self.db.execute(
                    "SELECT step_no,query,fetched_count,saved_file,source_urls,new_urls,status,created_at "
                    "FROM evidence WHERE mission_id=? ORDER BY id DESC LIMIT 8", (mid,)
                )
            ]
            item["events"] = [
                dict(row) for row in self.db.execute(
                    "SELECT event,detail,at FROM events WHERE mission_id=? ORDER BY id DESC LIMIT 15", (mid,)
                )
            ]
            return item

    def pause(self, mid, *, owner_confirmed=False):
        if owner_confirmed is not True:
            raise PermissionError("Pausing a mission requires owner approval.")
        with self.lock, self.db:
            item = self._mission(mid)
            if item["state"] in ACTIVE:
                # A slow web step is permitted to finish and commit, then scheduling stops.
                self.db.execute(
                    "UPDATE missions SET state='PAUSED',autorun=0,updated_at=? WHERE id=?",
                    (utc(), mid),
                )
                self._event(mid, "paused", "No new research steps; current step may finish.")
        return self.status(mid)

    def resume(self, mid, *, owner_confirmed=False):
        if owner_confirmed is not True:
            raise PermissionError("Resuming learning requires explicit owner approval.")
        with self.lock, self.db:
            item = self._mission(mid)
            if item["state"] != "PAUSED":
                raise ValueError("Only paused missions can resume. A stopped mission is final.")
            self.db.execute(
                "UPDATE missions SET state='RUNNING',autorun=1,next_due=0,updated_at=? WHERE id=?",
                (utc(), mid),
            )
            self._event(mid, "resumed", "Previous public-source research approval renewed.")
        return self.status(mid)

    def stop(self, mid, *, owner_confirmed=False):
        if owner_confirmed is not True:
            raise PermissionError("Stop requires explicit owner instruction.")
        with self.lock, self.db:
            item = self._mission(mid)
            if item["state"] not in TERMINAL:
                self.db.execute(
                    "UPDATE missions SET state='STOP_REQUESTED',autorun=0,updated_at=? WHERE id=?",
                    (utc(), mid),
                )
                self._event(mid, "stop_requested",
                            "Finish the in-flight source fetch, preserve findings, write closing report.")
        return self.status(mid)

    def stop_all(self, *, owner_confirmed=False):
        if owner_confirmed is not True:
            raise PermissionError("Owner must explicitly request stopping all missions.")
        for item in self.list():
            if item["state"] not in TERMINAL:
                self.stop(item["id"], owner_confirmed=True)
        return self.list()

    def pick(self, *, now=None):
        """Choose at most one due job. Only RUNNING jobs are executable."""
        now = now or time.time()
        with self.lock, self.db:
            candidates = self.db.execute(
                "SELECT * FROM missions WHERE state='RUNNING' AND autorun=1 AND web_allowed=1"
                " AND next_due<=? ORDER BY next_due,id LIMIT 20", (now,)
            ).fetchall()
            for row in candidates:
                mid = row["id"]
                day_start = datetime.fromtimestamp(now,timezone.utc).date().isoformat()
                used = self.db.execute(
                    "SELECT count(*) FROM evidence WHERE mission_id=? AND substr(created_at,1,10)=?",
                    (mid, day_start),
                ).fetchone()[0]
                if used >= MAX_DAILY_CYCLES:
                    # Avoid a hot loop: until-stop mode sleeps until next UTC day.
                    tomorrow = datetime.fromisoformat(day_start).replace(tzinfo=timezone.utc).timestamp()+86400
                    self.db.execute("UPDATE missions SET next_due=? WHERE id=?", (tomorrow,mid))
                    continue
                if row["mode"]=="fixed" and row["completed_steps"]>=row["max_steps"]:
                    self._finish(mid, "COMPLETED")
                    continue
                if row["no_new_steps"]>=3:
                    self._finish(mid, "BLOCKED", "No new source URLs in three research passes. Review the goal.")
                    continue
                # Reserve step before web action, guaranteeing one active worker/cycle.
                self.db.execute(
                    "UPDATE missions SET next_due=?,updated_at=? WHERE id=?",
                    (now+row["interval_seconds"],utc(),mid),
                )
                self._event(mid, "step_started", "Source research batch reserved")
                return dict(row)
        return None

    def record(self, mid, query, result=None, error=None):
        """Persist source receipts. No model-generated claim is marked verified."""
        with self.lock, self.db:
            item = self._mission(mid)
            step_no = item["completed_steps"]+item["failed_steps"]+1
            sources = (result or {}).get("sources") or []
            urls = sorted({
                str(entry.get("url") or "")[:700]
                for entry in sources if isinstance(entry,dict)
                and str(entry.get("url") or "").startswith("https://")
            })
            old = set()
            for row in self.db.execute(
                "SELECT source_urls FROM evidence WHERE mission_id=?", (mid,)
            ):
                try:
                    old.update(json.loads(row[0]))
                except (ValueError, TypeError):
                    pass
            new_urls = [url for url in urls if url not in old]
            count = int((result or {}).get("source_pages_fetched") or 0)
            saved = (result or {}).get("saved") or {}
            filename = str(saved.get("filename") or "")
            success = bool(result and count>0 and saved.get("saved")
                           and filename.startswith("learning_missions/")
                           and not error)
            if not success:
                count = 0
                filename = ""
            with self.db:
                self.db.execute(
                    "INSERT INTO evidence(mission_id,step_no,query,fetched_count,saved_file,"
                    "source_urls,new_urls,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (mid, step_no, query[:250], count, filename, json.dumps(urls if success else []),
                     json.dumps(new_urls if success else []), "saved" if success else "failed", utc()),
                )
                self.db.execute(
                    "UPDATE missions SET completed_steps=completed_steps+?,failed_steps=failed_steps+?,"
                    "no_new_steps=?,last_error=?,updated_at=? WHERE id=?",
                    (int(success),int(not success),
                     (0 if new_urls else item["no_new_steps"]+1) if success else item["no_new_steps"],
                     "" if success else str(error or "No fetched source pages")[:600],utc(),mid),
                )
                self._event(mid,"source_saved" if success else "step_failed",
                            f"{count} pages; {len(new_urls)} new source references"
                            if success else str(error or "No pages fetched")[:450])
                after = self._mission(mid)
                if after["state"] == "STOP_REQUESTED":
                    self._finish(mid,"STOPPED")
                elif after["state"] == "RUNNING" and after["mode"] == "fixed" and after["completed_steps"] >= after["max_steps"]:
                    self._finish(mid,"COMPLETED")
                elif after["state"] == "RUNNING" and after["failed_steps"] >= 3:
                    self._finish(mid,"BLOCKED","Three research steps failed. Review the error and tool permissions.")
                elif after["state"] == "RUNNING" and after["no_new_steps"] >= 3:
                    self._finish(mid,"BLOCKED","No new source URLs over three cycles; avoid endless repetition.")
        return self.status(mid)

    def _finish(self, mid, state, error=""):
        if state not in TERMINAL:
            raise ValueError("Invalid final state.")
        item = self._mission(mid)
        sources = [row for row in self.db.execute(
            "SELECT step_no,query,fetched_count,saved_file,new_urls,status FROM evidence "
            "WHERE mission_id=? ORDER BY id", (mid,)
        )]
        lines = [
            f"# Apollo learning mission #{mid}: {item['title']}",
            f"Research goal: {item['goal']}",
            f"Status: {state}",
            f"Completed research batches: {item['completed_steps']}",
            f"Failed batches: {item['failed_steps']}",
            "",
            "## Source research and saved artefacts",
        ]
        if not sources:
            lines.append("No source research completed.")
        for row in sources:
            lines.append(
                f"- Batch {row['step_no']}: {row['query']} "
                f"({row['status']}, {row['fetched_count']} pages)."
            )
            if row["saved_file"]:
                lines.append(f"  Local evidence: {row['saved_file']}")
            for url in json.loads(row["new_urls"])[:10]:
                lines.append(f"  New source: {url}")
        lines.extend([
            "",
            "## Review and next decisions",
            "Source excerpts are **unverified evidence**. No independent scientific",
            "verification, model training, core software upgrade or research breakthrough",
            "has occurred. Read and cross-check primary sources before promoting claims.",
            "Propose new experiments and improvements for human approval.",
        ])
        if error:
            lines.append("Blocker: "+error)
        report = "\n".join(lines)[:30000]
        self.db.execute(
            "UPDATE missions SET state=?,autorun=0,report=?,last_error=?,updated_at=? WHERE id=?",
            (state,report,error[:600] if error else item["last_error"],utc(),mid),
        )
        self._event(mid,"finalized",state+": "+str(error)[:300])

    def finalize_stops(self):
        with self.lock, self.db:
            mids=[r[0] for r in self.db.execute(
                "SELECT id FROM missions WHERE state='STOP_REQUESTED'"
            )]
            for mid in mids:
                self._finish(mid,"STOPPED")
            return mids

    def recover(self):
        """There is no running step lease across process restarts.

        Worker picks one step per process and saves results atomically. Stop
        requests finalize before scheduling; PAUSED and terminal work stay inert.
        """
        return self.finalize_stops()

    def reports(self, mid=None):
        with self.lock:
            rows = self.db.execute(
                "SELECT id,title,state,completed_steps,failed_steps,report,last_error "
                "FROM missions WHERE id=?" if mid is not None else
                "SELECT id,title,state,completed_steps,failed_steps,report,last_error "
                "FROM missions ORDER BY id DESC LIMIT 50",
                (int(mid),) if mid is not None else (),
            ).fetchall()
            return [dict(row) for row in rows]


def safe_public_https_urls(sources):
    """Source citations from search results are references, never instructions."""
    found=[]
    for value in sources or []:
        if not isinstance(value,dict):
            continue
        url = str(value.get("url") or "")
        try:
            parsed=urlsplit(url)
        except ValueError:
            continue
        if (parsed.scheme == "https" and parsed.hostname
                and not parsed.username and not parsed.password
                and len(url)<700):
            found.append(url)
    return found[:10]


class MissionService:
    """Single shared process worker; app and Chat read/write same database."""

    def __init__(self, root, *, executor=None, memory=False, auto_thread=True):
        self.root = Path(root).resolve()
        self._temp = tempfile.TemporaryDirectory() if memory else None
        self.store = MissionStore(self._temp.name if memory else self.root)
        self.executor = executor
        self.lock = threading.RLock()
        self._wake = threading.Event()
        self._shutdown = threading.Event()
        self.thread = None
        self.auto_thread = auto_thread
        self.store.recover()
        if auto_thread:
            self._ensure_thread()

    def configure(self, executor):
        self.executor = executor
        self._wake.set()

    def _ensure_thread(self):
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                return
            self.thread = threading.Thread(
                target=self._loop, name="ApolloLearningMissions", daemon=True,
            )
            self.thread.start()

    def begin(self, title, goal, **options):
        info=self.store.create(title,goal,**options)
        self._wake.set()
        self._ensure_thread() if self.auto_thread else None
        return info

    def pause(self, mid):
        status=self.store.pause(mid,owner_confirmed=True)
        self._wake.set()
        return status

    def resume(self, mid):
        status=self.store.resume(mid,owner_confirmed=True)
        self._wake.set()
        return status

    def stop(self, mid):
        status=self.store.stop(mid,owner_confirmed=True)
        self._wake.set()
        return status

    def stop_all(self):
        result=self.store.stop_all(owner_confirmed=True)
        self._wake.set()
        return result

    def tick(self):
        """Complete one bounded research pass. Callable from deterministic tests."""
        self.store.finalize_stops()
        if self._shutdown.is_set() or self.executor is None:
            # Never burn through pending missions while the Tool Manager loads.
            return None
        item=self.store.pick()
        if item is None:
            return None
        mid=item["id"]
        step_no=item["completed_steps"]+item["failed_steps"]
        focus=SEARCH_TOPICS[step_no % len(SEARCH_TOPICS)]
        query=(item["goal"]+" "+focus)[:240]
        result=None
        error=None
        try:
            if self.executor is None:
                raise RuntimeError("Research tool unavailable. Enable Apollo Training and its permitted public web search.")
            filename=f"learning_missions/mission_{mid}_step_{step_no+1}_{int(time.time())}.txt"
            result=self.executor(query,filename,3)
        except Exception as exc:
            error=f"{type(exc).__name__}: {str(exc)[:500]}"
        return self.store.record(mid,query,result,error)

    def _loop(self):
        while not self._shutdown.is_set():
            try:
                self.tick()
            except Exception:
                # Do not kill the daemon on one malformed result or disk fault.
                # Operator can still inspect/stop it; no false completion.
                pass
            self._wake.wait(1.5)
            self._wake.clear()

    def shutdown(self):
        self._shutdown.set()
        self._wake.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=0.3)
        # No destructive DB close while a slow network pass is still active.


def shared_service(root, *, executor=None, validation=False):
    """One service for both Apollo apps and Chat in a single running process."""
    if validation:
        return MissionService(root, memory=True, auto_thread=False,executor=executor)
    key=str(Path(root).resolve()).casefold()
    with SERVICE_LOCK:
        obj=SERVICES.get(key)
        if obj is None:
            obj=MissionService(root,executor=executor)
            SERVICES[key]=obj
        elif executor is not None:
            obj.configure(executor)
        return obj
