import hashlib, json, math, re, sqlite3, threading
from collections import Counter
from pathlib import Path

TOKEN_RE = re.compile(r"[a-zA-Z0-9']+")

def _tokens(text):
    return TOKEN_RE.findall(str(text or "").lower())

def _cosine(a, b):
    aa, bb = Counter(_tokens(a)), Counter(_tokens(b))
    if not aa or not bb:
        return 0.0
    dot = sum(aa[k] * bb[k] for k in set(aa) & set(bb))
    ma = math.sqrt(sum(v*v for v in aa.values()))
    mb = math.sqrt(sum(v*v for v in bb.values()))
    return dot / (ma * mb) if ma and mb else 0.0

class Module:
    def __init__(self, context=None):
        context = context or {}
        self.base_dir = Path(context.get("base_dir", ".")).resolve()
        self.validation = bool(context.get("validation", False))
        if self.validation:
            self.db_path = ":memory:"
        else:
            storage = self.base_dir / "storage"
            storage.mkdir(parents=True, exist_ok=True)
            self.db_path = str(storage / "databases" / "memory_bank.db")
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=15.0)
        self.conn.row_factory = sqlite3.Row
        self.fts_available = False
        self._setup()

    def _setup(self):
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    memory_type TEXT NOT NULL DEFAULT 'knowledge',
                    summary TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT '',
                    source_ref TEXT NOT NULL DEFAULT '',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    importance REAL NOT NULL DEFAULT 1.0,
                    content_hash TEXT NOT NULL UNIQUE,
                    learned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            try:
                cur.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
                    USING fts5(name, summary, content, source, tags,
                               content='memories', content_rowid='id')
                """)
                cur.executescript("""
                    CREATE TRIGGER IF NOT EXISTS memory_ai AFTER INSERT ON memories BEGIN
                        INSERT INTO memory_fts(rowid,name,summary,content,source,tags)
                        VALUES(new.id,new.name,new.summary,new.content,new.source,new.tags_json);
                    END;
                    CREATE TRIGGER IF NOT EXISTS memory_ad AFTER DELETE ON memories BEGIN
                        INSERT INTO memory_fts(memory_fts,rowid,name,summary,content,source,tags)
                        VALUES('delete',old.id,old.name,old.summary,old.content,old.source,old.tags_json);
                    END;
                    CREATE TRIGGER IF NOT EXISTS memory_au AFTER UPDATE ON memories BEGIN
                        INSERT INTO memory_fts(memory_fts,rowid,name,summary,content,source,tags)
                        VALUES('delete',old.id,old.name,old.summary,old.content,old.source,old.tags_json);
                        INSERT INTO memory_fts(rowid,name,summary,content,source,tags)
                        VALUES(new.id,new.name,new.summary,new.content,new.source,new.tags_json);
                    END;
                """)
                self.fts_available = True
            except sqlite3.OperationalError:
                self.fts_available = False
            self.conn.commit()

    def tools(self):
        return [
            {"name":"store_memory","description":"Store useful information in Apollo's named Memory Bank.",
             "parameters":{"type":"object","properties":{
                 "name":{"type":"string"},"memory_type":{"type":"string"},
                 "summary":{"type":"string"},"content":{"type":"string"},
                 "source":{"type":"string"},"source_ref":{"type":"string"},
                 "tags":{"type":"array","items":{"type":"string"}},
                 "importance":{"type":"number"}},"required":["name","content"]}},
            {"name":"search_memory_bank","description":"Search Apollo's named Memory Bank.",
             "parameters":{"type":"object","properties":{"query":{"type":"string"},"limit":{"type":"integer"}},"required":["query"]}},
            {"name":"list_memories","description":"List recent named memories.",
             "parameters":{"type":"object","properties":{"limit":{"type":"integer"},"memory_type":{"type":"string"}}}},
            {"name":"remove_memory","description":"Remove a Memory Bank entry by id or exact name.",
             "parameters":{"type":"object","properties":{"memory":{"type":"string"}},"required":["memory"]}},
            {"name":"memory_bank_stats","description":"Return Memory Bank statistics.",
             "parameters":{"type":"object","properties":{}}},
        ]

    @staticmethod
    def _limit(value, default=10, maximum=200):
        try: value = int(value)
        except Exception: value = default
        return max(1, min(value, maximum))

    @staticmethod
    def _tags(tags):
        if tags is None: return []
        if isinstance(tags, str): tags = re.split(r"[,;]", tags)
        if not isinstance(tags, (list,tuple,set)): tags = [str(tags)]
        out, seen = [], set()
        for tag in tags:
            v = str(tag or "").strip()
            if v and v.lower() not in seen:
                seen.add(v.lower()); out.append(v)
        return out[:30]

    def store_memory(self, name, content, memory_type="knowledge", summary="", source="",
                     source_ref="", tags=None, importance=1.0):
        name = " ".join(str(name or "").split()).strip()
        content = str(content or "").strip()
        if not name: raise ValueError("Memory name cannot be empty.")
        if not content: raise ValueError("Memory content cannot be empty.")
        try: importance = max(0.0, min(float(importance), 5.0))
        except Exception: importance = 1.0
        memory_type = str(memory_type or "knowledge").strip().lower().replace(" ","_")
        summary, source, source_ref = map(lambda x: str(x or "").strip(), (summary,source,source_ref))
        tags = self._tags(tags)
        digest = hashlib.sha256((source+"\n"+source_ref+"\n"+content).encode("utf-8","replace")).hexdigest()
        with self._lock:
            existing = self.conn.execute(
                "SELECT id FROM memories WHERE content_hash=? LIMIT 1",
                (digest,),
            ).fetchone()

            if existing is None:
                existing = self.conn.execute(
                    """
                    SELECT id
                    FROM memories
                    WHERE lower(name)=lower(?)
                      AND memory_type=?
                      AND lower(source)=lower(?)
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (
                        name,
                        memory_type,
                        source,
                    ),
                ).fetchone()

            if existing:
                self.conn.execute(
                    """
                    UPDATE memories
                    SET
                        name=?,
                        memory_type=?,
                        summary=?,
                        content=?,
                        source=?,
                        source_ref=?,
                        tags_json=?,
                        importance=?,
                        content_hash=?,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (
                        name,
                        memory_type,
                        summary,
                        content,
                        source,
                        source_ref,
                        json.dumps(
                            tags,
                            ensure_ascii=False,
                        ),
                        importance,
                        digest,
                        existing["id"],
                    ),
                )
                self.conn.commit()
                return {
                    "stored": True,
                    "updated_existing": True,
                    "id": existing["id"],
                    "name": name,
                }

            cur = self.conn.execute("""INSERT INTO memories(name,memory_type,summary,content,source,source_ref,
                                  tags_json,importance,content_hash) VALUES(?,?,?,?,?,?,?,?,?)""",
                                  (name,memory_type,summary,content,source,source_ref,
                                   json.dumps(tags,ensure_ascii=False),importance,digest))
            self.conn.commit()
            return {"stored":True,"updated_existing":False,"id":cur.lastrowid,"name":name}

    def _row(self, row):
        try: tags = json.loads(row["tags_json"] or "[]")
        except Exception: tags = []
        return {"id":row["id"],"name":row["name"],"memory_type":row["memory_type"],
                "summary":row["summary"],"content":row["content"],"source":row["source"],
                "source_ref":row["source_ref"],"tags":tags,"importance":float(row["importance"]),
                "learned_at":row["learned_at"],"updated_at":row["updated_at"]}

    def search_memory(self, query, limit=5):
        query = str(query or "").strip()
        if not query: raise ValueError("query cannot be empty.")
        limit = self._limit(limit,5,20)
        rows = []
        if self.fts_available:
            terms = [t for t in _tokens(query) if len(t)>=2]
            if terms:
                expression = " OR ".join('"'+t.replace('"','""')+'"' for t in terms[:12])
                try:
                    with self._lock:
                        rows = self.conn.execute("""SELECT m.* FROM memory_fts
                            JOIN memories m ON m.id=memory_fts.rowid
                            WHERE memory_fts MATCH ?
                            ORDER BY bm25(memory_fts),m.importance DESC,m.updated_at DESC LIMIT ?""",
                            (expression,limit)).fetchall()
                except sqlite3.OperationalError:
                    rows = []
        if not rows:
            with self._lock:
                candidates = self.conn.execute("""SELECT * FROM memories
                    ORDER BY importance DESC,updated_at DESC LIMIT 1000""").fetchall()
            ranked = []
            for row in candidates:
                searchable = " ".join(str(row[k] or "") for k in ("name","summary","content","source","tags_json"))
                score = _cosine(query, searchable) + (0.35 if query.lower() in searchable.lower() else 0)
                score += float(row["importance"]) * 0.02
                if score > 0: ranked.append((score,row))
            ranked.sort(key=lambda x:x[0], reverse=True)
            rows = [r for _,r in ranked[:limit]]
        return [self._row(r) for r in rows[:limit]]

    def list_memories(self, limit=20, memory_type=""):
        limit = self._limit(limit,20,200)
        with self._lock:
            if memory_type:
                rows = self.conn.execute("""SELECT * FROM memories WHERE memory_type=?
                    ORDER BY updated_at DESC,id DESC LIMIT ?""",(str(memory_type),limit)).fetchall()
            else:
                rows = self.conn.execute("""SELECT * FROM memories
                    ORDER BY updated_at DESC,id DESC LIMIT ?""",(limit,)).fetchall()
        return [self._row(r) for r in rows]

    def remove_memory(self, memory):
        value = str(memory or "").strip()
        if not value: raise ValueError("memory cannot be empty.")
        with self._lock:
            row = self.conn.execute("SELECT * FROM memories WHERE id=?",(int(value),)).fetchone() if value.isdigit() else None
            if row is None:
                row = self.conn.execute("SELECT * FROM memories WHERE lower(name)=lower(?) ORDER BY id DESC LIMIT 1",(value,)).fetchone()
            if row is None: raise KeyError(f"Memory '{value}' was not found.")
            self.conn.execute("DELETE FROM memories WHERE id=?",(row["id"],)); self.conn.commit()
        return {"removed":True,"id":row["id"],"name":row["name"]}

    def stats(self):
        with self._lock:
            total = self.conn.execute("SELECT COUNT(*) c FROM memories").fetchone()["c"]
            types = self.conn.execute("SELECT memory_type,COUNT(*) c FROM memories GROUP BY memory_type").fetchall()
            recent = self.conn.execute("""SELECT id,name,memory_type,learned_at FROM memories
                ORDER BY updated_at DESC LIMIT 5""").fetchall()
        return {"total_memories":int(total),"types":{r["memory_type"]:int(r["c"]) for r in types},
                "recent":[dict(r) for r in recent],
                "database":"in-memory validation database" if self.validation else self.db_path}

    def self_test(self):
        a = self.store_memory(
            "AI Coding in Python",
            "Python machine learning code uses testing and debugging.",
            "learned_knowledge",
            "Source-backed notes.",
            "The Pile",
            "test:1",
            ["AI","Python"],
            2,
        )
        assert a["stored"]
        assert self.search_memory("Python machine learning")

        updated = self.store_memory(
            "AI Coding in Python",
            "Advanced Python machine learning uses PyTorch model training, inference and evaluation.",
            "learned_knowledge",
            "Improved source-backed notes.",
            "The Pile",
            "test:2",
            ["AI","Python","PyTorch"],
            2.5,
        )

        assert updated["id"] == a["id"]
        refreshed = self.search_memory(
            "PyTorch model training",
            3,
        )
        assert refreshed
        assert "PyTorch" in refreshed[0]["content"]
        assert self.stats()["total_memories"] >= 1
        return "Memory Bank store/search/topic-replacement tests passed."

    def build_ui(self, parent=None, ui_context=None):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QPushButton,QListWidget,QListWidgetItem,QTextBrowser,QMessageBox
        page = QWidget(parent); layout = QVBoxLayout(page)
        title = QLabel("Memory Bank"); title.setStyleSheet("font-size:22px;font-weight:700;color:#e7fffb;")
        layout.addWidget(title)
        subtitle = QLabel("Named, dated memories Apollo has deliberately kept."); subtitle.setStyleSheet("color:#91bdb6;"); layout.addWidget(subtitle)
        row = QHBoxLayout(); search = QLineEdit(); search.setPlaceholderText("Search memories...")
        search_btn = QPushButton("Search"); recent_btn = QPushButton("Recent"); remove_btn = QPushButton("Remove Selected")
        row.addWidget(search,1); row.addWidget(search_btn); row.addWidget(recent_btn); row.addWidget(remove_btn); layout.addLayout(row)
        lst = QListWidget(); details = QTextBrowser(); layout.addWidget(lst,1); layout.addWidget(details,1)
        state={"rows":[]}
        def display(rows):
            state["rows"]=rows; lst.clear()
            for r in rows:
                item=QListWidgetItem(f"{r['name']}\n{r['memory_type']} • {r['source'] or 'local'} • {r['learned_at']}")
                item.setData(Qt.UserRole,r["id"]); lst.addItem(item)
            if rows: lst.setCurrentRow(0); show()
            else: details.setPlainText("No matching memories.")
        def recent(): display(self.list_memories(50))
        def do_search():
            q=search.text().strip(); display(self.search_memory(q,50) if q else self.list_memories(50))
        def show():
            sel=lst.selectedItems()
            if not sel: return
            ident=sel[0].data(Qt.UserRole)
            r=next((x for x in state["rows"] if x["id"]==ident),None)
            if r:
                details.setPlainText(f"Name: {r['name']}\nType: {r['memory_type']}\nLearned: {r['learned_at']}\nUpdated: {r['updated_at']}\nSource: {r['source']}\nSource reference: {r['source_ref']}\nTags: {', '.join(r['tags'])}\nImportance: {r['importance']}\n\nSummary:\n{r['summary']}\n\nMemory:\n{r['content']}")
        def remove():
            sel=lst.selectedItems()
            if not sel: return
            if QMessageBox.question(page,"Remove Memory","Remove the selected memory?",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes:
                self.remove_memory(str(sel[0].data(Qt.UserRole))); recent()
        search_btn.clicked.connect(do_search); recent_btn.clicked.connect(recent); remove_btn.clicked.connect(remove)
        search.returnPressed.connect(do_search); lst.itemSelectionChanged.connect(show); recent()
        return page

    def build_hub_widget(self, parent=None, ui_context=None):
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QFrame,QVBoxLayout,QLabel,QPushButton
        frame=QFrame(parent); frame.setObjectName("card"); layout=QVBoxLayout(frame)
        title=QLabel("Memory Bank"); title.setStyleSheet("font-size:14px;font-weight:700;color:#e9fffb;"); layout.addWidget(title)
        count=QLabel("0 named memories"); count.setStyleSheet("font-size:18px;font-weight:700;color:#7cf0d7;"); layout.addWidget(count)
        recent=QLabel("No stored memories yet."); recent.setWordWrap(True); recent.setStyleSheet("color:#b8d9d3;"); layout.addWidget(recent)
        btn=QPushButton("Open Memory Bank"); layout.addWidget(btn)
        win=(ui_context or {}).get("apollo_window")
        if win is not None: btn.clicked.connect(lambda: win.open_module_app("memory_bank"))
        else: btn.setEnabled(False)
        def refresh():
            try:
                s=self.stats(); count.setText(f"{s['total_memories']} named memories")
                names=[x["name"] for x in s.get("recent",[])[:4]]
                recent.setText("\n".join("• "+x for x in names) if names else "No stored memories yet.")
            except Exception as exc:
                recent.setText(f"Memory Bank error: {exc}")
        timer=QTimer(frame); timer.setInterval(1500); timer.timeout.connect(refresh); timer.start(); refresh()
        return frame

    def run(self, action, arguments):
        arguments=arguments or {}
        if action=="store_memory":
            return self.store_memory(arguments.get("name"),arguments.get("content"),
                arguments.get("memory_type","knowledge"),arguments.get("summary",""),
                arguments.get("source",""),arguments.get("source_ref",""),
                arguments.get("tags",[]),arguments.get("importance",1.0))
        if action=="search_memory_bank": return self.search_memory(arguments.get("query"),arguments.get("limit",5))
        if action=="list_memories": return self.list_memories(arguments.get("limit",20),arguments.get("memory_type",""))
        if action=="remove_memory": return self.remove_memory(arguments.get("memory"))
        if action=="memory_bank_stats": return self.stats()
        raise KeyError(action)

    def close(self):
        with self._lock:
            try: self.conn.close()
            except Exception: pass
