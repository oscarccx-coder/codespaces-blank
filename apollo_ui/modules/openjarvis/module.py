"""Apollo app and chat actions for the real OpenJarvis framework."""
import json
from pathlib import Path
from apollo_openjarvis import Bridge


class Module:
    def __init__(self, context=None):
        self.context = context or {}
        self.base = Path(self.context.get("base_dir") or ".").resolve()
        self.bridge = Bridge(self.base, self.context.get("runtime"))

    def manager(self):
        return getattr(self.context.get("runtime"), "_manager", None)

    def client(self):
        from apollo_config import ApolloConfigStore
        from ollama_client import OllamaClient
        config = ApolloConfigStore(self.base).load()
        client = OllamaClient(config["ollama_url"], config["model"], config.get("temperature", 0.65),
            min(config.get("num_ctx", 8192), 8192), config.get("num_batch", 256), "15m")
        client.strict_model = True
        client.num_predict = self.bridge.settings()["max_tokens"]
        client.think = False
        return client

    def tools(self):
        empty = {"type": "object", "properties": {}}
        query = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
        return [
            {"name": "status", "description": "Read actual OpenJarvis setup and active task state.", "parameters": empty},
            {"name": "readiness", "description": "Check framework setup, the local Ollama service, installed model and Apollo tool availability.", "parameters": empty},
            {"name": "capabilities", "description": "Inspect real upstream agent/engine/tool registries and missing optional dependencies.", "parameters": empty},
            {"name": "run_task", "description": "Carry out a bounded local agent task using Apollo's permitted tools; return actual receipts.", "parameters": query},
            {"name": "runs", "description": "List saved OpenJarvis task receipts.", "parameters": empty},
            {"name": "run_status", "description": "Inspect one saved run and its tool receipts.", "parameters": {"type": "object", "properties": {"run_id": {"type": "string"}}, "required": ["run_id"]}},
            {"name": "search_memory", "description": "Retrieve evidence from Apollo's shared Memory Bank.", "parameters": query},
            {"name": "skills", "description": "List installed upstream and Apollo skills.", "parameters": empty},
            {"name": "run_skill", "description": "Run an installed skill through Apollo's permission broker; context supplies that skill's input variables.", "parameters": {"type": "object", "properties": {"skill": {"type": "string"}, "query": {"type": "string"}, "context": {"type": "object"}}, "required": ["skill", "query"]}},
            {"name": "trace_summary", "description": "Read measured upstream execution trace statistics.", "parameters": empty},
            {"name": "route_task", "description": "Use OpenJarvis's actual router to select among installed local models without changing settings.", "parameters": query},
            {"name": "propose_routing", "description": "Produce a candidate routing policy from execution traces; never activate it automatically.", "parameters": empty},
        ]

    def run(self, action, arguments):
        args = arguments or {}
        if action == "status": return self.bridge.status()
        if action == "readiness":
            from urllib.parse import urlsplit
            checks = {"framework": self.bridge.status()["ready"], "local_endpoint": False, "ollama": False,
                      "model_installed": False, "apollo_tools": self.manager() is not None}
            error = ""
            try:
                client = self.client()
                checks["local_endpoint"] = urlsplit(client.base_url).hostname in {"localhost", "127.0.0.1", "::1"} and "cloud" not in client.model.lower()
                if checks["local_endpoint"]:
                    checks["ollama"] = client.is_running()
                    if checks["ollama"]: checks["model_installed"] = client.model in client.models()
            except Exception as exc: error = str(exc)
            return {"ready": all(checks.values()), "checks": checks, "error": error,
                    "notice": "This checks prerequisites, not the reasoning quality or speed of the selected model."}
        if action == "runs": return {"runs": self.bridge.store.list()}
        if action == "run_status": return self.bridge.store.get(args["run_id"])
        if action == "run_task": return self.bridge.run_task(args["query"], manager=self.manager(), client=self.client())
        operation = {"capabilities": "probe", "search_memory": "memory", "skills": "skills", "run_skill": "skill_run",
                     "trace_summary": "traces", "route_task": "route", "propose_routing": "learn"}.get(action)
        if operation is None: raise KeyError(action)
        values = dict(args)
        if operation in {"route", "learn"}:
            client = self.client(); values.update(models=client.models(), default_model=client.model)
        return self.bridge.request(operation, values, manager=self.manager(), client=self.client() if operation == "skill_run" else None)

    def self_test(self):
        assert len({t["name"] for t in self.tools()}) == len(self.tools())
        assert "ready" in self.bridge.status()
        return "OpenJarvis contracts passed; live inference is a separate readiness check"

    def close(self): self.bridge.close()

    def build_ui(self, parent=None, ui_context=None):
        from apollo_openjarvis_ui import build_view
        return build_view(self, parent)
