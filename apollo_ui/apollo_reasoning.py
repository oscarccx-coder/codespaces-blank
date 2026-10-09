"""Apollo Learning & Reasoning Director, offline-first and evidence-aware.

It tracks research topics/questions and measures a bounded reasoning practice
set. It does NOT claim to retrain the LLM, browse unattended, run shell code,
accept jobs, change model parameters or promote web text into verified facts.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import re
import sqlite3
import threading
import time

MAX_TOPICS = 250
MAX_QUESTIONS_PER_TOPIC = 12
MAX_ATTEMPTS = 3000
QUESTIONS = (
    {"id": "electronics_01", "skill": "quantitative", "question": "A 5V supply drives a 2V LED at 10mA. Calculate the theoretical series resistance in ohms. Respond with a number.", "answers": ("300", "300 ohm", "300 ohms", "300 ω"), "explain": "Ohm's law: (5-2)V / 0.01A = 300 ohms. Choose a standard resistor at least this large."},
    {"id": "electronics_02", "skill": "quantitative", "question": "The exact theoretical resistance is 300 ohms. Which next higher E12 series resistor should be selected in ohms?", "answers": ("330", "330 ohms", "330 ohm", "330 ω"), "explain": "E12 values around 300 are 270 and 330 ohms. Use 330 to keep LED current below target."},
    {"id": "inference_01", "skill": "logical", "question": "All A are B. Some B are C. Is it logically certain that some A are C? Answer yes or no.", "answers": ("no",), "explain": "The intersection B∩C need not overlap A, even if all A belong to B."},
    {"id": "inference_02", "skill": "logical", "question": "If an experiment has no control group, can it by itself conclusively establish causation? Answer yes or no.", "answers": ("no",), "explain": "There are plausible confounders and alternative explanations without an appropriate comparison."},
    {"id": "verification_01", "skill": "evidence", "question": "Two websites copy the same press release. Do they provide two independent confirmations? Answer yes or no.", "answers": ("no",), "explain": "Both derive from one upstream source. Independent corroboration has not increased."},
    {"id": "verification_02", "skill": "evidence", "question": "A Python program parses with no syntax errors. Does this guarantee its business logic is correct? Answer yes or no.", "answers": ("no",), "explain": "Syntax checks do not prove intended behavior or performance. Functional tests are needed."},
    {"id": "finance_01", "skill": "planning", "question": "A software job pays £125. Materials cost £35 and you work 2 hours valued at £20 per hour. Calculate the remainder in pounds before fees and tax. Answer a number.", "answers": ("50", "50.00", "£50", "£50.00"), "explain": "125 - 35 - (2×20) = 50 pounds. This is not necessarily business profit."},
    {"id": "rates_01", "skill": "quantitative", "question": "A local model generates 84 output tokens in 7 seconds. What is its output tokens/second rate? Answer a number.", "answers": ("12", "12.0"), "explain": "84/7 = 12 output tokens per second. Measure on the actual hardware."},
    {"id": "code_01", "skill": "programming", "question": "In Python, what common problem occurs when defining def f(items=[]): and modifying items? Answer with the core issue name.", "answers": ("mutable default argument", "shared mutable default", "shared mutable default argument", "mutable default"), "explain": "The same mutable default list persists across calls, creating accidental shared state."},
    {"id": "units_01", "skill": "quantitative", "question": "Exactly how many bytes are in one MiB? Answer an integer.", "answers": ("1048576", "1,048,576"), "explain": "A mebibyte is 2^20 bytes, not 10^6 bytes."},
    {"id": "models_01", "skill": "evidence", "question": "A model scores 8/10 on one tiny test and 9/10 on the next. Is that enough evidence to prove broad reasoning improvement? Yes or no.", "answers": ("no",), "explain": "This small, non-controlled test has high sampling variability and can be memorized."},
    {"id": "safety_01", "skill": "planning", "question": "Should Apollo count a drafted invoice as money already received in its hardware fund? Answer yes or no.", "answers": ("no",), "explain": "Revenue is not confirmed by a quote or invoice. A payment must be independently verified by its owner."},
)
QUESTION_MAP = {q["id"]: q for q in QUESTIONS}

def utc_now():
    return datetime.now(timezone.utc)

def iso(value=None):
    return (value or utc_now()).astimezone(timezone.utc).isoformat(timespec="seconds")

def clean(value, *, limit=240, minimum=1):
    text = " ".join(str(value or "").split())
    if not minimum <= len(text) <= limit or any(ord(x) < 32 for x in text):
        raise ValueError(f"Text must be {minimum}-{limit} printable characters.")
    return text

def simplified(value):
    return re.sub(r"\s+", " ", str(value or "").strip().lower())

def grade(challenge_id, response):
    task = QUESTION_MAP.get(str(challenge_id))
    if not task:
        raise KeyError("Unknown benchmark task")
    text = str(response or "").strip()
    finals = re.findall(r"(?im)^\s*final\s*:\s*(.+?)\s*$", text)
    answer = (finals[-1] if finals else text).strip()
    normalized = simplified(answer).strip(" .!")
    return {
        "id": task["id"], "skill": task["skill"],
        "passed": normalized in {simplified(x) for x in task["answers"]},
        "submitted": answer[:240],
        "expected_explanation": task["explain"],
        "grader": "deterministic exact match; narrow practice checks, not human-level reasoning assessment",
    }

def due_at(now=None, days=7):
    return iso((now or utc_now()) + timedelta(days=days))

class ReasoningStore:
    def __init__(self, base_dir):
        root = Path(base_dir).resolve() / "storage" / "databases"
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "apollo_reasoning.db"
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(self.path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self.db:
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS topics(
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    purpose TEXT NOT NULL,
                    priority INTEGER NOT NULL CHECK(priority BETWEEN 1 AND 5),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    next_review TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'active'
                        CHECK(state IN ('active','paused','archived'))
                );
                CREATE TABLE IF NOT EXISTS questions(
                    id INTEGER PRIMARY KEY,
                    topic_id INTEGER NOT NULL REFERENCES topics(id),
                    prompt TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'open'
                        CHECK(state IN ('open','researched','revisit')),
                    created_at TEXT NOT NULL,
                    next_review TEXT NOT NULL,
                    UNIQUE(topic_id,prompt)
                );
                CREATE TABLE IF NOT EXISTS research(
                    id INTEGER PRIMARY KEY,
                    question_id INTEGER NOT NULL REFERENCES questions(id),
                    summary TEXT NOT NULL,
                    source TEXT NOT NULL,
                    evidence_type TEXT NOT NULL
                        CHECK(evidence_type IN ('public_source','personal_note','experiment')),
                    confidence TEXT NOT NULL
                        CHECK(confidence IN ('unverified','supported','disputed')),
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS practice(
                    id INTEGER PRIMARY KEY,
                    challenge_id TEXT NOT NULL,
                    skill TEXT NOT NULL,
                    model TEXT NOT NULL,
                    method TEXT NOT NULL CHECK(method IN ('direct','self_review','manual')),
                    passed INTEGER NOT NULL CHECK(passed IN (0,1)),
                    response TEXT NOT NULL,
                    elapsed_seconds REAL,
                    output_tokens INTEGER,
                    output_tokens_per_second REAL,
                    recorded_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS topics_due ON topics(next_review,state);
                CREATE INDEX IF NOT EXISTS questions_due ON questions(next_review,state);
                CREATE INDEX IF NOT EXISTS practice_skill ON practice(skill, recorded_at);
            """)

    def close(self):
        with self.lock:
            self.db.close()

    def propose_topic(self, name, purpose, priority=3):
        name = clean(name, limit=110, minimum=3)
        purpose = clean(purpose, limit=1200, minimum=12)
        priority = int(priority)
        if not 1 <= priority <= 5:
            raise ValueError("Priority must be between 1 and 5")
        with self.lock, self.db:
            existing = self.db.execute(
                "SELECT id FROM topics WHERE name=? COLLATE NOCASE", (name,)
            ).fetchone()
            if existing:
                return {"created": False, "id": existing["id"],
                        "note": "Already in learning queue; original notes are preserved."}
            if self.db.execute("SELECT count(*) FROM topics").fetchone()[0] >= MAX_TOPICS:
                raise ValueError("Research topic queue full. Review older topics first.")
            moment = iso()
            cur = self.db.execute(
                "INSERT INTO topics(name,purpose,priority,created_at,updated_at,next_review)"
                " VALUES(?,?,?,?,?,?)", (name, purpose, priority, moment, moment, moment)
            )
            return {"created": True, "id": cur.lastrowid, "state": "active"}

    def topic(self, topic_id):
        with self.lock:
            r = self.db.execute("SELECT * FROM topics WHERE id=?", (int(topic_id),)).fetchone()
            if not r:
                raise KeyError("Learning topic not found")
            return dict(r)

    def list_topics(self, *, include_archived=False, limit=50):
        with self.lock:
            limit = max(1, min(int(limit), 100))
            where = "" if include_archived else "WHERE state='active'"
            rows = self.db.execute(
                f"SELECT * FROM topics {where} ORDER BY priority DESC,next_review,id LIMIT ?",
                (limit,)
            ).fetchall()
            return [dict(x) for x in rows]

    def questions_for(self, topic_id):
        with self.lock:
            rows = self.db.execute(
                "SELECT * FROM questions WHERE topic_id=? ORDER BY id",
                (int(topic_id),)
            ).fetchall()
            return [dict(r) for r in rows]

    def suggest_questions(self, topic_id):
        """Deterministic curiosity prompts, not unverified model-generated facts."""
        topic = self.topic(topic_id)
        phrase = topic["name"]
        stems = (
            f"What are the essential concepts and reliable primary sources for {phrase}?",
            f"What observations or tests would disprove a common assumption about {phrase}?",
            f"How could we apply {phrase} in a small, measurable Apollo project?",
            f"Which parts of our existing knowledge about {phrase} may be outdated or contradictory?",
        )
        created = []
        for prompt in stems:
            created.append(self.add_question(topic_id, prompt))
        return {"topic_id": int(topic_id), "questions": created}

    def add_question(self, topic_id, question):
        question = clean(question, limit=600, minimum=15)
        topic = self.topic(topic_id)
        if topic["state"] != "active":
            raise ValueError("Only active topics can accept research questions")
        with self.lock, self.db:
            row = self.db.execute(
                "SELECT id FROM questions WHERE topic_id=? AND prompt=?",
                (int(topic_id), question)
            ).fetchone()
            if row:
                return {"id": row["id"], "created": False}
            count = self.db.execute(
                "SELECT count(*) FROM questions WHERE topic_id=?", (int(topic_id),)
            ).fetchone()[0]
            if count >= MAX_QUESTIONS_PER_TOPIC:
                raise ValueError("Question limit reached for this topic")
            moment = iso()
            cur = self.db.execute(
                "INSERT INTO questions(topic_id,prompt,created_at,next_review)"
                " VALUES(?,?,?,?)", (int(topic_id), question, moment, moment)
            )
            return {"id": cur.lastrowid, "created": True}

    def due_questions(self, limit=12, as_of=None):
        now = iso(as_of) if as_of else iso()
        with self.lock:
            rows = self.db.execute(
                "SELECT q.*,t.name topic,t.priority FROM questions q "
                "JOIN topics t ON t.id=q.topic_id "
                "WHERE t.state='active' AND q.next_review<=? "
                "ORDER BY t.priority DESC,q.next_review ASC LIMIT ?",
                (now, max(1, min(int(limit), 50)))
            ).fetchall()
            return [dict(x) for x in rows]

    def record_research(self, question_id, summary, source, evidence_type,
                        confidence="unverified", review_days=7):
        """A citation/note can be recorded; no source is silently 'verified'."""
        summary = clean(summary, limit=4000, minimum=20)
        source = clean(source, limit=1000, minimum=4)
        if evidence_type not in {"public_source", "personal_note", "experiment"}:
            raise ValueError("Unsupported evidence type")
        if evidence_type == "public_source":
            from urllib.parse import urlsplit
            url = urlsplit(source)
            if url.scheme != "https" or not url.hostname or url.username or url.password:
                raise ValueError("Public source must be an HTTPS URL")
        if confidence not in {"unverified", "supported", "disputed"}:
            raise ValueError("Invalid confidence label")
        review_days = int(review_days)
        if not 1 <= review_days <= 365:
            raise ValueError("Review interval must be 1-365 days")
        with self.lock, self.db:
            q = self.db.execute(
                "SELECT q.*,t.state topic_state FROM questions q "
                "JOIN topics t ON t.id=q.topic_id WHERE q.id=?", (int(question_id),)
            ).fetchone()
            if not q or q["topic_state"] != "active":
                raise ValueError("Active question is required")
            cur = self.db.execute(
                "INSERT INTO research(question_id,summary,source,evidence_type,confidence,created_at)"
                " VALUES(?,?,?,?,?,?)",
                (int(question_id), summary, source, evidence_type, confidence, iso())
            )
            self.db.execute(
                "UPDATE questions SET state='researched',next_review=? WHERE id=?",
                (due_at(days=review_days), int(question_id))
            )
            self.db.execute(
                "UPDATE topics SET updated_at=?,next_review=? WHERE id=?",
                (iso(), due_at(days=review_days), int(q["topic_id"]))
            )
            return {
                "id": cur.lastrowid, "question_id": int(question_id),
                "status": "saved_for_review", "confidence": confidence,
                "proof_of_correctness": False,
            }

    def research_for(self, question_id):
        with self.lock:
            rows = self.db.execute(
                "SELECT * FROM research WHERE question_id=? ORDER BY id DESC LIMIT 25",
                (int(question_id),)
            ).fetchall()
            return [dict(x) for x in rows]

    def practice_questions(self, limit=3, skill=None):
        challenges = [dict(id=q["id"], skill=q["skill"], question=q["question"])
                      for q in QUESTIONS if skill is None or q["skill"] == skill]
        return challenges[:max(1, min(int(limit), len(challenges)))]

    def save_attempt(self, challenge_id, response, model="manual", method="manual",
                     elapsed_seconds=None, output_tokens=None, output_duration_ns=None):
        if method not in {"direct", "self_review", "manual"}:
            raise ValueError("Unsupported practice mode")
        model = clean(model, limit=120)
        response = str(response or "").strip()
        if len(response) > 6000 or not response:
            raise ValueError("Practice answer must be 1-6000 characters")
        graded = grade(challenge_id, response)
        seconds = float(elapsed_seconds) if elapsed_seconds is not None else None
        if seconds is not None and not 0 <= seconds <= 3600:
            raise ValueError("Invalid latency")
        tokens, throughput = None, None
        if output_tokens is not None and output_duration_ns is not None:
            tokens = int(output_tokens)
            duration = int(output_duration_ns)
            if tokens >= 0 and duration > 0:
                throughput = round(tokens * 1e9 / duration, 2)
            else:
                tokens = None
        with self.lock, self.db:
            count = self.db.execute("SELECT COUNT(*) FROM practice").fetchone()[0]
            if count >= MAX_ATTEMPTS:
                self.db.execute(
                    "DELETE FROM practice WHERE id IN "
                    "(SELECT id FROM practice ORDER BY id LIMIT 50)"
                )
            cur = self.db.execute(
                "INSERT INTO practice(challenge_id,skill,model,method,passed,response,"
                "elapsed_seconds,output_tokens,output_tokens_per_second,recorded_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (challenge_id, graded["skill"], model, method,
                 int(graded["passed"]), response[:6000], seconds,
                 tokens, throughput, iso())
            )
            return {"attempt_id": cur.lastrowid, **graded,
                    "output_tokens_per_second": throughput}

    def progress(self):
        with self.lock:
            by_skill = self.db.execute(
                "SELECT skill,count(*) attempts,sum(passed) correct "
                "FROM practice GROUP BY skill ORDER BY skill"
            ).fetchall()
            latest = self.db.execute(
                "SELECT challenge_id,model,method,passed,recorded_at,"
                "output_tokens_per_second FROM practice ORDER BY id DESC LIMIT 30"
            ).fetchall()
            by_mode = self.db.execute(
                "SELECT model,method,count(*) n,sum(passed) correct "
                "FROM practice GROUP BY model,method ORDER BY model,method"
            ).fetchall()
            n_topics = self.db.execute(
                "SELECT count(*) FROM topics WHERE state='active'"
            ).fetchone()[0]
        return {
            "active_topics": n_topics, "due": len(self.due_questions(limit=50)),
            "skills": [{
                "skill": x["skill"], "attempts": x["attempts"],
                "correct": x["correct"],
                "practice_accuracy_pct": round(x["correct"] * 100 / x["attempts"], 1),
            } for x in by_skill],
            "methods": [dict(x) for x in by_mode],
            "recent": [dict(x) for x in latest],
            "warning": "Practice scores on a small fixed set can improve from familiarity. "
                       "They are not proof of general reasoning gains, AI training or real earnings.",
        }


