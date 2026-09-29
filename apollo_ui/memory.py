import math
import re
import sqlite3
from collections import Counter
from pathlib import Path


TOKEN_RE = re.compile(r"[a-zA-Z0-9']+")


def tokenize(text):
    return TOKEN_RE.findall((text or "").lower())


def similarity(a, b):
    aa = Counter(tokenize(a))
    bb = Counter(tokenize(b))
    if not aa or not bb:
        return 0.0

    dot = sum(aa[k] * bb[k] for k in set(aa) & set(bb))
    ma = math.sqrt(sum(v * v for v in aa.values()))
    mb = math.sqrt(sum(v * v for v in bb.values()))
    if not ma or not mb:
        return 0.0
    return dot / (ma * mb)


class MemoryStore:
    def __init__(self, path):
        self.path = Path(path)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._setup()

    def _setup(self):
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS lessons(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                strength REAL NOT NULL DEFAULT 1.0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS facts(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS conversations(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_text TEXT NOT NULL,
                assistant_text TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()

    def teach(self, question, answer):
        question = question.strip()
        answer = answer.strip()
        cur = self.conn.cursor()

        existing = cur.execute(
            """
            SELECT id
            FROM lessons
            WHERE lower(question) = lower(?)
              AND lower(answer) = lower(?)
            LIMIT 1
            """,
            (question, answer),
        ).fetchone()

        if existing:
            return existing["id"]

        cur.execute(
            "INSERT INTO lessons(question, answer) VALUES (?, ?)",
            (question, answer)
        )
        self.conn.commit()
        return cur.lastrowid

    def remember(self, topic, content):
        topic = topic.strip()
        content = content.strip()
        cur = self.conn.cursor()

        existing = cur.execute(
            """
            SELECT id
            FROM facts
            WHERE lower(topic) = lower(?)
              AND lower(content) = lower(?)
            LIMIT 1
            """,
            (topic, content),
        ).fetchone()

        if existing:
            return existing["id"]

        cur.execute(
            "INSERT INTO facts(topic, content) VALUES (?, ?)",
            (topic, content)
        )
        self.conn.commit()
        return cur.lastrowid

    def add_conversation(self, user_text, assistant_text):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO conversations(user_text, assistant_text) VALUES (?, ?)",
            (user_text, assistant_text)
        )
        self.conn.commit()

    def context(self, query, limit=6):
        cur = self.conn.cursor()
        lessons = cur.execute("SELECT * FROM lessons").fetchall()
        facts = cur.execute("SELECT * FROM facts").fetchall()

        scored = []

        for row in lessons:
            score = similarity(query, row["question"])
            if score > 0.12:
                scored.append((
                    score,
                    f"Learned lesson:\nQ: {row['question']}\nA: {row['answer']}"
                ))

        for row in facts:
            score = similarity(query, row["topic"] + " " + row["content"])
            if row["topic"].lower() in query.lower():
                score += 0.3
            if score > 0.12:
                scored.append((
                    score,
                    f"Remembered fact:\n{row['topic']}: {row['content']}"
                ))

        scored.sort(key=lambda x: x[0], reverse=True)
        return "\n\n".join(text for _, text in scored[:limit])

    def stats(self):
        cur = self.conn.cursor()
        return {
            "lessons": cur.execute("SELECT COUNT(*) FROM lessons").fetchone()[0],
            "facts": cur.execute("SELECT COUNT(*) FROM facts").fetchone()[0],
            "conversations": cur.execute(
                "SELECT COUNT(*) FROM conversations"
            ).fetchone()[0],
        }

    def recent_memories(self, limit=8):
        cur = self.conn.cursor()
        rows = cur.execute("""
            SELECT 'lesson' AS kind, question AS title, answer AS body, created_at
            FROM lessons
            UNION ALL
            SELECT 'fact' AS kind, topic AS title, content AS body, created_at
            FROM facts
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]
