"""Isolated interpreter for Apollo's pinned OpenJarvis source.

Trusted agent logic lives here. Every inference and tool action is returned to
Apollo over stdio; generated Python is never executed by this interpreter.
"""
from __future__ import annotations
from dataclasses import asdict, replace
import importlib
import inspect
import json
import os
from pathlib import Path
import sys
import threading
import time
import traceback

SOURCE = Path(__file__).resolve().parent / "vendor/openjarvis"
sys.path.insert(0, str(SOURCE / "src"))
LIMIT = 2 * 1024 * 1024
IO_LOCK = threading.RLock()
SEQUENCE = 0


def emit(value):
    text = json.dumps(value, default=str)
    if len(text) > LIMIT: raise ValueError("Worker response exceeds frame limit")
    sys.stdout.write(text + "\n"); sys.stdout.flush()


def callback(kind, arguments):
    global SEQUENCE
    with IO_LOCK:
        SEQUENCE += 1; ident = SEQUENCE
        emit({"callback": kind, "id": ident, "arguments": arguments})
        line = sys.stdin.readline(LIMIT + 1)
        if not line or len(line) > LIMIT: raise RuntimeError("Apollo disconnected")
        response = json.loads(line)
        if response.get("id") != ident: raise RuntimeError("Callback correlation failed")
        if response.get("error"): raise RuntimeError(response["error"])
        return response.get("result")


class BrokerPolicy:
    def __init__(self, names): self.names = frozenset(names)
    def check(self, agent_id, capability, resource=""):
        return capability == "apollo:dispatch" and resource in self.names


def make_tools(specs):
    from openjarvis.tools._stubs import BaseTool, ToolSpec
    from openjarvis.core.types import ToolResult
    class ApolloTool(BaseTool):
        is_local = True
        def __init__(self, spec): self.definition = spec["function"]; self.tool_id = self.definition["name"]
        @property
        def spec(self):
            return ToolSpec(name=self.tool_id, description=self.definition.get("description", ""),
                parameters=self.definition.get("parameters", {}), required_capabilities=["apollo:dispatch"], timeout_seconds=120)
        def execute(self, **arguments):
            try:
                result = callback("tool", {"name": self.tool_id, "arguments": arguments})
                bad = isinstance(result, dict) and (result.get("ok") is False or result.get("success") is False
                      or result.get("status") in {"failed", "denied", "unavailable", "incomplete"})
                return ToolResult(tool_name=self.tool_id, content=json.dumps(result, default=str), success=not bad)
            except Exception as exc:
                return ToolResult(tool_name=self.tool_id, content=str(exc), success=False)
    return [ApolloTool(spec) for spec in specs]


def skill_bindings(specs):
    """Translate upstream skill names into uniquely named, brokered Apollo tools.

    Never grant native `file_read` / `web_search` names: that would also permit
    an agent to construct the native implementation outside Apollo's broker.
    """
    from openjarvis.tools._stubs import BaseTool, ToolSpec
    from openjarvis.core.types import ToolResult
    targets = {s["function"]["name"] for s in specs}
    mapping = {"file_read": "file_manager__read_text", "file_write": "file_manager__write_text",
               "web_search": "web_explorer__search_web", "calculator": "calculator__calculate",
               "memory_search": "memory_bank__search_memory_bank", "memory_store": "memory_bank__store_memory"}
    class BoundTool(BaseTool):
        is_local = True
        def __init__(self, alias, target): self.alias = alias; self.target = target; self.tool_id = "apollo_skill__" + alias
        @property
        def spec(self):
            return ToolSpec(name=self.tool_id, description="Apollo binding for " + self.alias,
                            parameters={"type": "object", "properties": {}}, required_capabilities=["apollo:dispatch"])
        def execute(self, **params):
            try:
                if self.alias == "think":
                    value = callback("generate", {"messages": [{"role": "user", "content": str(params.get("thought", ""))}], "stream": False})
                    return ToolResult(tool_name=self.tool_id, content=value["content"], success=bool(value["content"].strip()))
                if self.alias in {"file_read", "file_write"}: params["root"] = "workspace"
                if self.alias == "memory_store":
                    params = {"name": "OpenJarvis skill: " + str(params.get("metadata", "note"))[:120],
                              "content": str(params.get("content", "")), "memory_type": "research",
                              "source": "OpenJarvis skill (unverified)", "tags": ["openjarvis", "unverified"]}
                value = callback("tool", {"name": self.target, "arguments": params})
                return ToolResult(tool_name=self.tool_id, content=json.dumps(value, default=str),
                                  success=not (isinstance(value, dict) and (value.get("ok") is False or value.get("success") is False)))
            except Exception as exc: return ToolResult(tool_name=self.tool_id, content=str(exc), success=False)
    tools = [BoundTool(alias, target) for alias, target in mapping.items() if target in targets]
    tools.append(BoundTool("think", ""))
    aliases = {tool.alias: tool.tool_id for tool in tools}
    return tools, aliases