def practice_prompt(task):
    return [
        {"role": "system", "content": (
            "You are Apollo, practising concise, checkable reasoning. "
            "Do not browse, call tools or claim to have tested anything. "
            "Verify units and distinguish assumptions from facts. "
            "Explain in at most three short sentences, then finish with one line "
            "formatted FINAL: <short answer>. Do not make up missing information."
        )},
        {"role": "user", "content": task["question"]},
    ]


def run_practice(client, store, *, limit=3, review=False):
    """Opt-in local practice loop; no model weight updates or background scheduler."""
    results = []
    for challenge in store.practice_questions(limit):
        start = time.monotonic()
        first = client.chat_once(practice_prompt(challenge))
        first_text = str((first.get("message") or {}).get("content") or "").strip()
        if not first_text:
            raise ValueError("Local model returned an empty practice answer")
        final = first
        text = first_text
        if review:
            followup = [
                *practice_prompt(challenge),
                {"role": "assistant", "content": first_text},
                {"role": "user", "content": (
                    "Critically check your answer for arithmetic, units, logical entailment "
                    "and evidence quality. If mistaken, correct it. "
                    "Give a short verification and finish FINAL: <short answer>."
                )},
            ]
            final = client.chat_once(followup)
            text = str((final.get("message") or {}).get("content") or "").strip()
            if not text:
                raise ValueError("Review pass returned an empty answer")
        results.append(store.save_attempt(
            challenge["id"], text, model=client.model,
            method="self_review" if review else "direct",
            elapsed_seconds=round(time.monotonic() - start, 3),
            output_tokens=final.get("eval_count"),
            output_duration_ns=final.get("eval_duration"),
        ))
    return {"completed": len(results), "mode": "self_review" if review else "direct",
            "results": results, "progress": store.progress()}
