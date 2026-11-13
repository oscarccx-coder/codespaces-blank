"""Run the pinned OpenJarvis framework through Apollo's model and tool broker."""
from __future__ import annotations
import json
import os
from pathlib import Path
import queue
import re
import secrets
import sqlite3
import subprocess
import threading
import time
from urllib.parse import urlsplit

PIN = "13706f2b5b5ba6cac9ad31bc575d9e115213784f"
FRAME_LIMIT = 2 * 1024 * 1024
OPERATIONS = {"probe", "agent", "route", "skills", "skill_run", "traces", "learn", "memory"}


def atomic_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + secrets.token_hex(4) + ".tmp")
    try:
        temporary.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class RunStore:
    def __init__(self, base):
        path = Path(base) / "storage/databases/openjarvis_runs.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, goal TEXT, agent TEXT,
                state TEXT, updated REAL, result TEXT DEFAULT '{}', error TEXT DEFAULT '');
            CREATE TABLE IF NOT EXISTS steps(id INTEGER PRIMARY KEY, run_id TEXT,
                kind TEXT, created REAL, payload TEXT);
        """); self.db.commit()

    def create(self, goal, agent):
        ident = secrets.token_hex(6)
        with self.lock, self.db:
            self.db.execute("INSERT INTO runs(id,goal,agent,state,updated) VALUES(?,?,?,?,?)",
                            (ident, goal, agent, "queued", time.time()))
        return ident

    def finish(self, ident, state, result=None, error=""):
        with self.lock, self.db:
            self.db.execute("UPDATE runs SET state=?,updated=?,result=?,error=? WHERE id=?",
                (state, time.time(), json.dumps(result or {}, default=str)[:1000000], str(error)[:4000], ident))

    def step(self, ident, kind, value):
        with self.lock, self.db:
            self.db.execute("INSERT INTO steps(run_id,kind,created,payload) VALUES(?,?,?,?)",
                            (ident, kind, time.time(), json.dumps(value, default=str)[:16000]))

    def list(self):
        with self.lock:
            return [dict(r) for r in self.db.execute(
                "SELECT id,goal,agent,state,updated,error FROM runs ORDER BY updated DESC LIMIT 50")]

    def get(self, ident):
        with self.lock:
            row = self.db.execute("SELECT * FROM runs WHERE id=?", (ident,)).fetchone()
            if row is None: raise KeyError("Unknown OpenJarvis run")
            data = dict(row); data["result"] = json.loads(data["result"])
            data["steps"] = [dict(r) for r in self.db.execute(
                "SELECT kind,created,payload FROM steps WHERE run_id=? ORDER BY id", (ident,))]
            return data

    def recover(self):
        # Explicit recovery never replays possibly completed writes.
        with self.lock, self.db:
            self.db.execute("UPDATE runs SET state='interrupted',error='Interrupted; review receipts before restarting' WHERE state IN ('running','queued')")

    def close(self):
        with self.lock:
            self.db.close()


def select_tools(manager, query):
    if manager is None: return []
    words = {w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2}
    candidates = []
    for tool in manager.ollama_tools():
        fn = tool["function"]; name = fn["name"]
        if name.startswith("openjarvis__"): continue
        score = sum(w in (name + " " + fn.get("description", "")).lower() for w in words)
        if score or name.startswith(("calculator__", "memory_bank__", "web_explorer__", "file_manager__")):
            candidates.append((score, name, tool))
    return [v[2] for v in sorted(candidates, key=lambda v: (-v[0], v[1]))[:32]]


class Bridge:
    def __init__(self, base, runtime=None):
        self.base = Path(base).resolve(); self.runtime = runtime
        self.source = self.base / "vendor/openjarvis"
        self.data = self.base / "storage/openjarvis"
        self.worker = Path(__file__).with_name("openjarvis_worker.py")
        self.settings_file = self.base / "storage/state/openjarvis.json"
        self.python = self.base / "storage/environments/openjarvis" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        self.store = RunStore(base)
        self.lock = threading.Lock(); self.state_lock = threading.RLock()
        self.process = None; self.client = None; self.active_run = None
        self.cancelled = threading.Event(); self.closed = False

    def settings(self):
        value = {"enabled": True, "agent": "orchestrator", "max_turns": 8, "max_tokens": 1024, "timeout": 240}
        try: saved = json.loads(self.settings_file.read_text(encoding="utf-8"))
        except FileNotFoundError: saved = {}
        if not isinstance(saved, dict): raise ValueError("Malformed OpenJarvis settings")
        return {**value, **saved}

    def configure(self, enabled=None, agent=None):
        value = self.settings()
        if enabled is not None: value["enabled"] = bool(enabled)
        if agent is not None: value["agent"] = str(agent)
        atomic_json(self.settings_file, value)
        return value

    def status(self):
        try: receipt = json.loads((self.data / "installation.json").read_text(encoding="utf-8"))
        except (OSError, ValueError): receipt = {}
        source = (self.source / "src/openjarvis/sdk.py").is_file()
        ready = source and self.python.is_file() and receipt.get("commit") == PIN
        return {"ready": bool(ready), "source_present": source, "environment_present": self.python.is_file(),
                "commit": PIN, "enabled": self.settings()["enabled"], "active_run": self.active_run,
                "installation": receipt, "setup": "Setup/19_SETUP_OPENJARVIS.bat",
                "message": "Framework ready; check model readiness before the first task" if ready else "Finish OpenJarvis setup in Apps → OpenJarvis"}

    def publish(self, topic, data):
        if self.runtime: self.runtime.publish(topic, "openjarvis", data)

    def cancel(self):
        self.cancelled.set()
        with self.state_lock:
            if self.client: self.client.cancel_generation()
            if self.process and self.process.poll() is None: self.process.terminate()

    def request(self, operation, arguments=None, *, manager=None, client=None, on_chunk=None, on_event=None, run_id=None):
        if operation not in OPERATIONS: raise ValueError("Unsupported OpenJarvis operation")
        if self.closed: raise RuntimeError("OpenJarvis is closed")
        if not self.python.is_file(): raise RuntimeError(self.status()["message"])
        if not self.lock.acquire(False): raise RuntimeError("An OpenJarvis task is already running")
        process = None; timer = None; expired = threading.Event()
        old_options = None
        try:
            if operation != "agent": self.cancelled.clear()
            args = dict(arguments or {})
            if client is not None:
                if urlsplit(client.base_url).hostname not in {"localhost", "127.0.0.1", "::1"} or "cloud" in client.model.lower():
                    raise PermissionError("OpenJarvis uses a local Ollama model only")
                args["model"] = client.model
                old_options = (client.num_predict, client.think, client.keep_alive)
                if client.num_predict is None: client.num_predict = self.settings()["max_tokens"]
                if client.think is None: client.think = False
                client.keep_alive = "15m"
            specs = select_tools(manager, str(args.get("query", "")))
            allowed = {s["function"]["name"] for s in specs}
            args.update(tools=specs, settings=self.settings(), data_dir=str(self.data))
            env = dict(os.environ); env.update(PYTHONUNBUFFERED="1", OPENJARVIS_HOME=str(self.data / "framework"),
                PYTHONPATH=str(self.source / "src"), DO_NOT_TRACK="1")
            self.data.mkdir(parents=True, exist_ok=True)
            with (self.data / "worker.log").open("a", encoding="utf-8") as log:
                process = subprocess.Popen([str(self.python), "-u", str(self.worker)],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True, encoding="utf-8",
                    cwd=self.data, env=env, **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
            with self.state_lock: self.process, self.client = process, client
            def expire():
                expired.set()
                if client: client.cancel_generation()
                if process.poll() is None: process.terminate()
            timer = threading.Timer(self.settings()["timeout"], expire); timer.daemon = True; timer.start()
            packets = queue.Queue(maxsize=128)
            def read():
                try:
                    while True:
                        line = process.stdout.readline(FRAME_LIMIT + 1)
                        if not line: break
                        if len(line) > FRAME_LIMIT: raise ValueError("Worker frame too large")
                        packets.put(json.loads(line), timeout=1)
                except Exception as exc:
                    try: packets.put({"error": str(exc)}, timeout=1)
                    except queue.Full: pass
                finally:
                    try: packets.put({"eof": True}, timeout=1)
                    except queue.Full: pass
            threading.Thread(target=read, daemon=True).start()
            def send(value):
                encoded = json.dumps(value, default=str)
                if len(encoded) > FRAME_LIMIT: raise ValueError("Request frame too large")
                process.stdin.write(encoded + "\n"); process.stdin.flush()
            send({"operation": operation, "arguments": args})
            tool_count = 0
            while True:
                if expired.is_set(): raise TimeoutError("OpenJarvis reached its time budget")
                if self.cancelled.is_set(): raise RuntimeError("OpenJarvis task cancelled")
                try: packet = packets.get(timeout=0.1)
                except queue.Empty: continue
                if packet.get("callback"):
                    kind = packet["callback"]; payload = packet.get("arguments", {})
                    try:
                        if kind == "generate":
                            if client is None: raise RuntimeError("No model client attached")
                            if payload.get("stream") and not payload.get("tools"):
                                chunks = []
                                for chunk in client.stream_chat(payload["messages"]):
                                    chunks.append(chunk)
                                    if on_chunk: on_chunk(chunk)
                                result = {"content": "".join(chunks), "tool_calls": [], "metrics": client.last_metrics}
                            else:
                                raw = client.chat_once(payload["messages"], tools=payload.get("tools"))
                                result = {"content": raw.get("message", {}).get("content", ""),
                                          "tool_calls": raw.get("message", {}).get("tool_calls", []), "metrics": client.last_metrics}
                        elif kind == "tool":
                            tool_count += 1; name = payload.get("name", "")
                            if tool_count > 28: raise RuntimeError("Tool-call budget exhausted")
                            if name not in allowed or manager is None: raise PermissionError("Tool is outside this run's grant")
                            if on_event: on_event({"type": "tool_started", "name": name})
                            result = manager.execute_tool(name, payload.get("arguments") or {})
                            if on_event: on_event({"type": "tool_finished", "name": name, "result": result})
                        elif kind == "memory":
                            if manager is None: result = {"text": "", "notice": "Memory disabled"}
                            else: result = manager.execute_tool("memory_bank__knowledge_context", {"query": payload["query"], "limit": 4, "max_chars": 3000})
                        else: raise PermissionError("Unknown callback")
                        reply = {"id": packet["id"], "result": result}
                    except Exception as exc: reply = {"id": packet["id"], "error": f"{type(exc).__name__}: {exc}"}
                    if run_id: self.store.step(run_id, kind, {"name": payload.get("name"), "error": reply.get("error")})
                    send(reply)
                elif packet.get("event"):
                    self.publish("openjarvis.activity", packet["event"])
                elif "result" in packet: return packet["result"]
                elif packet.get("error"): raise RuntimeError(packet["error"])
                elif packet.get("eof"): raise RuntimeError("Worker exited without a result; inspect storage/openjarvis/worker.log")
        finally:
            if timer: timer.cancel()
            if process:
                if process.poll() is None: process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=3)
                for pipe in (process.stdin, process.stdout):
                    if pipe: pipe.close()
            with self.state_lock: self.process, self.client = None, None
            if old_options is not None:
                client.num_predict, client.think, client.keep_alive = old_options
            self.lock.release()

    def run_task(self, query, *, manager=None, client=None, messages=None, agent=None, on_chunk=None, on_event=None):
        query = str(query).strip()
        if not query or len(query) > 12000: raise ValueError("Task must contain 1–12000 characters")
        with self.state_lock:
            if self.active_run is not None: raise RuntimeError("An OpenJarvis task is already active")
            self.cancelled.clear()
            ident = self.store.create(query, agent or self.settings()["agent"]); self.active_run = ident
        self.store.finish(ident, "running"); self.publish("openjarvis.started", {"run_id": ident})
        try:
            result = self.request("agent", {"query": query, "agent": agent or self.settings()["agent"], "messages": messages or []},
                manager=manager, client=client, on_chunk=on_chunk, on_event=on_event, run_id=ident)
            result["run_id"] = ident
            state = "completed" if result.get("completed") else "blocked"
            self.store.finish(ident, state, result); self.publish("openjarvis.finished", {"run_id": ident, "state": state})
            return result
        except Exception as exc:
            self.store.finish(ident, "cancelled" if self.cancelled.is_set() else "failed", error=str(exc)); raise
        finally:
            with self.state_lock: self.active_run = None
            if self.closed: self.store.close()

    def close(self):
        self.closed = True; self.cancel()
        if self.active_run is None and not self.lock.locked(): self.store.close()