def make_engine(model, bus, stream=False):
    from openjarvis.engine._stubs import InferenceEngine
    from openjarvis.engine._base import messages_to_dicts
    from openjarvis.core.events import EventType
    class ApolloEngine(InferenceEngine):
        engine_id = "apollo"; is_cloud = False
        def generate(self, messages, *, model, temperature=0.35, max_tokens=1024, **kwargs):
            bus.publish(EventType.INFERENCE_START, {"model": model, "engine": "apollo"})
            start = time.monotonic()
            raw = callback("generate", {"messages": messages_to_dicts(messages), "tools": kwargs.get("tools"),
                                       "stream": stream, "max_tokens": max_tokens, "temperature": temperature})
            metrics = raw.pop("metrics", {})
            raw["usage"] = {"prompt_tokens": metrics.get("prompt_eval_count", 0),
                            "completion_tokens": metrics.get("eval_count", 0),
                            "total_tokens": metrics.get("prompt_eval_count", 0) + metrics.get("eval_count", 0)}
            raw["tool_calls"] = [{"id": item.get("id", f"call_{i}"),
                "name": item.get("function", item).get("name", ""),
                "arguments": json.dumps(item.get("function", item).get("arguments", {}))
                if not isinstance(item.get("function", item).get("arguments", {}), str)
                else item.get("function", item)["arguments"]} for i, item in enumerate(raw.get("tool_calls", []))]
            bus.publish(EventType.INFERENCE_END, {"model": model, "engine": "apollo", "usage": raw["usage"],
                "latency_seconds": time.monotonic() - start})
            return raw
        async def stream(self, messages, *, model, **kwargs):
            yield self.generate(messages, model=model, **kwargs).get("content", "")
        def list_models(self): return [model]
        def health(self): return True
    return ApolloEngine()


def inventory():
    from openjarvis.core import registry
    failures = {}
    for name in ("agents", "engine", "tools", "learning", "skills", "channels", "evals"):
        try: importlib.import_module("openjarvis." + name)
        except Exception as exc: failures[name] = f"{type(exc).__name__}: {exc}"
    registries = {name: list(getattr(registry, name).keys()) for name in (
        "AgentRegistry", "EngineRegistry", "MemoryRegistry", "ToolRegistry", "RouterPolicyRegistry",
        "LearningRegistry", "ChannelRegistry", "BenchmarkRegistry")}
    from openjarvis._rust_bridge import RUST_AVAILABLE
    return {"registries": registries, "native_extension": RUST_AVAILABLE,
            "optional_dependencies": failures, "python_version": sys.version.split()[0],
            "notice": "Registration is not a readiness check. Cloud accounts, native extensions and external services remain optional and must be configured."}


def agent_task(args):
    import openjarvis.agents
    from openjarvis.core.registry import AgentRegistry
    from openjarvis.core.events import EventBus, EventType
    from openjarvis.core.types import Message, Role
    from openjarvis.agents._stubs import AgentContext
    from openjarvis.traces.store import TraceStore
    from openjarvis.traces.collector import TraceCollector
    name = args.get("agent", "orchestrator"); cls = AgentRegistry.get(name)
    if getattr(cls, "uses_direct_operations", False) or ".hybrid." in cls.__module__:
        raise PermissionError(f"{name} needs its external execution adapter. Use Apollo Foundry for sandboxed coding; cloud access is not enabled by this integration.")
    bus = EventBus()
    for event in (EventType.TOOL_CALL_START, EventType.TOOL_CALL_END, EventType.LOOP_GUARD_TRIGGERED):
        bus.subscribe(event, lambda value: emit({"event": {"type": value.event_type.value}}))
    tools = make_tools(args.get("tools", [])); policy = BrokerPolicy([tool.tool_id for tool in tools])
    engine = make_engine(args["model"], bus, stream=name == "simple")
    kwargs = {"bus": bus, "temperature": 0.35, "max_tokens": args["settings"]["max_tokens"],
              "capability_policy": policy, "agent_id": name}
    if getattr(cls, "accepts_tools", False): kwargs.update(tools=tools, max_turns=args["settings"]["max_turns"])
    signature = inspect.signature(cls.__init__)
    if not any(p.kind == p.VAR_KEYWORD for p in signature.parameters.values()):
        kwargs = {key: value for key, value in kwargs.items() if key in signature.parameters}
    agent = cls(engine, args["model"], **kwargs)
    context = AgentContext()
    for message in args.get("messages", [])[:-1]:
        if message.get("role") in {"system", "user", "assistant"}:
            context.conversation.add(Message(role=Role(message["role"]), content=str(message.get("content", ""))))
    store = TraceStore(str(Path(args["data_dir"]) / "traces.db"))
    try:
        collector = TraceCollector(agent, store=store, bus=bus)
        result = collector.run(args["query"], context=context)
        failed = any(not item.success for item in result.tool_results)
        exhausted = result.metadata.get("max_turns_exceeded", False) or result.metadata.get("reason") == "max_turns"
        # Upstream's turn-limit return has a separate metadata marker.
        exhausted = exhausted or bool(result.metadata.get("max_turns_reached"))
        completed = bool(result.content.strip()) and not failed and not exhausted
        content = result.content
        if not completed:
            reasons = [f"{item.tool_name}: {item.content[:600]}" for item in result.tool_results if not item.success]
            if exhausted: reasons.append("Agent turn budget exhausted")
            content = "Task incomplete.\n" + "\n".join(reasons or ["No final answer was produced."])
        return {"content": content, "completed": completed, "agent": name, "turns": result.turns,
                "streamed": name == "simple", "tool_results": [asdict(item) for item in result.tool_results],
                "metadata": result.metadata, "trace_id": collector.last_trace.trace_id if collector.last_trace else None,
                "verification": "Tool receipts checked; final prose is model-generated"}
    finally: store.close()


