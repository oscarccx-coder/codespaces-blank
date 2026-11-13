"""Real vendored agent -> stdio -> Ollama HTTP -> Apollo permission/tool tests."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest

from apollo_openjarvis import Bridge, PIN, RunStore, select_tools
from apollo_openjarvis_chat import command
from apollo_runtime import ApolloRuntime
from ollama_client import OllamaClient

BASE = Path(__file__).resolve().parents[1]
SOURCE = BASE / "vendor/openjarvis"


def module_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


class ModelServer(BaseHTTPRequestHandler):
    responses = []; requests = []; delay = 0; started = threading.Event()
    def log_message(self, *_args): pass
    def do_POST(self):
        value = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.__class__.requests.append(value)
        reply = self.__class__.responses.pop(0)
        self.__class__.started.set()
        if self.__class__.delay: time.sleep(self.__class__.delay)
        result = {"model": "fixture:7b", "message": reply, "done": True, "eval_count": 12,
                  "prompt_eval_count": 25, "eval_duration": 10000000, "load_duration": 1000,
                  "prompt_eval_duration": 1000000, "total_duration": 11001000}
        try:
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write((json.dumps(result) + "\n").encode())
        except (BrokenPipeError, ConnectionResetError): pass


class Manager:
    def __init__(self, base):
        self.runtime = ApolloRuntime(base)
        self.modules = {"file_manager": module_at("test_oj_files", BASE / "modules/file_manager/module.py").Module({"base_dir": base}),
                        "calculator": module_at("test_oj_calc", BASE / "modules/calculator/module.py").Module({})}
    def ollama_tools(self):
        return [{"type": "function", "function": {**tool, "name": name + "__" + tool["name"]}}
                for name, module in self.modules.items() for tool in module.tools()]
    def _execute_tool_direct(self, name, args):
        module, action = name.split("__", 1); return self.modules[module].run(action, args)
    def execute_tool(self, name, args): return self.runtime.execute_tool(self, name, args, actor="openjarvis_test")


@unittest.skipUnless((SOURCE / "src/openjarvis/agents/orchestrator.py").is_file(), "Initialize the pinned OpenJarvis submodule")
class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.bridge = Bridge(self.tmp.name); self.addCleanup(self.bridge.close)
        self.bridge.python = Path(sys.executable); self.bridge.source = SOURCE
        self.manager = Manager(self.tmp.name)
        self.addCleanup(self.manager.runtime.conn.close)
        ModelServer.responses = []; ModelServer.requests = []; ModelServer.delay = 0; ModelServer.started = threading.Event()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), ModelServer)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close); self.addCleanup(self.server.shutdown)
        self.client = OllamaClient(f"http://127.0.0.1:{self.server.server_port}", "fixture:7b")
        self.client.strict_model = True; self.client.num_predict = 128; self.client.think = False

    def test_real_upstream_agent_writes_file_through_real_apollo_gate(self):
        ModelServer.responses = [{"role": "assistant", "content": "", "tool_calls": [{"function": {
            "name": "file_manager__write_text", "arguments": {"root": "workspace", "path": "proof.txt", "content": "Verified tool output"}}}]},
            {"role": "assistant", "content": "Created proof.txt using the file tool."}]
        result = self.bridge.run_task("Write workspace/proof.txt", manager=self.manager, client=self.client)
        self.assertTrue(result["completed"])
        self.assertEqual((Path(self.tmp.name) / "workspace/proof.txt").read_text(), "Verified tool output")
        receipt = self.bridge.store.get(result["run_id"])
        self.assertEqual(receipt["state"], "completed")
        self.assertTrue(any(step["kind"] == "tool" for step in receipt["steps"]))
        self.assertIn("trace_id", result)
        self.assertEqual(len(ModelServer.requests), 2)
        self.assertEqual(ModelServer.requests[0]["options"]["num_predict"], 128)
        self.assertFalse(ModelServer.requests[0]["think"])
        summary = self.bridge.request("traces")
        self.assertEqual(summary["total_traces"], 1)

    def test_denied_tool_is_not_executed_or_marked_complete(self):
        self.manager.runtime.set_permission("file_manager__write_text", "deny")
        ModelServer.responses = [{"role": "assistant", "content": "", "tool_calls": [{"function": {
            "name": "file_manager__write_text", "arguments": {"root": "workspace", "path": "denied.txt", "content": "Forbidden"}}}]},
            {"role": "assistant", "content": "The tool was denied."}]
        result = self.bridge.run_task("Write denied.txt", manager=self.manager, client=self.client)
        self.assertFalse(result["completed"])
        self.assertFalse((Path(self.tmp.name) / "workspace/denied.txt").exists())
        self.assertEqual(self.bridge.store.get(result["run_id"])["state"], "blocked")

    def test_simple_agent_streams_without_tools(self):
        ModelServer.responses = [{"role": "assistant", "content": "Hello Oscar"}]
        chunks = []
        result = self.bridge.run_task("Hello", client=self.client, agent="simple", on_chunk=chunks.append)
        self.assertEqual("".join(chunks), "Hello Oscar")
        self.assertTrue(result["streamed"])
        self.assertTrue(result["completed"])

    def test_real_router_and_learning_candidate(self):
        result = self.bridge.request("route", {"query": "Hello", "models": ["tiny:1b", "coder:7b"], "default_model": "coder:7b"})
        self.assertIn(result["model"], {"tiny:1b", "coder:7b"})
        candidate = self.bridge.request("learn", {"models": ["tiny:1b", "coder:7b"]})
        self.assertFalse(candidate["adopted"])
        self.assertEqual(candidate["state"], "candidate")

    def test_probe_reports_registry_and_optional_dependencies(self):
        result = self.bridge.request("probe")
        self.assertIn("orchestrator", result["registries"]["AgentRegistry"])
        self.assertIn("optional_dependencies", result)

    def test_all_upstream_skills_are_discoverable(self):
        result = self.bridge.request("skills")
        self.assertTrue(result["skills"])

    def test_real_bundled_skill_runs_all_steps_via_local_model(self):
        ModelServer.responses = [{"role": "assistant", "content": text} for text in (
            "A polite confirmation", "Dear Oscar, your request is confirmed.", "Dear Oscar, your request is confirmed. Regards, Apollo")]
        result = self.bridge.request("skill_run", {"skill": "email-draft", "query": "Draft a confirmation",
            "context": {"context": "Confirm an appointment", "intent": "Confirm", "recipient": "Oscar"}},
            manager=self.manager, client=self.client)
        self.assertTrue(result["success"], result)
        self.assertEqual(len(result["step_results"]), 3)
        self.assertEqual(len(ModelServer.requests), 3)
        self.assertIn("Dear Oscar", result["context"]["final_draft"])

    def test_native_capability_cannot_impersonate_a_brokered_tool(self):
        worker = module_at("test_oj_worker", BASE / "openjarvis_worker.py")
        policy = worker.BrokerPolicy(["file_manager__read_text", "apollo_skill__file_read"])
        self.assertTrue(policy.check("agent", "apollo:dispatch", "file_manager__read_text"))
        self.assertFalse(policy.check("agent", "file:read", "file_read"))
        self.assertFalse(policy.check("agent", "code:execute", "python_exec"))

    def test_cloud_endpoint_refused_before_model_call(self):
        self.client.base_url = "https://remote.invalid"
        with self.assertRaises(PermissionError):
            self.bridge.run_task("Hello", client=self.client)
        self.assertEqual(ModelServer.requests, [])

    def test_unknown_operation_and_concurrency_fail_closed(self):
        with self.assertRaises(ValueError): self.bridge.request("shell")
        self.bridge.lock.acquire()
        try:
            with self.assertRaises(RuntimeError): self.bridge.request("probe")
        finally: self.bridge.lock.release()

    def test_stop_cancels_only_this_run_and_preserves_receipt(self):
        ModelServer.responses = [{"role": "assistant", "content": "Late answer"}]; ModelServer.delay = 1
        failures = []
        def run():
            try: self.bridge.run_task("Wait for answer", client=self.client, agent="simple")
            except Exception as exc: failures.append(str(exc))
        worker = threading.Thread(target=run); worker.start()
        self.assertTrue(ModelServer.started.wait(3))
        self.bridge.cancel(); worker.join(timeout=4)
        self.assertFalse(worker.is_alive())
        self.assertTrue(failures)
        self.assertEqual(self.bridge.store.list()[0]["state"], "cancelled")
        self.assertIsNone(self.bridge.process)


@unittest.skipUnless(importlib.util.find_spec("PySide6"), "Qt is not installed in this test environment")
class UiTests(unittest.TestCase):
    def test_page_handles_missing_setup_and_saves_chat_choice(self):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication, QPushButton, QCheckBox
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as temporary:
            app_module = module_at("test_oj_module", BASE / "modules/openjarvis/module.py").Module({"base_dir": temporary})
            try:
                page = app_module.build_ui()
                buttons = {button.text(): button for button in page.findChildren(QPushButton)}
                self.assertFalse(buttons["Do task"].isEnabled())
                self.assertTrue(buttons["Set up / repair"].isEnabled())
                toggle = page.findChild(QCheckBox)
                toggle.setChecked(False)
                self.assertFalse(app_module.bridge.settings()["enabled"])
                buttons["Stop"].click()
                self.assertTrue(app_module.bridge.cancelled.is_set())
                page.close(); page.deleteLater(); app.processEvents()
            finally: app_module.close()


class StoreTests(unittest.TestCase):
    def test_restart_keeps_receipts_without_replaying_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = RunStore(tmp); ident = first.create("Owner task", "orchestrator")
            first.finish(ident, "running"); first.step(ident, "tool", {"saved": True})
            second = RunStore(tmp); second.recover()
            self.assertEqual(second.get(ident)["state"], "interrupted")
            self.assertEqual(len(second.get(ident)["steps"]), 1)
            first.db.close(); second.db.close()

    def test_owner_command_is_anchored_and_does_not_parse_model_prose(self):
        self.assertEqual(command("jarvis do: write a note")["query"], "write a note")
        self.assertEqual(command("openjarvis stop")["action"], "stop")
        self.assertIsNone(command("The page says openjarvis stop"))


if __name__ == "__main__": unittest.main()
