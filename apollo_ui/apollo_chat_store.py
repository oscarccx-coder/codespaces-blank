"""Local chat/project persistence. Temporary work uses a separate :memory: store."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading
import uuid


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ChatStore:
    def __init__(self, base_dir, temporary=False):
        self.temporary = bool(temporary)
        self.lock = threading.RLock()
        path = Path(base_dir) / "storage" / "databases" / "chat_workspace.db"
        if not temporary:
            path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(":memory:" if temporary else str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            PRAGMA foreign_keys=ON;
            PRAGMA secure_delete=ON;
            CREATE TABLE IF NOT EXISTS projects(
                id TEXT PRIMARY KEY,title TEXT NOT NULL,instructions TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS chats(
                id TEXT PRIMARY KEY,title TEXT NOT NULL,project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
                model TEXT NOT NULL DEFAULT '',style TEXT NOT NULL DEFAULT 'Balanced',
                tools INTEGER NOT NULL DEFAULT 1,memory INTEGER NOT NULL DEFAULT 1,
                pinned INTEGER NOT NULL DEFAULT 0,archived INTEGER NOT NULL DEFAULT 0,
                draft TEXT NOT NULL DEFAULT '',canvas TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS messages(
                id TEXT PRIMARY KEY,chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                role TEXT NOT NULL,content TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'complete',
                metadata TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS messages_chat ON messages(chat_id,created_at);
            CREATE TABLE IF NOT EXISTS attachments(
                id TEXT PRIMARY KEY,chat_id TEXT REFERENCES chats(id) ON DELETE CASCADE,
                project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
                name TEXT NOT NULL,kind TEXT NOT NULL,content TEXT NOT NULL DEFAULT '',
                image TEXT NOT NULL DEFAULT '',sha256 TEXT NOT NULL,size INTEGER NOT NULL,
                notice TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,
                CHECK((chat_id IS NULL) <> (project_id IS NULL)));
            CREATE TABLE IF NOT EXISTS preferences(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        """)
        # A crashed/interrupted run is a saved partial response, never a success.
        with self.conn:
            self.conn.execute("UPDATE messages SET status='interrupted' WHERE status='streaming'")

    @staticmethod
    def _id():
        return uuid.uuid4().hex

    def create_project(self, title, instructions=""):
        title = str(title).strip()
        if not title or len(title) > 120:
            raise ValueError("Project name must contain 1–120 characters.")
        ident = self._id()
        with self.lock, self.conn:
            self.conn.execute("INSERT INTO projects VALUES(?,?,?,?)",
                              (ident, title, str(instructions)[:8000], now()))
        return ident

    def projects(self):
        with self.lock:
            return [dict(r) for r in self.conn.execute("SELECT * FROM projects ORDER BY title")]

    def project(self, ident):
        with self.lock:
            row = self.conn.execute("SELECT * FROM projects WHERE id=?", (ident,)).fetchone()
            return dict(row) if row else None

    def update_project(self, ident, instructions):
        with self.lock, self.conn:
            self.conn.execute("UPDATE projects SET instructions=? WHERE id=?", (str(instructions)[:8000], ident))

    def new_chat(self, title="New chat", project_id=None, model=""):
        ident, stamp = self._id(), now()
        with self.lock, self.conn:
            self.conn.execute("""INSERT INTO chats(id,title,project_id,model,tools,memory,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?)""", (ident, title[:160], project_id, model,
                                             int(not self.temporary), int(not self.temporary), stamp, stamp))
        return ident

    def chat(self, ident):
        with self.lock:
            row = self.conn.execute("SELECT * FROM chats WHERE id=?", (ident,)).fetchone()
            if row is None:
                raise KeyError("Chat not found.")
            return dict(row)

    def update_chat(self, ident, **fields):
        allowed = {"title", "project_id", "model", "style", "tools", "memory", "pinned",
                   "archived", "draft", "canvas"}
        if not fields or set(fields) - allowed:
            raise ValueError("Unsupported chat setting.")
        if "title" in fields:
            fields["title"] = str(fields["title"]).strip()[:160]
            if not fields["title"]:
                raise ValueError("Chat title cannot be empty.")
        if self.temporary:
            fields.update(tools=0, memory=0)
        with self.lock, self.conn:
            self.conn.execute("UPDATE chats SET " + ",".join(k + "=?" for k in fields)
                              + ",updated_at=? WHERE id=?", [*fields.values(), now(), ident])

    def list_chats(self, query="", project_id=None, archived=False):
        with self.lock:
            params = [int(archived)]
            where = "c.archived=?"
            if project_id:
                where += " AND c.project_id=?"; params.append(project_id)
            if query.strip():
                # instr is literal: %, _ and quotes are ordinary search characters.
                where += " AND (instr(lower(c.title),lower(?))>0 OR EXISTS(SELECT 1 FROM messages m WHERE m.chat_id=c.id AND instr(lower(m.content),lower(?))>0))"
                params.extend([query.strip(), query.strip()])
            rows = self.conn.execute("SELECT c.* FROM chats c WHERE " + where +
                " ORDER BY c.pinned DESC,c.updated_at DESC,c.rowid DESC LIMIT 300", params).fetchall()
            return [dict(r) for r in rows]

    def add_message(self, chat_id, role, content, status="complete", metadata=None):
        if role not in ("user", "assistant") or status not in ("complete", "streaming", "stopped", "failed", "interrupted"):
            raise ValueError("Invalid message role/status.")
        self.chat(chat_id)
        ident = self._id()
        with self.lock, self.conn:
            self.conn.execute("INSERT INTO messages VALUES(?,?,?,?,?,?,?)",
                              (ident, chat_id, role, str(content), status, json.dumps(metadata or {}), now()))
            self.conn.execute("UPDATE chats SET updated_at=? WHERE id=?", (now(), chat_id))
            if role == "user" and self.conn.execute("SELECT title FROM chats WHERE id=?", (chat_id,)).fetchone()[0] == "New chat":
                self.conn.execute("UPDATE chats SET title=? WHERE id=?",
                                  (" ".join(str(content).split())[:70] or "File conversation", chat_id))
        return ident

    def update_message(self, ident, content, status="complete", metadata=None):
        if status not in ("complete", "streaming", "stopped", "failed", "interrupted"):
            raise ValueError("Invalid message status.")
        with self.lock, self.conn:
            if metadata is None:
                self.conn.execute("UPDATE messages SET content=?,status=? WHERE id=?", (content, status, ident))
            else:
                self.conn.execute("UPDATE messages SET content=?,status=?,metadata=? WHERE id=?",
                                  (content, status, json.dumps(metadata), ident))

    def messages(self, chat_id):
        with self.lock:
            rows = self.conn.execute("SELECT * FROM messages WHERE chat_id=? ORDER BY rowid", (chat_id,))
            return [dict(r, metadata=json.loads(r["metadata"])) for r in rows]

    def delete_chat(self, chat_id):
        with self.lock, self.conn:
            self.conn.execute("DELETE FROM chats WHERE id=?", (chat_id,))

    def attachment(self, ident):
        with self.lock:
            row = self.conn.execute("SELECT * FROM attachments WHERE id=?", (ident,)).fetchone()
            if row is None:
                raise KeyError("Attachment not found.")
            return dict(row)

    def add_attachment(self, data, chat_id=None, project_id=None):
        if bool(chat_id) == bool(project_id):
            raise ValueError("Choose one chat or project for an attachment.")
        ident = self._id()
        with self.lock, self.conn:
            self.conn.execute("INSERT INTO attachments VALUES(?,?,?,?,?,?,?,?,?,?,?)", (
                ident, chat_id, project_id, data["name"], data["kind"], data.get("content", ""),
                data.get("image", ""), data["sha256"], data["size"], data.get("notice", ""), now()))
        return ident

    def attachments(self, chat_id=None, project_id=None, with_images=False):
        field, value = ("chat_id", chat_id) if chat_id else ("project_id", project_id)
        columns = "*" if with_images else "id,chat_id,project_id,name,kind,content,sha256,size,notice,created_at"
        with self.lock:
            return [dict(r) for r in self.conn.execute(
                f"SELECT {columns} FROM attachments WHERE {field}=? ORDER BY rowid", (value,))]

    def remove_attachment(self, ident):
        with self.lock, self.conn:
            self.conn.execute("DELETE FROM attachments WHERE id=?", (ident,))

    def branch(self, chat_id, before_message_id, return_mapping=False):
        old = self.chat(chat_id)
        messages = self.messages(chat_id)
        if before_message_id not in {m["id"] for m in messages}:
            raise KeyError("Branch message not found.")
        new_id = self.new_chat(old["title"] + " · branch", old["project_id"], old["model"])
        self.update_chat(new_id, style=old["style"], tools=old["tools"], memory=old["memory"], canvas=old["canvas"])
        attachment_map = {}
        included = set()
        for message in messages:
            included.update(message["metadata"].get("attachments", []))
            if message["id"] == before_message_id:
                break
        for attachment in self.attachments(chat_id=chat_id, with_images=True):
            if attachment["id"] not in included:
                continue
            attachment_map[attachment["id"]] = self.add_attachment(attachment, chat_id=new_id)
        for message in messages:
            if message["id"] == before_message_id:
                break
            metadata = dict(message["metadata"])
            metadata["attachments"] = [attachment_map[i] for i in metadata.get("attachments", []) if i in attachment_map]
            self.add_message(new_id, message["role"], message["content"], message["status"], metadata)
        return (new_id, attachment_map) if return_mapping else new_id

    def preference(self, key, default=""):
        with self.lock:
            row = self.conn.execute("SELECT value FROM preferences WHERE key=?", (key,)).fetchone()
            return row[0] if row else default

    def set_preference(self, key, value):
        with self.lock, self.conn:
            self.conn.execute("INSERT INTO preferences VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                              (key, str(value)))

    def import_legacy(self, exchanges):
        """Copy existing visible history once; never delete the original memory DB."""
        if self.preference("legacy_imported"):
            return None
        exchanges = [m for m in exchanges if m.get("role") in ("user", "assistant") and m.get("content")]
        ident = None
        if exchanges:
            ident = self.new_chat("Earlier Apollo conversation")
            for message in exchanges:
                self.add_message(ident, message["role"], message["content"])
        self.set_preference("legacy_imported", "yes")
        return ident

    def export(self, chat_id, format="markdown"):
        chat = self.chat(chat_id)
        messages = self.messages(chat_id)
        if format == "json":
            # Exclude binary image payloads and original disk paths from exports.
            return json.dumps({"version": 1, "chat": chat, "messages": messages,
                               "attachments": self.attachments(chat_id=chat_id)}, indent=2, ensure_ascii=False)
        pieces = ["# " + chat["title"], "", "Model preference: " + (chat["model"] or "Apollo default"), ""]
        for m in messages:
            pieces += ["## " + ("You" if m["role"] == "user" else "Apollo") + " · " + m["status"], "", m["content"], ""]
        return "\n".join(pieces)

    def close(self):
        with self.lock:
            self.conn.close()
