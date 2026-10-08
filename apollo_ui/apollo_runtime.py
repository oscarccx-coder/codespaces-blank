import json
import os
import sqlite3
import threading
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from apollo_storage import StorageLayout


def _now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class ApolloRuntime:
    """Shared nervous system for Apollo 7.

    All live module actions can pass through this runtime so permissions, events,
    task history, notifications, blackboard state and recovery are consistent no
    matter whether an action came from Chat, Workshop, automation or a module UI.
    """

    HIGH_RISK_WORDS = {
        "terminate", "kill", "install_package", "install_into_env", "run_command", "write_serial",
        "capture_screen", "set_permission", "apply_core", "self_modify",
    }
    MEDIUM_WORDS = {
        "write", "save", "store", "add", "update", "create", "remove",
        "record", "snapshot", "schedule", "complete", "reopen", "train",
        "speak", "listen", "fetch", "download", "set_active", "set_role",
        "move", "copy", "import", "rename", "trash", "restore", "clipboard", "stage",
    }

    def __init__(self, base_dir):
        self.base_dir = Path(base_dir).resolve()
        self.storage_layout = StorageLayout(self.base_dir)
        self.storage_layout.ensure_layout()
        self.storage_dir = self.storage_layout.root
        self.db_path = self.storage_layout.databases / "apollo_runtime.db"
        self._lock = threading.RLock()
        self._manager = None
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()
        self._startup_marker = self.storage_layout.state / "apollo_running.flag"
        self.previous_unclean_shutdown = self._startup_marker.exists()
        self._startup_marker.write_text(_now(), encoding="utf-8")
        if self.previous_unclean_shutdown:
            self.notify(
                "Apollo recovered after an unclean shutdown",
                "The previous session did not close cleanly. Core data was left intact; use Recovery if anything looks wrong.",
                level="warning",
                source="runtime",
            )

    def _init_db(self):
        with self._lock:
            self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS permissions(
                capability TEXT PRIMARY KEY,
                decision TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                topic TEXT NOT NULL,
                source TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tasks(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                actor TEXT NOT NULL,
                capability TEXT NOT NULL,
                status TEXT NOT NULL,
                detail TEXT
            );
            CREATE TABLE IF NOT EXISTS notifications(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                level TEXT NOT NULL,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                read INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS blackboard(
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS goals(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                priority INTEGER NOT NULL DEFAULT 50,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS module_failures(
                module_id TEXT PRIMARY KEY,
                failure_count INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                last_failed_at TEXT,
                quarantined INTEGER NOT NULL DEFAULT 0
            );
            """)
            self.conn.commit()

    def attach_manager(self, manager):
        self._manager = manager
        self.refresh_capabilities(manager)

    def risk_for(self, capability):
        cap = str(capability or "").lower()
        action = cap.split("__", 1)[-1]
        if any(word in action for word in self.HIGH_RISK_WORDS):
            return "high"
        if any(word in action for word in self.MEDIUM_WORDS):
            return "medium"
        return "low"

    def get_permission(self, capability):
        capability = str(capability)
        with self._lock:
            row = self.conn.execute(
                "SELECT decision FROM permissions WHERE capability=?", (capability,)
            ).fetchone()
        if row:
            return row["decision"]
        return "deny" if self.risk_for(capability) == "high" else "allow"

    def set_permission(self, capability, decision):
        decision = str(decision or "").lower().strip()
        if decision not in {"allow", "deny"}:
            raise ValueError("decision must be allow or deny")
        with self._lock:
            self.conn.execute(
                "INSERT INTO permissions(capability, decision, updated_at) VALUES(?,?,?) "
                "ON CONFLICT(capability) DO UPDATE SET decision=excluded.decision, updated_at=excluded.updated_at",
                (str(capability), decision, _now()),
            )
            self.conn.commit()
        self.publish("permission.changed", "runtime", {"capability": capability, "decision": decision})
        self.refresh_capabilities(self._manager)
        return {"capability": capability, "decision": decision}

    def capability_records(self, manager=None):
        manager = manager or self._manager
        if manager is None:
            return []
        records = []
        for tool in manager.ollama_tools(raw=True):
            fn = tool.get("function", {}) or {}
            name = str(fn.get("name", ""))
            records.append({
                "capability": name,
                "description": str(fn.get("description", "")),
                "risk": self.risk_for(name),
                "permission": self.get_permission(name),
            })
        return records

    def refresh_capabilities(self, manager=None):
        manager = manager or self._manager
        if manager is None:
            return None
        workspace = self.base_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        target = workspace / "APOLLO_CAPABILITIES.json"
        payload = {
            "generated_at": _now(),
            "count": len(self.capability_records(manager)),
            "capabilities": self.capability_records(manager),
        }
        temp = target.with_suffix(".json.tmp")
        temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp.replace(target)
        return str(target)

    def execute_tool(self, manager, function_name, arguments=None, actor="apollo"):
        capability = str(function_name)
        arguments = arguments or {}
        decision = self.get_permission(capability)
        risk = self.risk_for(capability)
        if decision != "allow":
            self.publish("action.denied", actor, {"capability": capability, "risk": risk})
            raise PermissionError(
                f"Capability '{capability}' is blocked by Apollo's permission gate. "
                "Enable it explicitly in Core Services / Control Center first."
            )

        started = _now()
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO tasks(started_at, actor, capability, status, detail) VALUES(?,?,?,?,?)",
                (started, actor, capability, "running", json.dumps(arguments, ensure_ascii=False)[:4000]),
            )
            task_id = cur.lastrowid
            self.conn.commit()
        self.publish("action.started", actor, {"task_id": task_id, "capability": capability})
        try:
            result = manager._execute_tool_direct(capability, arguments)
            status = "success"
            detail = json.dumps(result, ensure_ascii=False, default=str)[:8000]
            self.publish("action.completed", actor, {"task_id": task_id, "capability": capability})
            return result
        except Exception as exc:
            status = "failed"
            detail = f"{type(exc).__name__}: {exc}"
            self.publish("action.failed", actor, {"task_id": task_id, "capability": capability, "error": detail})
            raise
        finally:
            with self._lock:
                self.conn.execute(
                    "UPDATE tasks SET finished_at=?, status=?, detail=? WHERE id=?",
                    (_now(), status, detail, task_id),
                )
                self.conn.commit()

    def publish(self, topic, source, payload=None):
        payload = payload if isinstance(payload, dict) else {"value": payload}
        with self._lock:
            self.conn.execute(
                "INSERT INTO events(created_at, topic, source, payload_json) VALUES(?,?,?,?)",
                (_now(), str(topic), str(source), json.dumps(payload, ensure_ascii=False, default=str)),
            )
            self.conn.commit()

    def recent_events(self, limit=100, topic=None):
        limit = max(1, min(int(limit), 500))
        with self._lock:
            if topic:
                rows = self.conn.execute(
                    "SELECT * FROM events WHERE topic=? ORDER BY id DESC LIMIT ?", (str(topic), limit)
                ).fetchall()
            else:
                rows = self.conn.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def blackboard_set(self, key, value, source="apollo"):
        with self._lock:
            self.conn.execute(
                "INSERT INTO blackboard(key,value_json,updated_at,source) VALUES(?,?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at, source=excluded.source",
                (str(key), json.dumps(value, ensure_ascii=False, default=str), _now(), str(source)),
            )
            self.conn.commit()
        self.publish("blackboard.changed", source, {"key": str(key)})

    def blackboard_get(self, key, default=None):
        with self._lock:
            row = self.conn.execute("SELECT value_json FROM blackboard WHERE key=?", (str(key),)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value_json"])
        except Exception:
            return row["value_json"]

    def blackboard_all(self):
        with self._lock:
            rows = self.conn.execute("SELECT * FROM blackboard ORDER BY key").fetchall()
        out = {}
        for row in rows:
            try:
                value = json.loads(row["value_json"])
            except Exception:
                value = row["value_json"]
            out[row["key"]] = {"value": value, "updated_at": row["updated_at"], "source": row["source"]}
        return out

    def notify(self, title, message, level="info", source="apollo"):
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO notifications(created_at,level,source,title,message,read) VALUES(?,?,?,?,?,0)",
                (_now(), str(level), str(source), str(title), str(message)),
            )
            self.conn.commit()
        return cur.lastrowid

    def notifications(self, unread_only=False, limit=100):
        with self._lock:
            if unread_only:
                rows = self.conn.execute(
                    "SELECT * FROM notifications WHERE read=0 ORDER BY id DESC LIMIT ?", (int(limit),)
                ).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT * FROM notifications ORDER BY id DESC LIMIT ?", (int(limit),)
                ).fetchall()
        return [dict(r) for r in rows]

    def mark_notification_read(self, notification_id):
        with self._lock:
            self.conn.execute("UPDATE notifications SET read=1 WHERE id=?", (int(notification_id),))
            self.conn.commit()

    def task_history(self, limit=100):
        with self._lock:
            rows = self.conn.execute("SELECT * FROM tasks ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
        return [dict(r) for r in rows]

    def health(self):
        manager = self._manager
        modules = manager.list_modules() if manager else []
        return {
            "runtime_db": str(self.db_path),
            "previous_unclean_shutdown": bool(self.previous_unclean_shutdown),
            "module_count": len(modules),
            "loaded_modules": sum(1 for m in modules if m.get("loaded")),
            "module_errors": manager.errors() if manager else {},
            "capability_count": len(self.capability_records(manager)) if manager else 0,
            "denied_capabilities": sum(1 for x in self.capability_records(manager) if x["permission"] == "deny") if manager else 0,
        }

    def apply_permission_profile(self, profile):
        profile = str(profile or "normal").strip().lower()
        if profile not in {"safe", "normal", "developer"}:
            raise ValueError("profile must be safe, normal, or developer")
        protected = {"apply_core", "self_modify", "overwrite_core", "delete_core"}
        changed = 0
        for item in self.capability_records():
            cap, risk = item["capability"], item["risk"]
            if profile == "safe":
                decision = "allow" if risk == "low" else "deny"
            elif profile == "normal":
                decision = "deny" if risk == "high" else "allow"
            else:
                decision = "deny" if any(x in cap.lower() for x in protected) else "allow"
            with self._lock:
                self.conn.execute(
                    "INSERT INTO permissions(capability,decision,updated_at) VALUES(?,?,?) "
                    "ON CONFLICT(capability) DO UPDATE SET decision=excluded.decision,updated_at=excluded.updated_at",
                    (cap, decision, _now()),
                )
                self.conn.commit()
            changed += 1
        self.blackboard_set("permissions.profile", profile, "runtime")
        self.publish("permission.profile.changed", "runtime", {"profile": profile, "changed": changed})
        self.refresh_capabilities(self._manager)
        return {"profile": profile, "changed": changed}

    def permission_profile(self):
        return str(self.blackboard_get("permissions.profile", "normal") or "normal")

    def record_module_failure(self, module_id, error):
        module_id = str(module_id)
        with self._lock:
            row = self.conn.execute(
                "SELECT failure_count,quarantined FROM module_failures WHERE module_id=?",
                (module_id,),
            ).fetchone()
            count = int(row["failure_count"]) + 1 if row else 1
            quarantined = 1 if count >= 3 else (int(row["quarantined"]) if row else 0)
            self.conn.execute(
                "INSERT INTO module_failures(module_id,failure_count,last_error,last_failed_at,quarantined) VALUES(?,?,?,?,?) "
                "ON CONFLICT(module_id) DO UPDATE SET failure_count=excluded.failure_count,last_error=excluded.last_error,last_failed_at=excluded.last_failed_at,quarantined=excluded.quarantined",
                (module_id, count, str(error)[:6000], _now(), quarantined),
            )
            self.conn.commit()
        self.publish("module.failure", "runtime", {"module_id": module_id, "failure_count": count, "quarantined": bool(quarantined)})
        if quarantined:
            self.notify(
                f"Module quarantined: {module_id}",
                f"{module_id} failed to load {count} consecutive times. Its files were left intact; clear quarantine in Control Center to retry.",
                level="error", source="runtime"
            )
        return {"module_id": module_id, "failure_count": count, "quarantined": bool(quarantined)}

    def clear_module_failure(self, module_id):
        with self._lock:
            self.conn.execute("DELETE FROM module_failures WHERE module_id=?", (str(module_id),))
            self.conn.commit()
        self.publish("module.quarantine.cleared", "runtime", {"module_id": str(module_id)})
        return {"module_id": str(module_id), "cleared": True}

    def module_failure_records(self):
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM module_failures ORDER BY quarantined DESC,failure_count DESC,module_id"
            ).fetchall()
        return [dict(r) for r in rows]

    def is_module_quarantined(self, module_id):
        with self._lock:
            row = self.conn.execute("SELECT quarantined FROM module_failures WHERE module_id=?", (str(module_id),)).fetchone()
        return bool(row and int(row["quarantined"]))

    def operational_summary(self):
        return {
            "health": self.health(),
            "permission_profile": self.permission_profile(),
            "active_goals": self.goals("active")[:12],
            "recent_failures": self.module_failure_records()[:12],
            "recent_tasks": self.task_history(20),
            "recent_events": self.recent_events(20),
            "shared_state_keys": sorted(self.blackboard_all().keys())[:100],
        }

    def create_snapshot(self, name="manual"):
        safe = re_safe(name)
        target_dir = self.storage_layout.backups / "recovery"
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = target_dir / f"apollo_{stamp}_{safe}.zip"
        # Capture the actual executable code, including newly introduced core
        # helpers. A fixed list silently omits new files after a refactor.
        allowed_root_suffixes = {".py", ".pyw", ".json", ".txt", ".md", ".bat", ".ps1", ".spec"}
        allowed_module_suffixes = {".py", ".json", ".txt", ".md", ".bat", ".ps1"}
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(self.base_dir.iterdir()):
                if path.is_file() and path.suffix.lower() in allowed_root_suffixes:
                    if path.stat().st_size <= 20 * 1024 * 1024:
                        zf.write(path, arcname=path.name)
            for folder_name in ("modules", "pending_modules"):
                folder = self.base_dir / folder_name
                if not folder.exists():
                    continue
                for path in sorted(folder.rglob("*")):
                    if (path.is_file()
                        and not path.is_symlink()
                        and "__pycache__" not in path.parts
                        and path.suffix.lower() in allowed_module_suffixes
                        and path.stat().st_size <= 20 * 1024 * 1024):
                        zf.write(path, arcname=str(path.relative_to(self.base_dir)))
        self.publish("recovery.snapshot", "runtime", {"file": str(target)})
        return str(target)

    def list_snapshots(self):
        folder = self.storage_layout.backups / "recovery"
        if not folder.exists():
            return []
        return [str(p) for p in sorted(folder.glob("*.zip"), reverse=True)]

    def add_goal(self, title, priority=50, notes=""):
        now = _now()
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO goals(title,status,priority,notes,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (str(title), "active", int(priority), str(notes), now, now),
            )
            self.conn.commit()
        return cur.lastrowid

    def update_goal(self, goal_id, status=None, notes=None):
        with self._lock:
            row = self.conn.execute("SELECT * FROM goals WHERE id=?", (int(goal_id),)).fetchone()
            if not row:
                raise KeyError("Goal not found")
            new_status = str(status if status is not None else row["status"])
            new_notes = str(notes if notes is not None else row["notes"])
            self.conn.execute(
                "UPDATE goals SET status=?,notes=?,updated_at=? WHERE id=?",
                (new_status, new_notes, _now(), int(goal_id)),
            )
            self.conn.commit()

    def goals(self, status=None):
        with self._lock:
            if status:
                rows = self.conn.execute(
                    "SELECT * FROM goals WHERE status=? ORDER BY priority DESC,id DESC", (str(status),)
                ).fetchall()
            else:
                rows = self.conn.execute("SELECT * FROM goals ORDER BY priority DESC,id DESC").fetchall()
        return [dict(r) for r in rows]

    def mark_clean_shutdown(self):
        try:
            if self._startup_marker.exists():
                self._startup_marker.unlink()
        finally:
            with self._lock:
                try:
                    self.conn.commit()
                    self.conn.close()
                except Exception:
                    pass


def re_safe(text):
    text = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(text))
    return text[:48] or "snapshot"
