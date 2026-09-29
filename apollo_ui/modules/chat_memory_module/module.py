import math
import re
import sqlite3
from collections import Counter
from pathlib import Path


TOKEN_RE = re.compile(r"[a-zA-Z0-9']+")

RETRY_PHRASES = {
    "try again", "retry", "again", "do it again", "have another go",
    "try that again", "redo it", "retry that", "go again",
    "do it", "do that", "go ahead", "yes do it", "go for it",
    "make it", "build it", "create it",
}

TRIVIAL_USER_PHRASES = {
    "hi", "hello", "hey", "thanks", "thank you", "okay", "ok", "cool",
    "nice", "yep", "yes", "no",
}


def _tokens(text):
    return TOKEN_RE.findall((text or "").lower())


def _similarity(a, b):
    aa = Counter(_tokens(a))
    bb = Counter(_tokens(b))

    if not aa or not bb:
        return 0.0

    dot = sum(aa[k] * bb[k] for k in set(aa) & set(bb))
    ma = math.sqrt(sum(v * v for v in aa.values()))
    mb = math.sqrt(sum(v * v for v in bb.values()))

    if not ma or not mb:
        return 0.0

    return dot / (ma * mb)


class Module:
    """
    Apollo-compatible persistent chat memory.

    Runtime database:
        <Apollo>/storage/databases/chat_memory_module.db

    Validation uses SQLite :memory:, so validator tests do not pollute live memory.
    """

    def __init__(self, context=None):
        context = context or {}
        self.validation = bool(context.get("validation", False))
        self.base_dir = Path(context.get("base_dir", ".")).resolve()

        if self.validation:
            self.db_path = ":memory:"
        else:
            storage = self.base_dir / "storage"
            storage.mkdir(parents=True, exist_ok=True)
            self.db_path = str(storage / "databases" / "chat_memory_module.db")

        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._setup()

    def _setup(self):
        cur = self.conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS chat_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_text TEXT NOT NULL,
                assistant_text TEXT NOT NULL,
                tags TEXT DEFAULT '',
                importance REAL NOT NULL DEFAULT 1.0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self.conn.commit()

    def tools(self):
        return [
            {
                "name": "save_chat_memory",
                "description": (
                    "Save a useful user/assistant exchange into Apollo's persistent "
                    "local chat memory."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_text": {"type": "string"},
                        "assistant_text": {"type": "string"},
                        "tags": {"type": "string"},
                        "importance": {"type": "number"}
                    },
                    "required": ["user_text", "assistant_text"]
                }
            },
            {
                "name": "search_chat_memory",
                "description": (
                    "Search Apollo's stored conversation memories for exchanges "
                    "relevant to a query."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer"}
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "recent_chat_memories",
                "description": "Return Apollo's most recent persistent chat memories.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer"}
                    }
                }
            },
            {
                "name": "conversation_context",
                "description": (
                    "Return a compact persistent conversation context containing recent exchanges "
                    "in chronological order plus older exchanges relevant to the current query."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "recent_limit": {"type": "integer"},
                        "related_limit": {"type": "integer"},
                        "max_chars": {"type": "integer"}
                    }
                }
            },
            {
                "name": "previous_user_request",
                "description": (
                    "Return the most recent meaningful user request from persistent conversation memory, "
                    "skipping retry phrases and trivial acknowledgements."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer"},
                        "skip_text": {"type": "string"}
                    }
                }
            },
            {
                "name": "chat_memory_stats",
                "description": "Return statistics for Apollo's persistent chat memory.",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        ]

    @staticmethod
    def _limit(value, default=5):
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = default
        return max(1, min(value, 25))

    def _save(self, user_text, assistant_text, tags="", importance=1.0):
        user_text = str(user_text or "").strip()
        assistant_text = str(assistant_text or "").strip()
        tags = str(tags or "").strip()

        if not user_text:
            raise ValueError("user_text cannot be empty.")
        if not assistant_text:
            raise ValueError("assistant_text cannot be empty.")

        try:
            importance = float(importance)
        except (TypeError, ValueError):
            importance = 1.0

        importance = max(0.1, min(importance, 10.0))

        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO chat_memories(
                user_text, assistant_text, tags, importance
            )
            VALUES (?, ?, ?, ?)
            """,
            (user_text, assistant_text, tags, importance),
        )
        self.conn.commit()

        return {
            "saved": True,
            "memory_id": cur.lastrowid,
            "importance": importance,
        }

    def _search(self, query, limit=5):
        query = str(query or "").strip()
        if not query:
            raise ValueError("query cannot be empty.")

        limit = self._limit(limit)

        rows = self.conn.execute(
            """
            SELECT id, user_text, assistant_text, tags, importance, created_at
            FROM chat_memories
            ORDER BY id DESC
            """
        ).fetchall()

        scored = []

        for row in rows:
            searchable = " ".join([
                row["user_text"],
                row["assistant_text"],
                row["tags"] or "",
            ])

            score = _similarity(query, searchable)
            score *= max(0.1, float(row["importance"]))

            if query.lower() in searchable.lower():
                score += 0.25

            if score > 0:
                scored.append((score, row))

        scored.sort(key=lambda item: item[0], reverse=True)

        output = []
        for score, row in scored[:limit]:
            output.append({
                "memory_id": row["id"],
                "user_text": row["user_text"],
                "assistant_text": row["assistant_text"],
                "tags": row["tags"],
                "importance": row["importance"],
                "created_at": row["created_at"],
                "relevance": round(score, 4),
            })

        return output

    def _recent(self, limit=5):
        limit = self._limit(limit)
        rows = self.conn.execute(
            """
            SELECT id, user_text, assistant_text, tags, importance, created_at
            FROM chat_memories
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        return [
            {
                "memory_id": row["id"],
                "user_text": row["user_text"],
                "assistant_text": row["assistant_text"],
                "tags": row["tags"],
                "importance": row["importance"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    @staticmethod
    def _clean_phrase(text):
        return " ".join(str(text or "").lower().split()).strip(" .!?\t\r\n")

    @classmethod
    def _is_retry_phrase(cls, text):
        return cls._clean_phrase(text) in RETRY_PHRASES

    @classmethod
    def _is_meaningful_user_request(cls, text):
        cleaned = cls._clean_phrase(text)
        if not cleaned:
            return False
        if cleaned in RETRY_PHRASES or cleaned in TRIVIAL_USER_PHRASES:
            return False
        return len(cleaned) >= 3

    def _previous_user_request(self, limit=50, skip_text=""):
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 50
        limit = max(1, min(limit, 250))
        skip_clean = self._clean_phrase(skip_text)
        rows = self.conn.execute(
            """
            SELECT id, user_text, assistant_text, tags, importance, created_at
            FROM chat_memories
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        for row in rows:
            user_text = str(row["user_text"] or "").strip()
            cleaned = self._clean_phrase(user_text)
            if skip_clean and cleaned == skip_clean:
                continue
            if not self._is_meaningful_user_request(user_text):
                continue
            return {
                "found": True,
                "memory_id": row["id"],
                "user_text": user_text,
                "assistant_text": row["assistant_text"],
                "tags": row["tags"],
                "importance": row["importance"],
                "created_at": row["created_at"],
            }

        return {"found": False, "user_text": "", "assistant_text": ""}

    def _conversation_context(self, query="", recent_limit=6, related_limit=4, max_chars=9000):
        try:
            recent_limit = int(recent_limit)
        except (TypeError, ValueError):
            recent_limit = 6
        try:
            related_limit = int(related_limit)
        except (TypeError, ValueError):
            related_limit = 4
        try:
            max_chars = int(max_chars)
        except (TypeError, ValueError):
            max_chars = 9000

        recent_limit = max(1, min(recent_limit, 20))
        related_limit = max(0, min(related_limit, 20))
        max_chars = max(1200, min(max_chars, 24000))

        recent = list(reversed(self._recent(recent_limit)))
        recent_ids = {item.get("memory_id") for item in recent}

        related = []
        if str(query or "").strip() and related_limit:
            for item in self._search(query, related_limit + recent_limit):
                if item.get("memory_id") in recent_ids:
                    continue
                related.append(item)
                if len(related) >= related_limit:
                    break

        def compact(item, per_side=1200):
            return {
                "memory_id": item.get("memory_id"),
                "user_text": str(item.get("user_text", ""))[:per_side],
                "assistant_text": str(item.get("assistant_text", ""))[:per_side],
                "created_at": item.get("created_at", ""),
                "relevance": item.get("relevance"),
            }

        recent_compact = [compact(item) for item in recent]
        related_compact = [compact(item) for item in related]

        def payload_size():
            return sum(
                len(item.get("user_text", "")) + len(item.get("assistant_text", ""))
                for item in recent_compact + related_compact
            )

        while payload_size() > max_chars:
            if related_compact:
                related_compact.pop()
            elif len(recent_compact) > 2:
                recent_compact.pop(0)
            else:
                break

        return {
            "recent": recent_compact,
            "related": related_compact,
            "recent_count": len(recent_compact),
            "related_count": len(related_compact),
            "max_chars": max_chars,
        }

    def _stats(self):
        row = self.conn.execute(
            """
            SELECT
                COUNT(*) AS count,
                COALESCE(AVG(importance), 0) AS avg_importance
            FROM chat_memories
            """
        ).fetchone()

        return {
            "memory_count": int(row["count"]),
            "average_importance": round(float(row["avg_importance"]), 3),
            "storage": (
                "in-memory validation database"
                if self.validation
                else self.db_path
            ),
        }

    def self_test(self):
        before = self._stats()["memory_count"]

        saved = self._save(
            "What is Apollo?",
            "Apollo is a modular local AI assistant.",
            "apollo,test",
            1.0,
        )
        assert saved["saved"] is True

        found = self._search("Apollo modular AI", 3)
        assert found
        assert "modular local AI" in found[0]["assistant_text"]

        recent = self._recent(3)
        assert recent

        context = self._conversation_context("Apollo modular", 3, 2, 4000)
        assert context["recent"]

        previous = self._previous_user_request(10)
        assert previous["found"] is True
        assert previous["user_text"] == "What is Apollo?"

        after = self._stats()["memory_count"]
        assert after == before + 1

        return "Persistent chat memory save/search/recent/stats tests passed."

    def run(self, action, arguments):
        arguments = arguments or {}

        if action == "save_chat_memory":
            return self._save(
                arguments.get("user_text"),
                arguments.get("assistant_text"),
                arguments.get("tags", ""),
                arguments.get("importance", 1.0),
            )

        if action == "search_chat_memory":
            return self._search(
                arguments.get("query"),
                arguments.get("limit", 5),
            )

        if action == "recent_chat_memories":
            return self._recent(arguments.get("limit", 5))

        if action == "conversation_context":
            return self._conversation_context(
                arguments.get("query", ""),
                arguments.get("recent_limit", 6),
                arguments.get("related_limit", 4),
                arguments.get("max_chars", 9000),
            )

        if action == "previous_user_request":
            return self._previous_user_request(
                arguments.get("limit", 50),
                arguments.get("skip_text", ""),
            )

        if action == "chat_memory_stats":
            return self._stats()

        raise KeyError(f"Unknown action: {action}")

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass
