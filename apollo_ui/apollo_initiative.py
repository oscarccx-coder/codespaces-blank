"""Goal-aware initiative planning for Apollo's existing Suggestions and Runtime.

This service writes goal metadata into ApolloRuntime's existing SQLite database.
It NEVER starts tools, assigns permissions, or creates executable missions.
Model-generated proposals stay in the existing SuggestionStore for owner review.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
import sqlite3

_WORDS = re.compile(r"[a-z0-9]{3,}")
_STOP = {"the", "and", "for", "with", "from", "this", "that", "what", "should", "apollo", "into", "your", "more"}
_MAX_ACTIVE_GOALS = 40


def _utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean(value, field, limit):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    value = " ".join(value.split())
    if not 5 <= len(value) <= limit or any(ord(c) < 32 for c in value):
        raise ValueError(f"{field} must contain 5-{limit} printable characters")
    return value


def _terms(value):
    return set(_WORDS.findall(str(value).casefold())) - _STOP


class InitiativeDirector:
    """Owner-goal registry and deterministic proposal ranking, not an executor."""

    def __init__(self, runtime, suggestions):
        if runtime is None or not hasattr(runtime, "conn") or not hasattr(runtime, "_lock"):
            raise RuntimeError("ApolloRuntime is required for InitiativeDirector")
        self.runtime = runtime
        self.suggestions = suggestions
        with self.runtime._lock, self.runtime.conn:
            self.runtime.conn.executescript("""
                CREATE TABLE IF NOT EXISTS initiative_goal_meta (
                    goal_id INTEGER PRIMARY KEY REFERENCES goals(id),
                    parent_goal_id INTEGER REFERENCES goals(id),
                    desired_outcome TEXT NOT NULL,
                    success_metric TEXT NOT NULL,
                    origin TEXT NOT NULL DEFAULT 'owner',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS initiative_parent_idx
                    ON initiative_goal_meta(parent_goal_id);
                CREATE TABLE IF NOT EXISTS initiative_step_links (
                    goal_id INTEGER NOT NULL REFERENCES goals(id),
                    suggestion_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(goal_id, suggestion_id)
                );
            """)

    def create_goal(self, title, desired_outcome, *, success_metric="Owner reviews the evidence-backed result", priority=70, parent_goal_id=None, owner_confirmed=False):
        if owner_confirmed is not True:
            raise PermissionError("Only the owner may add a strategic initiative goal")
        title = _clean(title, "Goal title", 160)
        desired_outcome = _clean(desired_outcome, "Desired outcome", 800)
        success_metric = _clean(success_metric, "Success metric", 400)
        if type(priority) is not int or not 1 <= priority <= 100:
            raise ValueError("Priority must be an integer from 1 to 100")
        if parent_goal_id is not None and (type(parent_goal_id) is not int or parent_goal_id < 1):
            raise ValueError("Invalid parent goal ID")
        with self.runtime._lock, self.runtime.conn:
            if parent_goal_id is not None:
                parent = self.runtime.conn.execute("SELECT id,status FROM goals WHERE id=?", (parent_goal_id,)).fetchone()
                if parent is None or parent["status"] != "active":
                    raise ValueError("Parent must be an active existing goal")
                if self._depth(parent_goal_id) >= 5:
                    raise ValueError("Maximum five goal ancestry levels")
            active = self.runtime.conn.execute("SELECT count(*) FROM initiative_goal_meta JOIN goals ON goal_id=goals.id WHERE goals.status='active'").fetchone()[0]
            if active >= _MAX_ACTIVE_GOALS:
                raise ValueError("Review existing active goals before adding more")
            duplicate = self.runtime.conn.execute("SELECT id FROM goals WHERE lower(title)=lower(?) AND status='active'", (title,)).fetchone()
            if duplicate is not None:
                raise ValueError("An active goal with this title already exists")
            now = _utc()
            cur = self.runtime.conn.execute(
                "INSERT INTO goals(title,status,priority,notes,created_at,updated_at) VALUES(?,'active',?,'',?,?)",
                (title, priority, now, now),
            )
            gid = cur.lastrowid
            self.runtime.conn.execute(
                "INSERT INTO initiative_goal_meta(goal_id,parent_goal_id,desired_outcome,success_metric,origin,created_at) VALUES(?,?,?,?,?,?)",
                (gid, parent_goal_id, desired_outcome, success_metric, "owner", now),
            )
        return self.goal(gid)

    def _depth(self, goal_id):
        depth, seen = 0, set()
        while goal_id is not None:
            if goal_id in seen:
                raise ValueError("Goal ancestry cycle detected")
            seen.add(goal_id)
            row = self.runtime.conn.execute("SELECT parent_goal_id FROM initiative_goal_meta WHERE goal_id=?", (goal_id,)).fetchone()
            goal_id = row[0] if row is not None else None
            depth += 1
        return depth

    def goal(self, goal_id):
        with self.runtime._lock:
            row = self.runtime.conn.execute(
                "SELECT g.*,m.parent_goal_id,m.desired_outcome,m.success_metric,m.origin "
                "FROM initiative_goal_meta m JOIN goals g ON g.id=m.goal_id WHERE g.id=?", (int(goal_id),),
            ).fetchone()
            if row is None:
                raise KeyError("Initiative goal not found")
            return dict(row)

    def goals(self, *, active_only=False, limit=20):
        limit = max(1, min(int(limit), 40))
        with self.runtime._lock:
            rows = self.runtime.conn.execute(
                "SELECT g.*,m.parent_goal_id,m.desired_outcome,m.success_metric,m.origin "
                "FROM initiative_goal_meta m JOIN goals g ON g.id=m.goal_id "
                + ("WHERE g.status='active' " if active_only else "")
                + "ORDER BY g.priority DESC,g.id ASC LIMIT ?", (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def set_goal_status(self, goal_id, state, *, owner_confirmed=False):
        if owner_confirmed is not True:
            raise PermissionError("Only the owner may change strategic goals")
        if state not in ("active", "paused", "completed", "stopped"):
            raise ValueError("Invalid goal status")
        self.goal(goal_id)
        with self.runtime._lock, self.runtime.conn:
            self.runtime.conn.execute("UPDATE goals SET status=?,updated_at=? WHERE id=?", (state, _utc(), int(goal_id)))
        return self.goal(goal_id)

    def propose_step(self, goal_id, *, owner_confirmed=False):
        """Create a review-only self-prompt, never a mission or tool call."""
        if owner_confirmed is not True:
            raise PermissionError("Only the owner may request a goal-specific planning step")
        goal = self.goal(goal_id)
        if goal["status"] != "active":
            raise ValueError("Only active goals may receive new proposals")
        title = f"Goal #{goal['id']}: {goal['title']}"[:180]
        prompt = (f"Identify one smallest measurable next step toward: {goal['desired_outcome']}. "
                  f"Acceptance measure: {goal['success_metric']}. "
                  "First inspect existing evidence and dependencies; distinguish observations from hypotheses. "
                  "Create a proposed plan only; do not run tools or assume permission.")[:1000]
        reason = f"Owner-created goal #{goal['id']} (priority {goal['priority']}); proposal awaits explicit review."
        proposal = self.suggestions.add("proposal", title, prompt, reason, evidence=())
        with self.runtime._lock, self.runtime.conn:
            self.runtime.conn.execute(
                "INSERT OR IGNORE INTO initiative_step_links(goal_id,suggestion_id,created_at) VALUES(?,?,?)",
                (goal["id"], proposal["id"], _utc()),
            )
        return proposal

    def ranked_proposals(self, *, limit=12):
        """Deterministic, explainable ranking. Scores are heuristics, NOT outcomes."""
        goals = self.goals(active_only=True, limit=40)
        with self.runtime._lock:
            linked = {(r[0], r[1]) for r in self.runtime.conn.execute("SELECT goal_id,suggestion_id FROM initiative_step_links")}
        results = []
        for item in self.suggestions.list():
            if item["kind"] != "proposal" or item["status"] not in ("open", "accepted"):
                continue
            text = item["title"] + " " + item["prompt"]
            words = _terms(text)
            best_score, best_goal = 15.0, None
            for goal in goals:
                goal_words = _terms(goal["title"] + " " + goal["desired_outcome"])
                overlap = len(words & goal_words) / max(1, min(6, len(goal_words)))
                explicit = (goal["id"], item["id"]) in linked
                alignment = 1.0 if explicit else min(1.0, overlap)
                score = 15 + 50 * alignment * goal["priority"] / 100
                if score > best_score:
                    best_score, best_goal = score, goal["id"]
            receipts = item.get("evidence") or []
            # Mission references add only a small ranking signal, not 'verified' status.
            score = min(100, round(best_score + (10 if receipts else 0) + (5 if item["status"] == "open" else 0)))
            results.append({"suggestion_id": item["id"], "title": item["title"],
                            "score": score, "goal_id": best_goal,
                            "status": item["status"], "kind": "proposal",
                            "explanation": "Heuristic goal alignment; not evidence of success"})
        return sorted(results, key=lambda r: (-r["score"], r["suggestion_id"]))[:max(1, min(int(limit), 50))]

    def reflection_context(self):
        """Trusted context data for the existing bounded idle reflection engine."""
        return [{"id": g["id"], "title": g["title"],
                 "desired_outcome": g["desired_outcome"],
                 "success_metric": g["success_metric"], "priority": g["priority"]}
                for g in self.goals(active_only=True, limit=8)]
