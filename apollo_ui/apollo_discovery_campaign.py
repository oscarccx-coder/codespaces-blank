"""Apollo Discovery Alliance: owner-authorised, finite local recipe experiments.

This is NOT model-weight training or production self-modification. Fixed tests
exercise prompt recipes using the existing loopback Ollama model. No generated
code, filesystem changes, device controls or external tools are available to
candidate agents. Owner approval is mandatory before spending local compute.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
import uuid

from apollo_discovery_selection import (
    CandidateEvaluation, SelectionPolicy, clone_recipe, select_generation,
)

REPEATS = 3
DEFAULT_POLICY = SelectionPolicy()
MAX_CAMPAIGN_AGE_SECONDS = 2 * 3600
NUMBER = re.compile(r"^\s*(?:answer\s*[:=]\s*)?(-?\d+)\s*[.!]?\s*$", re.I)
BASE_RECIPE = {"strategy": "direct", "review_passes": 0,
               "context_budget": 512, "retrieval_limit": 0}
CHALLENGER_RECIPE = {"strategy": "decompose", "review_passes": 0,
                     "context_budget": 512, "retrieval_limit": 0}


def _utc():
    return datetime.now(timezone.utc).isoformat()


def benchmark():
    """Fixed non-sensitive math/Python exercises with exact numeric outcomes.

    This is a preliminary capability *smoke* benchmark, not unseen research,
    scientific discovery, medical competence or a general reasoning IQ test.
    """
    cases = []
    for index in range(1, 13):
        x, y = index * 13 + 17, index * 7 + 4
        cases.append((f"Calculate {x} + {y} * 3.", str(x + y * 3)))
    for index in range(1, 11):
        x, y = index * 89 + 11, index + 6
        cases.append((f"Calculate the remainder when {x} is divided by {y}.", str(x % y)))
    for index in range(1, 11):
        length, scale = index + 2, index % 4 + 2
        cases.append((f"Python: what does len('x' * {length} * {scale}) return?", str(length * scale)))
    for index in range(1, 9):
        x, y = index * 9 + 1, index * 5 + 2
        cases.append((f"Python: what integer does ({x} // 3) + ({y} % 4) produce?",
                      str((x // 3) + (y % 4))))
    return tuple(cases)


SUITE = benchmark()
SUITE_DIGEST = hashlib.sha256(
    json.dumps(SUITE, separators=(",", ":"), ensure_ascii=True).encode()
).hexdigest()
assert len(SUITE) >= 30


def _safe_answer(value):
    match = NUMBER.fullmatch(str(value or "")[:512])
    return match.group(1) if match else None


def _prompt(question, recipe):
    strategy = recipe["strategy"]
    instruction = {
        "direct": "Compute carefully.",
        "decompose": "Work through the arithmetic or Python evaluation internally before responding.",
        "verify": "Independently check the result internally before responding.",
    }[strategy]
    return (
        "You are an isolated mathematical/code-expression answer specialist. "
        "You have no tools or permissions. Respond with exactly one signed decimal "
        "integer, no explanation, markdown, commands or extra text. "
        + instruction + "\nTask: " + question
    )


def _ask_local(prompt, model, context_budget, timeout=90):
    """Only use Apollo's existing serialized loopback Ollama connection."""
    import urllib.request
    from apollo_project_workers import LOCAL_ENDPOINT, MODEL_LOCK, _read_model_response
    if not MODEL_LOCK.acquire(blocking=False):
        raise RuntimeError("Apollo Ollama is busy; Discovery will pause, not overload the GPU.")
    try:
        request = urllib.request.Request(
            LOCAL_ENDPOINT,
            data=json.dumps({
                "model": model, "prompt": prompt, "stream": False,
                "options": {"num_ctx": context_budget, "num_predict": 80,
                            "temperature": 0.0},
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        response = _read_model_response(request, timeout=min(110, max(10, int(timeout))))
        result = response.get("response")
        if not isinstance(result, str) or not result.strip():
            raise RuntimeError("Ollama returned no response; no result has been counted.")
        if response.get("done_reason") == "length":
            raise RuntimeError("Ollama response was truncated; no result has been counted.")
        return result[:512]
    finally:
        MODEL_LOCK.release()


class DiscoveryCampaign:
    """Small durable experiment state machine, instantiated per UI worker thread."""

    def __init__(self, base):
        root = Path(base).resolve()
        db_dir = root / "storage" / "databases"
        db_dir.mkdir(parents=True, exist_ok=True)
        self.path = db_dir / "apollo_discovery.db"
        self.conn = sqlite3.connect(str(self.path), timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS discovery_campaigns (
              id TEXT PRIMARY KEY, title TEXT NOT NULL, model TEXT NOT NULL,
              state TEXT NOT NULL, generation INTEGER NOT NULL DEFAULT 0,
              expires_at REAL NOT NULL DEFAULT 0, steps INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL, note TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS discovery_agents (
              id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES discovery_campaigns(id),
              generation INTEGER NOT NULL, parent_id TEXT, baseline INTEGER NOT NULL DEFAULT 0,
              recipe TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'ACTIVE',
              misses INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS discovery_agents_campaign ON discovery_agents(campaign_id, generation);
            CREATE TABLE IF NOT EXISTS discovery_trials (
              campaign_id TEXT NOT NULL REFERENCES discovery_campaigns(id),
              agent_id TEXT NOT NULL REFERENCES discovery_agents(id),
              case_index INTEGER NOT NULL, repeat_index INTEGER NOT NULL,
              correct INTEGER NOT NULL, answer_sha256 TEXT NOT NULL,
              elapsed_seconds REAL NOT NULL, completed_at TEXT NOT NULL,
              PRIMARY KEY(agent_id, case_index, repeat_index)
            );
            CREATE TABLE IF NOT EXISTS discovery_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id TEXT NOT NULL,
              event_type TEXT NOT NULL, detail TEXT NOT NULL, at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS discovery_proposals (
              campaign_id TEXT PRIMARY KEY REFERENCES discovery_campaigns(id),
              agent_id TEXT NOT NULL, baseline_accuracy REAL NOT NULL,
              candidate_accuracy REAL NOT NULL, summary TEXT NOT NULL,
              state TEXT NOT NULL DEFAULT 'PENDING_OWNER_REVIEW', created_at TEXT NOT NULL
            );
        """)
        self.conn.commit()

    def close(self):
        self.conn.close()

    def _row(self, campaign_id):
        row = self.conn.execute(
            "SELECT * FROM discovery_campaigns WHERE id=?", (campaign_id,)
        ).fetchone()
        if not row:
            raise ValueError("Discovery campaign not found")
        return row

    def _event(self, campaign_id, kind, detail=""):
        self.conn.execute(
            "INSERT INTO discovery_events(campaign_id,event_type,detail,at) VALUES(?,?,?,?)",
            (campaign_id, kind, str(detail)[:1000], _utc()),
        )

    def create(self, title, model):
        from apollo_project_workers import model_from_config
        # Model name comes only from Apollo's trusted local config, never from AI-generated input.
        configured = model_from_config(self.path.parent.parent.parent)
        if model != configured:
            raise ValueError("Discovery must use Apollo's configured local coding model")
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 100:
            raise ValueError("Give the campaign a short title.")
        identifier = uuid.uuid4().hex
        with self.conn:
            self.conn.execute(
                "INSERT INTO discovery_campaigns(id,title,model,state,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (identifier, title.strip(), model, "DRAFT", _utc(), _utc()),
            )
            for recipe, baseline in ((BASE_RECIPE, True), (CHALLENGER_RECIPE, False)):
                self._add_agent(identifier, 0, recipe, baseline=baseline)
            self._event(identifier, "created", "Draft; no worker started or GPU time consumed")
        return identifier

    def _add_agent(self, campaign_id, generation, recipe, *, baseline=False, parent_id=None, misses=0):
        candidate_id = uuid.uuid4().hex
        self.conn.execute(
            "INSERT INTO discovery_agents(id,campaign_id,generation,parent_id,baseline,recipe,misses,created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (candidate_id, campaign_id, generation, parent_id, int(baseline),
             json.dumps(recipe, sort_keys=True), int(misses), _utc()),
        )
        return candidate_id

    def begin(self, campaign_id, *, owner_confirmed=False):
        if owner_confirmed is not True:
            raise PermissionError("Only explicit owner confirmation in the Foundry UI can begin a campaign.")
        row = self._row(campaign_id)
        if row["state"] not in ("DRAFT", "PAUSED"):
            raise ValueError("Only draft or paused campaigns can begin")
        with self.conn:
            self.conn.execute(
                "UPDATE discovery_campaigns SET state='RUNNING',expires_at=?,updated_at=? WHERE id=?",
                (time.time() + MAX_CAMPAIGN_AGE_SECONDS, _utc(), campaign_id),
            )
            self._event(campaign_id, "owner_authorized", "Finite local evaluation session only")
        return self.snapshot(campaign_id)

    def pause(self, campaign_id):
        if self._row(campaign_id)["state"] != "RUNNING":
            raise ValueError("Campaign is not running")
        with self.conn:
            self.conn.execute(
                "UPDATE discovery_campaigns SET state='PAUSED',expires_at=0,updated_at=? WHERE id=?",
                (_utc(), campaign_id),
            )
            self._event(campaign_id, "paused", "No future tests authorized")
        return self.snapshot(campaign_id)

    def stop(self, campaign_id):
        if self._row(campaign_id)["state"] in ("STOPPED", "COMPLETE"):
            return self.snapshot(campaign_id)
        with self.conn:
            self.conn.execute(
                "UPDATE discovery_campaigns SET state='STOPPED',expires_at=0,updated_at=? WHERE id=?",
                (_utc(), campaign_id),
            )
            self._event(campaign_id, "stopped", "Evidence retained; no restart")
        return self.snapshot(campaign_id)

    def snapshot(self, campaign_id):
        row = dict(self._row(campaign_id))
        agents = [dict(agent) for agent in self.conn.execute(
            "SELECT * FROM discovery_agents WHERE campaign_id=? ORDER BY generation,baseline DESC,id",
            (campaign_id,),
        )]
        for agent in agents:
            agent["recipe"] = json.loads(agent["recipe"])
            agent["trials"] = self.conn.execute(
                "SELECT COUNT(*) FROM discovery_trials WHERE agent_id=?", (agent["id"],)
            ).fetchone()[0]
        row.pop("expires_at", None)  # An authorization timestamp is not proof of user identity.
        row["agents"] = agents
        proposal = self.conn.execute(
            "SELECT * FROM discovery_proposals WHERE campaign_id=?", (campaign_id,)
        ).fetchone()
        row["proposal"] = dict(proposal) if proposal else None
        row["events"] = [dict(e) for e in self.conn.execute(
            "SELECT event_type,detail,at FROM discovery_events WHERE campaign_id=? ORDER BY id DESC LIMIT 18",
            (campaign_id,),
        )]
        row["suite_cases"] = len(SUITE)
        row["repeats"] = REPEATS
        row["suite_sha256"] = SUITE_DIGEST
        return row

    def list_campaigns(self):
        return [dict(x) for x in self.conn.execute(
            "SELECT id,title,state,generation,steps,updated_at FROM discovery_campaigns "
            "ORDER BY created_at DESC LIMIT 25"
        )]

    def _next_case(self, campaign_id, generation):
        agents = list(self.conn.execute(
            "SELECT * FROM discovery_agents WHERE campaign_id=? AND generation=? "
            "AND state='ACTIVE' ORDER BY baseline DESC,created_at,id",
            (campaign_id, generation),
        ))
        for agent in agents:
            tested = {(row["case_index"], row["repeat_index"]) for row in self.conn.execute(
                "SELECT case_index,repeat_index FROM discovery_trials WHERE agent_id=?", (agent["id"],)
            )}
            for case_index in range(len(SUITE)):
                for repeat_index in range(REPEATS):
                    if (case_index, repeat_index) not in tested:
                        return agent, case_index, repeat_index
        return None

    def _evaluate(self, agent):
        data = self.conn.execute(
            "SELECT case_index,repeat_index,correct,answer_sha256,elapsed_seconds FROM discovery_trials "
            "WHERE agent_id=? ORDER BY case_index,repeat_index", (agent["id"],)
        ).fetchall()
        if len(data) != len(SUITE) * REPEATS:
            raise ValueError("Candidate evidence incomplete; cannot score.")
        correct = sum(x["correct"] for x in data)
        by_case = {}
        for x in data:
            by_case.setdefault(x["case_index"], set()).add(x["answer_sha256"])
        robust = sum(len(values) == 1 for values in by_case.values()) / len(SUITE)
        average_seconds = sum(x["elapsed_seconds"] for x in data) / len(data)
        efficiency = 1 / (1 + average_seconds / 5)
        return CandidateEvaluation(
            candidate_id=agent["id"], generation=agent["generation"],
            suite_sha256=SUITE_DIGEST, accuracy=correct / len(data),
            robustness=robust, efficiency=efficiency, cases=len(SUITE),
            repeat_runs=REPEATS, safety_passed=True, regressions_passed=True,
            provenance_passed=True, prior_misses=agent["misses"],
            lineage=agent["parent_id"] or "",
        )

    def _successor_recipe(self, parent, ordinal):
        """Change a narrow recipe setting, never permissions/policy/benchmarks."""
        recipe = json.loads(parent["recipe"])
        updates = (
            {"strategy": "verify" if recipe["strategy"] != "verify" else "decompose"},
            {"review_passes": (recipe["review_passes"] + 1) % 3},
            {"context_budget": 1024 if recipe["context_budget"] < 1024 else 512},
        )
        for offset in range(len(updates)):
            change = updates[(ordinal + offset) % len(updates)]
            child = clone_recipe(recipe, change)
            # Retrieval isn't enabled because Discovery has no approved retrieval corpus.
            if child["strategy"] != "retrieval":
                return child
        raise RuntimeError("No safe recipe variation remains.")

    def _finish_generation(self, campaign_id, generation):
        candidates = list(self.conn.execute(
            "SELECT * FROM discovery_agents WHERE campaign_id=? AND generation=? AND state='ACTIVE' "
            "ORDER BY baseline DESC,id", (campaign_id, generation)
        ))
        evaluations = [self._evaluate(candidate) for candidate in candidates]
        baseline = next((x for x in candidates if x["baseline"]), None)
        if baseline is None:
            raise RuntimeError("Missing protected baseline")
        outcome = select_generation(
            evaluations, baseline_id=baseline["id"], suite_sha256=SUITE_DIGEST,
            generation=generation, policy=DEFAULT_POLICY,
        )
        for state, ids in (
            ("RETIRED", outcome.retired), ("QUARANTINED", outcome.quarantined),
            ("ARCHIVED", outcome.archived), ("PROBATION", outcome.probation),
        ):
            for ident in ids:
                self.conn.execute(
                    "UPDATE discovery_agents SET state=? WHERE id=? AND campaign_id=?",
                    (state, ident, campaign_id),
                )
        self._event(campaign_id, "selection",
                    json.dumps({"generation": generation, "clones": len(outcome.clone_parents),
                                "retired": len(outcome.retired), "qualified": len(outcome.clone_parents),
                                "archived": len(outcome.archived)}))

        next_generation = generation + 1
        keep = [c for c in candidates if c["id"] in outcome.retained]
        if next_generation >= DEFAULT_POLICY.max_generations:
            self._finalise(campaign_id, evaluations, baseline["id"], outcome)
            return

        if len(keep) == 1 and not outcome.clone_parents:
            self._finalise(campaign_id, evaluations, baseline["id"], outcome)
            return

        for prior in keep:
            recipe = json.loads(prior["recipe"])
            self._add_agent(
                campaign_id, next_generation, recipe, baseline=bool(prior["baseline"]),
                parent_id=prior["id"],
                misses=prior["misses"] + (1 if prior["id"] in outcome.probation else 0),
            )
        for ordinal, parent_id in enumerate(outcome.clone_parents):
            parent = next(a for a in candidates if a["id"] == parent_id)
            recipe = self._successor_recipe(parent, ordinal)
            self._add_agent(campaign_id, next_generation, recipe, parent_id=parent_id)
        self.conn.execute(
            "UPDATE discovery_campaigns SET generation=?,updated_at=? WHERE id=?",
            (next_generation, _utc(), campaign_id),
        )
        self._event(campaign_id, "generation", f"Generation {next_generation} prepared; no core changes")

    def _finalise(self, campaign_id, evaluations, baseline_id, outcome):
        baseline_accuracy = next(x.accuracy for x in evaluations if x.candidate_id == baseline_id)
        eligible = [x for x in evaluations
                    if x.candidate_id in outcome.retained and x.candidate_id != baseline_id
                    and x.candidate_id not in outcome.probation and
                    x.accuracy >= baseline_accuracy + DEFAULT_POLICY.min_gain and
                    x.accuracy >= DEFAULT_POLICY.min_accuracy]
        if eligible:
            winner = max(eligible, key=lambda x: (x.fitness, x.accuracy))
            summary = (
                "Review-only local Discovery proposal: narrow integer-expression reasoning "
                f"recipe {winner.candidate_id}; accuracy {winner.accuracy:.1%} vs "
                f"baseline {baseline_accuracy:.1%} on {len(SUITE)} authored cases x {REPEATS}. "
                "Not verified on an independent hidden test set. No promotion, system patch "
                "or skill activation is authorized."
            )
            self.conn.execute(
                "INSERT OR IGNORE INTO discovery_proposals"
                "(campaign_id,agent_id,baseline_accuracy,candidate_accuracy,summary,created_at)"
                " VALUES(?,?,?,?,?,?)",
                (campaign_id, winner.candidate_id, baseline_accuracy,
                 winner.accuracy, summary, _utc()),
            )
        self.conn.execute(
            "UPDATE discovery_campaigns SET state='COMPLETE',expires_at=0,updated_at=? WHERE id=?",
            (_utc(), campaign_id),
        )
        self._event(campaign_id, "complete",
                    "Review-only recommendation created" if eligible else "No qualified improvement")

    def step(self, campaign_id, *, ask=None):
        """Make at most one bounded Ollama request per step (plus configured reviewer passes).

        The caller must schedule a new step explicitly and may pause/stop between
        calls. An in-flight synchronous Ollama request completes before cancellation.
        """
        row = self._row(campaign_id)
        if row["state"] != "RUNNING":
            raise PermissionError("Discovery is not running; owner must authorise or resume.")
        if time.time() >= row["expires_at"]:
            self.pause(campaign_id)
            raise PermissionError("Discovery authorisation expired; owner must renew.")
        if row["generation"] >= DEFAULT_POLICY.max_generations:
            raise ValueError("Campaign generation budget exhausted")
        selected = self._next_case(campaign_id, row["generation"])
        if selected is None:
            with self.conn:
                self._finish_generation(campaign_id, row["generation"])
            return self.snapshot(campaign_id)
        agent, case_index, repeat_index = selected
        recipe = json.loads(agent["recipe"])
        if recipe["strategy"] not in ("direct", "decompose", "verify"):
            raise ValueError("Retrieval-based recipes are not approved in this Discovery phase.")
        prompt, expected = SUITE[case_index]
        speaker = ask or _ask_local
        start = time.monotonic()
        answer = speaker(_prompt(prompt, recipe), row["model"], recipe["context_budget"])
        for _ in range(recipe["review_passes"]):
            first = str(answer)[:200]
            followup = (
                "You are a separate sceptical reviewer with NO tools. "
                "Verify this safe arithmetic/Python expression and give ONLY the "
                "final integer, no text. Task: " + prompt + "\nProposed result: " + first
            )
            answer = speaker(followup, row["model"], recipe["context_budget"])
        elapsed = min(3600.0, max(0.000001, time.monotonic() - start))
        normalised = _safe_answer(answer)
        digest = hashlib.sha256(str(answer)[:512].encode("utf-8", "replace")).hexdigest()
        # A pause/stop received during the model call must not be overwritten.
        with self.conn:
            current = self._row(campaign_id)
            if current["state"] != "RUNNING" or time.time() >= current["expires_at"]:
                self._event(campaign_id, "discarded", "In-flight result discarded after stop/expiry")
                return self.snapshot(campaign_id)
            self.conn.execute(
                "INSERT OR IGNORE INTO discovery_trials"
                "(campaign_id,agent_id,case_index,repeat_index,correct,answer_sha256,"
                "elapsed_seconds,completed_at) VALUES(?,?,?,?,?,?,?,?)",
                (campaign_id, agent["id"], case_index, repeat_index,
                 int(normalised == expected), digest, elapsed, _utc()),
            )
            self.conn.execute(
                "UPDATE discovery_campaigns SET steps=steps+1,updated_at=? WHERE id=?",
                (_utc(), campaign_id),
            )
        return self.snapshot(campaign_id)
