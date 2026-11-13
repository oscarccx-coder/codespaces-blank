"""Owner-approved wall-clock schedules for a limited set of Apollo mission tasks.

Only the owner-facing UI creates schedules. The store is deterministic and does
not call an LLM or execute model-generated commands. Due work is leased in SQLite
and handed off to existing approved capabilities by SuggestionCenter.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import threading
import time

REPEATS = frozenset({"once", "daily", "weekly"})
KINDS = frozenset({"research", "health"})
MAX_RUNS = 365
MAX_CATCHUP_SECONDS = 24 * 3600


def _utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _validate_text(value, label, limit=1000):
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    value = " ".join(value.split())
    if not 5 <= len(value) <= limit or any(ord(x) < 32 for x in value):
        raise ValueError(f"{label} must contain 5-{limit} printable characters")
    return value


def _wall_ts(day, clock):
    """OS-local timestamp: follows local Windows DST rules, no UTC drift."""
    d = date.fromisoformat(day)
    h, m = map(int, clock.split(":"))
    if not 0 <= h <= 23 or not 0 <= m <= 59 or len(clock) != 5:
        raise ValueError("Time must be HH:MM")
    # tm_isdst=-1 asks Windows/OS to resolve daylight saving for this date.
    return time.mktime((d.year, d.month, d.day, h, m, 0, 0, 0, -1))


def _next_occurrence(start_day, clock, repeat, after):
    """First eligible scheduled wall time strictly later than *after*."""
    if repeat not in REPEATS:
        raise ValueError("Unsupported repeat mode")
    first = date.fromisoformat(start_day)
    if repeat == "once":
        ts = _wall_ts(first.isoformat(), clock)
        return ts if ts > after else None
    today = datetime.fromtimestamp(after).date()
    if today > first:
        days = (today - first).days
        n = days if repeat == "daily" else days // 7 * 7
        first += timedelta(days=n)
    step = 1 if repeat == "daily" else 7
    for _ in range(4):
        ts = _wall_ts(first.isoformat(), clock)
        if ts > after:
            return ts
        first += timedelta(days=step)
    raise RuntimeError("Could not calculate next schedule occurrence")


class ScheduledMissionStore:
    """Recurring schedules with durable run receipts; one dispatched run per slot."""

    def __init__(self, root, *, memory=False):
        self.lock = threading.RLock()
        if memory:
            database = ":memory:"
        else:
            folder = Path(root) / "storage" / "databases"
            folder.mkdir(parents=True, exist_ok=True)
            database = str(folder / "apollo_schedules.db")
        self.db = sqlite3.connect(database, check_same_thread=False, timeout=15)
        self.db.row_factory = sqlite3.Row
        with self.lock, self.db:
            self.db.executescript("""
                PRAGMA foreign_keys=ON;
                CREATE TABLE IF NOT EXISTS schedules(
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    task_kind TEXT NOT NULL,
                    task_json TEXT NOT NULL,
                    repeat_mode TEXT NOT NULL,
                    start_day TEXT NOT NULL,
                    local_time TEXT NOT NULL,
                    next_due REAL,
                    state TEXT NOT NULL,
                    web_allowed INTEGER NOT NULL DEFAULT 0,
                    max_runs INTEGER NOT NULL,
                    run_count INTEGER NOT NULL DEFAULT 0,
                    consecutive_failures INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS schedule_runs(
                    id INTEGER PRIMARY KEY,
                    schedule_id INTEGER NOT NULL REFERENCES schedules(id),
                    slot_ts REAL NOT NULL,
                    state TEXT NOT NULL,
                    receipt_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    finished_at TEXT,
                    UNIQUE(schedule_id,slot_ts)
                );
                CREATE INDEX IF NOT EXISTS schedule_next_due_idx
                    ON schedules(state,next_due);
            """)

    def close(self):
        with self.lock:
            self.db.close()

    def create(self, *, name, kind, task, start_day, local_time, repeat="once",
               max_runs=30, web_allowed=False, owner_confirmed=False, now=None):
        if owner_confirmed is not True:
            raise PermissionError("Scheduling a task requires explicit owner approval")
        name = _validate_text(name, "Schedule name", 160)
        if kind not in KINDS or repeat not in REPEATS:
            raise ValueError("Unsupported task kind or repeat mode")
        if type(task) is not dict:
            raise ValueError("Scheduled task must be a typed payload")
        if type(web_allowed) is not bool:
            raise ValueError("Web approval must be explicit")
        if type(max_runs) is not int or not 1 <= max_runs <= MAX_RUNS:
            raise ValueError("Scheduled run limit must be 1-365")
        if kind == "research":
            title = _validate_text(task.get("title"), "Research title", 160)
            goal = _validate_text(task.get("goal"), "Research goal", 900)
            if not web_allowed:
                raise PermissionError("Scheduled public research requires explicit web consent")
            task = {"title": title, "goal": goal}
        else:
            if web_allowed or task:
                raise ValueError("Health checks do not accept web consent or arbitrary arguments")
            task = {}
        if repeat == "once":
            max_runs = 1
        # Validate wall clock and ensure future first occurrence.
        first = _wall_ts(start_day, local_time)
        now = time.time() if now is None else float(now)
        if first <= now:
            raise ValueError("Choose a future starting date and time")
        if first > now + 366 * 86400 * 3:
            raise ValueError("Scheduled start must be within three years")
        stamp = _utc()
        with self.lock, self.db:
            active = self.db.execute(
                "SELECT count(*) FROM schedules WHERE state IN ('active','paused','blocked')"
            ).fetchone()[0]
            if active >= 40:
                raise ValueError("Review existing schedules before creating more")
            cur = self.db.execute(
                "INSERT INTO schedules(name,task_kind,task_json,repeat_mode,start_day,local_time,"
                "next_due,state,web_allowed,max_runs,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,'active',?,?,?,?)",
                (name,kind,json.dumps(task),repeat,start_day,local_time,first,int(web_allowed),max_runs,stamp,stamp),
            )
        return self.get(cur.lastrowid)

    def _row(self, row):
        item = dict(row)
        item["task"] = json.loads(item.pop("task_json"))
        item["web_allowed"] = bool(item["web_allowed"])
        item["next_local"] = (
            datetime.fromtimestamp(item["next_due"]).strftime("%Y-%m-%d %H:%M")
            if item["next_due"] is not None else None
        )
        return item

    def get(self, ident):
        with self.lock:
            row = self.db.execute("SELECT * FROM schedules WHERE id=?", (int(ident),)).fetchone()
            if row is None:
                raise KeyError("Schedule not found")
            return self._row(row)

    def list(self):
        with self.lock:
            return [self._row(r) for r in self.db.execute(
                "SELECT * FROM schedules ORDER BY CASE state WHEN 'active' THEN 0 "
                "WHEN 'paused' THEN 1 ELSE 2 END,next_due,id LIMIT 100"
            )]

    def runs(self, ident, *, limit=15):
        self.get(ident)
        with self.lock:
            return [dict(row) for row in self.db.execute(
                "SELECT * FROM schedule_runs WHERE schedule_id=? ORDER BY id DESC LIMIT ?",
                (int(ident), max(1,min(int(limit),100))),
            )]

    def control(self, ident, action, *, owner_confirmed=False, now=None):
        if owner_confirmed is not True:
            raise PermissionError("Only the owner may change scheduled tasks")
        if action not in {"pause", "resume", "stop"}:
            raise ValueError("Unknown schedule action")
        now = time.time() if now is None else float(now)
        with self.lock, self.db:
            row = self.db.execute("SELECT * FROM schedules WHERE id=?", (int(ident),)).fetchone()
            if row is None:
                raise KeyError("Schedule not found")
            state = row["state"]
            due = row["next_due"]
            if action == "stop" and state in ("active", "paused", "blocked"):
                new_state = "stopped"
            elif action == "pause" and state == "active":
                new_state = "paused"
            elif action == "resume" and state in ("paused", "blocked"):
                if row["run_count"] >= row["max_runs"]:
                    raise ValueError("Scheduled run limit has been reached")
                due = _next_occurrence(row["start_day"],row["local_time"],row["repeat_mode"],now)
                if due is None:
                    raise ValueError("One-time schedule already expired")
                new_state = "active"
            else:
                raise ValueError("Schedule action not available for current state")
            self.db.execute(
                "UPDATE schedules SET state=?,next_due=?,consecutive_failures=0,updated_at=? WHERE id=?",
                (new_state,due,_utc(),int(ident)),
            )
        return self.get(ident)

    def recover(self):
        """Never blindly replay a reserved run after a process crash."""
        with self.lock, self.db:
            pending = [r[0] for r in self.db.execute(
                "SELECT DISTINCT schedule_id FROM schedule_runs WHERE state='reserved'"
            )]
            if pending:
                self.db.execute(
                    "UPDATE schedule_runs SET state='uncertain',error='Interrupted before receipt; review before retry',"
                    "finished_at=? WHERE state='reserved'", (_utc(),),
                )
                self.db.executemany(
                    "UPDATE schedules SET state='blocked',last_error=?,updated_at=? WHERE id=? "
                    "AND state='active'",
                    [("An earlier scheduled dispatch is uncertain; review its result",_utc(),i) for i in pending],
                )
            return pending

    def reserve_due(self, *, now=None):
        """Atomically reserve at most one due event across all Apollo processes."""
        now = time.time() if now is None else float(now)
        with self.lock, self.db:
            self.db.execute("BEGIN IMMEDIATE")
            rows = self.db.execute(
                "SELECT * FROM schedules WHERE state='active' AND next_due<=? "
                "ORDER BY next_due,id LIMIT 12",(now,)
            ).fetchall()
            for row in rows:
                sid = row["id"]
                if row["run_count"] >= row["max_runs"]:
                    self.db.execute("UPDATE schedules SET state='completed',next_due=NULL,updated_at=? WHERE id=?",
                                    (_utc(),sid))
                    continue
                due = row["next_due"]
                if now - due > MAX_CATCHUP_SECONDS:
                    # Coalesce missed days: only most recent occurrence may run.
                    candidate = _next_occurrence(
                        row["start_day"],row["local_time"],row["repeat_mode"],
                        now - MAX_CATCHUP_SECONDS
                    )
                    if candidate is None or candidate > now:
                        state = "expired" if row["repeat_mode"] == "once" else "active"
                        next_due = None if state == "expired" else _next_occurrence(
                            row["start_day"],row["local_time"],row["repeat_mode"],now
                        )
                        self.db.execute(
                            "UPDATE schedules SET state=?,next_due=?,last_error=?,updated_at=? WHERE id=?",
                            (state,next_due,"Skipped missed occurrence (older than 24 hours)",_utc(),sid),
                        )
                        continue
                    due = candidate
                next_due = _next_occurrence(row["start_day"],row["local_time"],row["repeat_mode"],now)
                total = row["run_count"] + 1
                next_state = "completed" if total >= row["max_runs"] or next_due is None else "active"
                token = _utc()
                cur = self.db.execute(
                    "INSERT OR IGNORE INTO schedule_runs(schedule_id,slot_ts,state,created_at) "
                    "VALUES(?,?,'reserved',?)", (sid,due,token),
                )
                self.db.execute(
                    "UPDATE schedules SET next_due=?,state=?,run_count=?,updated_at=? WHERE id=?",
                    (next_due if next_state=="active" else None,next_state,total,token,sid),
                )
                if cur.rowcount == 0:
                    continue
                result = self._row(row)
                result["run_id"] = cur.lastrowid
                result["slot_ts"] = due
                return result
        return None

    def finish(self, run_id, *, state, receipt=None, error=""):
        if state not in {"queued", "completed", "failed"}:
            raise ValueError("Invalid dispatch result state")
        message = str(error)[:700]
        payload = json.dumps(receipt or {},ensure_ascii=False,default=str)[:6000]
        with self.lock, self.db:
            row = self.db.execute(
                "SELECT r.schedule_id,s.consecutive_failures,s.state FROM schedule_runs r "
                "JOIN schedules s ON s.id=r.schedule_id WHERE r.id=? AND r.state='reserved'",
                (int(run_id),)
            ).fetchone()
            if row is None:
                raise ValueError("Run not reserved or already finalised")
            count = row["consecutive_failures"]+1 if state=="failed" else 0
            self.db.execute(
                "UPDATE schedule_runs SET state=?,receipt_json=?,error=?,finished_at=? WHERE id=?",
                (state,payload,message,_utc(),int(run_id)),
            )
            should_block = count >= 3 and row["state"]=="active"
            self.db.execute(
                "UPDATE schedules SET consecutive_failures=?,last_error=?,"
                "state=CASE WHEN ? THEN 'blocked' ELSE state END,updated_at=? WHERE id=?",
                (count,message,int(should_block),_utc(),row["schedule_id"]),
            )


__all__ = ["ScheduledMissionStore", "_next_occurrence"]