def dispatch(operation, args):
    root = Path(args["data_dir"]); root.mkdir(parents=True, exist_ok=True)
    if operation == "probe": return inventory()
    if operation == "agent": return agent_task(args)
    if operation == "route":
        from openjarvis.learning.routing.router import HeuristicRouter, build_routing_context
        context = build_routing_context(args["query"])
        model = HeuristicRouter(args.get("models", []), default_model=args.get("default_model", "")).select_model(context)
        return {"model": model, "analysis": asdict(context), "policy": "openjarvis.heuristic"}
    if operation == "memory": return callback("memory", {"query": args["query"]})
    if operation in {"traces", "learn"}:
        from openjarvis.traces.store import TraceStore
        from openjarvis.traces.analyzer import TraceAnalyzer
        store = TraceStore(str(root / "traces.db"))
        try:
            analyzer = TraceAnalyzer(store)
            if operation == "traces": return asdict(analyzer.summary())
            from openjarvis.learning.routing.learned_router import LearnedRouterPolicy
            policy = LearnedRouterPolicy(analyzer=analyzer, available_models=args.get("models", []))
            result = {"analysis": policy.update_from_traces(), "policy_map": policy.policy_map,
                      "state": "candidate", "adopted": False}
            (root / "routing_candidate.json").write_text(json.dumps(result, default=str, indent=2), encoding="utf-8")
            return result
        finally: store.close()
    if operation in {"skills", "skill_run"}:
        from openjarvis.skills.loader import discover_skills
        skills = {s.name: s for directory in (SOURCE / "src/openjarvis/skills/data", root / "skills")
                  if directory.is_dir() for s in discover_skills(directory)}
        if operation == "skills": return {"skills": [asdict(s) for s in skills.values()]}
        from openjarvis.skills.executor import SkillExecutor
        from openjarvis.tools._stubs import ToolExecutor
        tools, aliases = skill_bindings(args.get("tools", []))
        # Copy manifests for this run; retain upstream files and provenance.
        skills = {name: replace(skill, steps=[replace(step, tool_name=aliases.get(step.tool_name, step.tool_name))
                                            for step in skill.steps]) for name, skill in skills.items()}
        policy = BrokerPolicy([tool.tool_id for tool in tools])
        executor = ToolExecutor(tools, capability_policy=policy, agent_id="apollo_skill")
        active = set()
        def execute(name, context):
            if name in active or len(active) >= 8: raise ValueError("Skill dependency cycle/depth limit")
            active.add(name)
            try:
                instance = SkillExecutor(executor, allowed_capabilities={"apollo:dispatch"})
                instance.set_skill_resolver(execute)
                return instance.run(skills[name], initial_context=context)
            finally: active.remove(name)
        result = execute(args["skill"], args.get("context", {}))
        return asdict(result)
    raise ValueError("Unknown operation")


def main():
    line = sys.stdin.readline(LIMIT + 1)
    if not line or len(line) > LIMIT: raise ValueError("Invalid worker request")
    request = json.loads(line)
    os.environ["OPENJARVIS_HOME"] = str(Path(request["arguments"]["data_dir"]) / "framework")
    emit({"result": dispatch(request["operation"], request["arguments"])})


if __name__ == "__main__":
    try: main()
    except Exception as exc:
        traceback.print_exc(file=sys.stderr); emit({"error": f"{type(exc).__name__}: {exc}"}); sys.exit(1)
