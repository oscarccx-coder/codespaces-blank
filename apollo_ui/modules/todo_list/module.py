import sqlite3, threading
from pathlib import Path

class Module:
    def __init__(self, context=None):
        context=context or {}
        self.base_dir=Path(context.get("base_dir",".")).resolve()
        self.validation=bool(context.get("validation",False))
        if self.validation:
            self.db_path=":memory:"
        else:
            storage=self.base_dir/"storage"; storage.mkdir(parents=True, exist_ok=True)
            self.db_path=str(storage/"databases"/"to_do_list.db")
        self._lock=threading.RLock()
        self.conn=sqlite3.connect(self.db_path,check_same_thread=False,timeout=15.0)
        self.conn.row_factory=sqlite3.Row
        self._setup()

    def _setup(self):
        with self._lock:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS to_do_items(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    details TEXT NOT NULL DEFAULT '',
                    priority INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    completed_at TEXT
                )
            """); self.conn.commit()

    def tools(self):
        return [
            {"name":"add_to_do_item","description":"Add a persistent item to Apollo's To-Do List.",
             "parameters":{"type":"object","properties":{"title":{"type":"string"},"details":{"type":"string"},"priority":{"type":"integer"}},"required":["title"]}},
            {"name":"remove_to_do_item","description":"Remove a To-Do List item by id or title.",
             "parameters":{"type":"object","properties":{"item":{"type":"string"}},"required":["item"]}},
            {"name":"update_to_do_item","description":"Edit a To-Do List item.",
             "parameters":{"type":"object","properties":{"item":{"type":"string"},"title":{"type":"string"},"details":{"type":"string"},"priority":{"type":"integer"}},"required":["item"]}},
            {"name":"complete_to_do_item","description":"Tick off a To-Do List item after its work actually succeeds.",
             "parameters":{"type":"object","properties":{"item":{"type":"string"}},"required":["item"]}},
            {"name":"reopen_to_do_item","description":"Reopen a completed To-Do List item.",
             "parameters":{"type":"object","properties":{"item":{"type":"string"}},"required":["item"]}},
            {"name":"list_to_do_items","description":"List Apollo's To-Do List items.",
             "parameters":{"type":"object","properties":{"include_completed":{"type":"boolean"},"limit":{"type":"integer"}}}},
            {"name":"achieve_to_do_list","description":"Return open To-Do List items as an execution plan. Perform real actions, then complete each successful item.",
             "parameters":{"type":"object","properties":{"limit":{"type":"integer"}}}},
        ]

    @staticmethod
    def _priority(v):
        try:v=int(v)
        except Exception:v=0
        return max(-10,min(v,10))
    @staticmethod
    def _limit(v,default=50):
        try:v=int(v)
        except Exception:v=default
        return max(1,min(v,200))
    def _row(self,r):
        if r is None:return None
        return {k:r[k] for k in ("id","title","details","priority","status","created_at","updated_at","completed_at")}

    def _resolve(self,item):
        value=str(item or "").strip()
        if not value: raise ValueError("item cannot be empty.")
        with self._lock:
            row=self.conn.execute("SELECT * FROM to_do_items WHERE id=?",(int(value),)).fetchone() if value.isdigit() else None
            if row is None:
                row=self.conn.execute("SELECT * FROM to_do_items WHERE lower(title)=lower(?) ORDER BY id DESC LIMIT 1",(value,)).fetchone()
            if row is None:
                row=self.conn.execute("""SELECT * FROM to_do_items WHERE lower(title) LIKE lower(?)
                    ORDER BY status='open' DESC,priority DESC,id ASC LIMIT 1""",("%"+value+"%",)).fetchone()
        if row is None: raise KeyError(f"To-Do List item '{value}' was not found.")
        return row

    def add_item(self,title,details="",priority=0):
        title=" ".join(str(title or "").split()).strip()
        if not title: raise ValueError("title cannot be empty.")
        details=str(details or "").strip(); priority=self._priority(priority)
        with self._lock:
            existing=self.conn.execute("""SELECT * FROM to_do_items
                WHERE lower(title)=lower(?) AND status='open' LIMIT 1""",(title,)).fetchone()
            if existing:return {"added":False,"duplicate":True,"item":self._row(existing)}
            cur=self.conn.execute("INSERT INTO to_do_items(title,details,priority) VALUES(?,?,?)",(title,details,priority))
            self.conn.commit()
            row=self.conn.execute("SELECT * FROM to_do_items WHERE id=?",(cur.lastrowid,)).fetchone()
        return {"added":True,"duplicate":False,"item":self._row(row)}

    def remove_item(self,item):
        row=self._resolve(item)
        with self._lock:
            self.conn.execute("DELETE FROM to_do_items WHERE id=?",(row["id"],)); self.conn.commit()
        return {"removed":True,"item":self._row(row)}

    def update_item(self,item,title=None,details=None,priority=None):
        row=self._resolve(item)
        new_title=" ".join(str(title).split()).strip() if title is not None else row["title"]
        if not new_title: raise ValueError("title cannot be empty.")
        new_details=str(details).strip() if details is not None else row["details"]
        new_priority=self._priority(priority) if priority is not None else int(row["priority"])
        with self._lock:
            self.conn.execute("""UPDATE to_do_items SET title=?,details=?,priority=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                              (new_title,new_details,new_priority,row["id"]))
            self.conn.commit(); out=self.conn.execute("SELECT * FROM to_do_items WHERE id=?",(row["id"],)).fetchone()
        return {"updated":True,"item":self._row(out)}

    def complete_item(self,item):
        row=self._resolve(item)
        with self._lock:
            self.conn.execute("""UPDATE to_do_items SET status='completed',completed_at=CURRENT_TIMESTAMP,
                               updated_at=CURRENT_TIMESTAMP WHERE id=?""",(row["id"],))
            self.conn.commit(); out=self.conn.execute("SELECT * FROM to_do_items WHERE id=?",(row["id"],)).fetchone()
        return {"completed":True,"item":self._row(out)}

    def reopen_item(self,item):
        row=self._resolve(item)
        with self._lock:
            self.conn.execute("""UPDATE to_do_items SET status='open',completed_at=NULL,
                               updated_at=CURRENT_TIMESTAMP WHERE id=?""",(row["id"],))
            self.conn.commit(); out=self.conn.execute("SELECT * FROM to_do_items WHERE id=?",(row["id"],)).fetchone()
        return {"reopened":True,"item":self._row(out)}

    def list_items(self,include_completed=True,limit=50):
        limit=self._limit(limit)
        with self._lock:
            if include_completed:
                rows=self.conn.execute("""SELECT * FROM to_do_items
                    ORDER BY status='open' DESC,priority DESC,id ASC LIMIT ?""",(limit,)).fetchall()
            else:
                rows=self.conn.execute("""SELECT * FROM to_do_items WHERE status='open'
                    ORDER BY priority DESC,id ASC LIMIT ?""",(limit,)).fetchall()
        return [self._row(r) for r in rows]

    def achieve_list(self,limit=10):
        items=self.list_items(False,limit)
        return {"open_count":len(self.list_items(False,200)),"items":items,
                "instruction":"Work through these items in order using real Apollo tools. After an item genuinely succeeds, call todo_list__complete_to_do_item with its id. Do not mark manual, unsupported or failed work complete."}

    def self_test(self):
        a=self.add_item("Research Python AI coding","Use source-backed research.",2); assert a["added"]
        ident=str(a["item"]["id"]); assert self.complete_item(ident)["item"]["status"]=="completed"
        assert self.reopen_item(ident)["item"]["status"]=="open"; assert self.achieve_list(5)["items"]
        return "To-Do List add/update/complete/achievement tests passed."

    def _build_widget(self,parent=None,ui_context=None,compact=False):
        from PySide6.QtCore import Qt,QTimer
        from PySide6.QtWidgets import QWidget,QFrame,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QPushButton,QListWidget,QListWidgetItem,QInputDialog,QMessageBox
        page=QFrame(parent) if compact else QWidget(parent)
        if compact: page.setObjectName("card")
        layout=QVBoxLayout(page)
        title=QLabel("To-Do List"); title.setStyleSheet(("font-size:14px;" if compact else "font-size:22px;")+"font-weight:700;color:#e7fffb;")
        layout.addWidget(title)
        if not compact:
            sub=QLabel("Persistent tasks Apollo can add, edit, remove, complete and work through."); sub.setStyleSheet("color:#91bdb6;"); sub.setWordWrap(True); layout.addWidget(sub)
        addrow=QHBoxLayout(); entry=QLineEdit(); entry.setPlaceholderText("Add a To-Do List item..."); addbtn=QPushButton("Add")
        addrow.addWidget(entry,1); addrow.addWidget(addbtn); layout.addLayout(addrow)
        lst=QListWidget()
        if compact: lst.setMaximumHeight(230)
        layout.addWidget(lst,1)
        row=QHBoxLayout(); editbtn=QPushButton("Edit"); rembtn=QPushButton("Remove"); refreshbtn=QPushButton("Refresh")
        row.addWidget(editbtn); row.addWidget(rembtn); row.addWidget(refreshbtn)
        if not compact:
            achievebtn=QPushButton("Show Achievement Plan"); row.addWidget(achievebtn)
        row.addStretch(); layout.addLayout(row)
        state={"refreshing":False,"signature":None}
        def refresh(force=False):
            items=self.list_items(True,100); sig=tuple((x["id"],x["title"],x["status"],x["priority"],x["updated_at"]) for x in items)
            if not force and sig==state["signature"]: return
            state["signature"]=sig; state["refreshing"]=True; lst.clear()
            for r in items:
                item=QListWidgetItem(("✓ " if r["status"]=="completed" else "")+r["title"])
                item.setData(Qt.UserRole,r["id"]); item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if r["status"]=="completed" else Qt.CheckState.Unchecked)
                if r["details"]: item.setToolTip(r["details"])
                lst.addItem(item)
            state["refreshing"]=False
        def add():
            t=entry.text().strip()
            if t:self.add_item(t);entry.clear();refresh(True)
        def sid():
            s=lst.selectedItems();return str(s[0].data(Qt.UserRole)) if s else None
        def edit():
            ident=sid()
            if not ident:return
            r=self._row(self._resolve(ident))
            title,ok=QInputDialog.getText(page,"Edit To-Do Item","Title:",text=r["title"])
            if not ok:return
            details,ok=QInputDialog.getMultiLineText(page,"Edit To-Do Item","Details:",r["details"])
            if ok:self.update_item(ident,title=title,details=details);refresh(True)
        def remove():
            ident=sid()
            if not ident:return
            r=self._row(self._resolve(ident))
            if QMessageBox.question(page,"Remove To-Do Item",f"Remove '{r['title']}' from the To-Do List?",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes:
                self.remove_item(ident);refresh(True)
        def changed(item):
            if state["refreshing"]:return
            ident=str(item.data(Qt.UserRole))
            if item.checkState() == Qt.CheckState.Checked: self.complete_item(ident)
            else:self.reopen_item(ident)
            refresh(True)
        addbtn.clicked.connect(add);entry.returnPressed.connect(add);editbtn.clicked.connect(edit);rembtn.clicked.connect(remove)
        refreshbtn.clicked.connect(lambda:refresh(True));lst.itemChanged.connect(changed)
        if not compact:
            def show_plan():
                items=self.achieve_list(20)["items"]
                QMessageBox.information(page,"To-Do Achievement Plan","\n".join(f"{x['id']}. {x['title']}" for x in items) or "The To-Do List is complete.")
            achievebtn.clicked.connect(show_plan)
        timer=QTimer(page);timer.setInterval(1200);timer.timeout.connect(refresh);timer.start();refresh(True)
        return page

    def build_ui(self,parent=None,ui_context=None): return self._build_widget(parent,ui_context,False)
    def build_hub_widget(self,parent=None,ui_context=None): return self._build_widget(parent,ui_context,True)

    def run(self,action,arguments):
        a=arguments or {}
        if action=="add_to_do_item":return self.add_item(a.get("title"),a.get("details",""),a.get("priority",0))
        if action=="remove_to_do_item":return self.remove_item(a.get("item"))
        if action=="update_to_do_item":return self.update_item(a.get("item"),a.get("title"),a.get("details"),a.get("priority"))
        if action=="complete_to_do_item":return self.complete_item(a.get("item"))
        if action=="reopen_to_do_item":return self.reopen_item(a.get("item"))
        if action=="list_to_do_items":return self.list_items(bool(a.get("include_completed",True)),a.get("limit",50))
        if action=="achieve_to_do_list":return self.achieve_list(a.get("limit",10))
        raise KeyError(action)

    def close(self):
        with self._lock:
            try:self.conn.close()
            except Exception:pass
