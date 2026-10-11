"""Apollo v8 learning control: bounded follow-ups and evidence indexing.

This is not model-weight training. Offline reminders are the default.
Automatic public-web research requires the user to enable it explicitly.
"""
import json
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path


def utc_now():
    return datetime.now(timezone.utc)


def iso(moment):
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def knowledge_query(message):
    """Extract a subject from natural-language knowledge questions."""
    text = " ".join(str(message or "").split()).strip(" ?!.\n\r\t")
    patterns = (
        r"^(?:what (?:is|are|was|were)|who (?:is|was))\s+(.+)$",
        r"^(?:what (?:can|could|does) )(.+?)(?: do(?: for me| for us)?| offer(?: me)?)$",
        r"^(?:how (?:can|could|would) )(.+?)(?: help me| help us| work for me)$",
        r"^(?:tell me (?:about|what you know about)|explain|describe)\s+(.+)$",
        r"^(?:what do you know about|search (?:your |the )?(?:knowledge base|memory) (?:for|about))\s+(.+)$",
    )
    for pattern in patterns:
        match = re.match(pattern, text, re.IGNORECASE)
        if match:
            subject = match.group(1).strip(" :,.?!")
            if 2 <= len(subject) <= 160:
                return subject
    return text[:180]


class LearningController:
    """Persistent schedule + source-backed research bookkeeping.

    Scheduling only selects work. The caller must supply a separately
    permissioned research executor; no arbitrary code is ever run here.
    """

    MODES = ("manual", "remind", "auto")

    def __init__(self, base_dir, store):
        self.store = store
        self.path = Path(base_dir).resolve() / "storage" / "state" / "learning_v8.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def _read(self):
        defaults = dict(mode="manual", interval_hours=24, review_days=7,
                        next_run="", last_run="", last_message="",
                        last_question_id=None)
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                defaults.update({key: value[key] for key in defaults if key in value})
        except (OSError, ValueError, TypeError):
            pass
        if defaults["mode"] not in self.MODES:
            defaults["mode"] = "manual"
        try:
            defaults["interval_hours"] = max(1, min(int(defaults["interval_hours"]), 720))
            defaults["review_days"] = max(1, min(int(defaults["review_days"]), 365))
        except (ValueError, TypeError):
            defaults["interval_hours"], defaults["review_days"] = 24, 7
        return defaults

    def _write(self, data):
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def status(self):
        with self.lock:
            info = self._read()
        info["due_questions"] = len(self.store.due_questions(limit=50))
        info["active_topics"] = len(self.store.list_topics(limit=100))
        return info

    def configure(self, mode, interval_hours=24, review_days=7, now=None):
        if mode not in self.MODES:
            raise ValueError("Choose manual, remind or auto.")
        interval_hours = int(interval_hours)
        review_days = int(review_days)
        if not 1 <= interval_hours <= 720 or not 1 <= review_days <= 365:
            raise ValueError("Interval must be 1-720 hours and review 1-365 days.")
        now = now or utc_now()
        with self.lock:
            state = self._read()
            state.update(mode=mode, interval_hours=interval_hours,
                         review_days=review_days,
                         next_run=iso(now + timedelta(hours=interval_hours)),
                         last_message=("Automatic research enabled by user."
                                       if mode == "auto" else "Follow-up preference saved."))
            self._write(state)
            return dict(state)

    def reserve_due(self, now=None):
        """Deduplicate timer invocations and reserve at most one item per tick."""
        now = now or utc_now()
        with self.lock:
            state = self._read()
            if state["mode"] == "manual":
                return {"action": "disabled"}
            try:
                scheduled = datetime.fromisoformat(state["next_run"])
                if scheduled.tzinfo is None:
                    scheduled = scheduled.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                scheduled = now
            if scheduled > now:
                return {"action": "waiting", "next_run": iso(scheduled)}
            due = self.store.due_questions(limit=1, as_of=now)
            state["next_run"] = iso(now + timedelta(hours=state["interval_hours"]))
            state["last_run"] = iso(now)
            if not due:
                state["last_message"] = "No research questions due."
                self._write(state)
                return {"action": "none_due"}
            question = due[0]
            state["last_question_id"] = question["id"]
            if state["mode"] == "remind":
                state["last_message"] = "Research due: " + question["prompt"][:160]
                self._write(state)
                return {"action": "reminder", "question": question}
            state["last_message"] = "Research started: " + question["prompt"][:160]
            self._write(state)
            return {"action": "research", "question": question,
                    "review_days": state["review_days"]}

    def complete_research(self, question_id, result, review_days=7):
        """Only a fetched source constitutes a successful research attempt.

        A local file is indexed for later retrieval; source text is *not*
        promoted to a verified answer or a model instruction.
        """
        if not isinstance(result, dict):
            raise ValueError("Research returned no result.")
        count = int(result.get("source_pages_fetched") or 0)
        saved = result.get("saved") or {}
        filename = str(saved.get("filename") or "").strip()
        if count <= 0 or not saved.get("saved") or not filename:
            raise ValueError("No source pages fetched; leave question due and retry manually.")
        if not filename.startswith("reasoning_topics/"):
            raise ValueError("Unexpected research storage location.")
        record = self.store.record_research(
            question_id,
            (f"Apollo fetched {count} public source page(s), saved in {filename}. "
             "Original source text requires independent checking; no factual conclusion was verified."),
            filename, "personal_note", "unverified", int(review_days)
        )
        with self.lock:
            state = self._read()
            state["last_message"] = f"Saved {count} source pages for question #{question_id}."
            self._write(state)
        return {"evidence": record, "filename": filename,
                "source_pages_fetched": count, "verified": False}

    def fail(self, error):
        with self.lock:
            state = self._read()
            state["last_message"] = "Research failed: " + str(error)[:240]
            self._write(state)

    def suggestions(self):
        """Explainable, evidence-based suggestions, never automatic upgrades."""
        info = self.status()
        items = []
        if info["due_questions"]:
            items.append({
                "title": "Reduce overdue research",
                "why": f"{info['due_questions']} research questions need investigation or revision.",
                "next": "Research one due question and save source evidence.",
                "files": ["modules/reasoning_director/module.py"],
            })
        if info["mode"] == "manual":
            items.append({
                "title": "Enable research reminders",
                "why": "Follow-ups are currently manual.",
                "next": "Set a repeat interval in Learning; automatic browsing stays off until enabled.",
                "files": ["apollo_learning_v8.py"],
            })
        progress = self.store.progress()
        weak = [s for s in progress["skills"] if s["attempts"] >= 3 and s["practice_accuracy_pct"] < 75]
        if weak:
            area = sorted(weak, key=lambda s: s["practice_accuracy_pct"])[0]
            items.append({
                "title": "Strengthen " + area["skill"] + " reasoning",
                "why": f"Only {area['practice_accuracy_pct']}% correct in {area['attempts']} fixed practice attempts.",
                "next": "Compare direct and reviewed answers against new holdout tasks before changing prompts.",
                "files": ["apollo_reasoning.py"],
            })
        if not items:
            items.append({
                "title": "Check knowledge quality",
                "why": "No urgent learning gaps found in recorded results.",
                "next": "Select a new topic and collect reproducible source evidence.",
                "files": ["modules/reasoning_director/module.py"],
            })
        return items[:5]
