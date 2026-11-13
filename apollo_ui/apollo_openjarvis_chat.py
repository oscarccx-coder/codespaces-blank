"""Deterministic owner commands, plus the integrated Chat execution path."""
import json
import re


def command(text):
    text = str(text).strip()
    if re.fullmatch(r"(?:openjarvis|jarvis)\s+(status|runs|skills|stop|capabilities)[.!?]?", text, re.I):
        return {"action": re.fullmatch(r"(?:openjarvis|jarvis)\s+(status|runs|skills|stop|capabilities)[.!?]?", text, re.I)[1].lower()}
    match = re.fullmatch(r"(?:openjarvis|jarvis)\s+do\s*:\s*(.{1,12000})", text, re.I | re.S)
    return {"action": "task", "query": match[1]} if match else None


def handle(task, owner_text):
    manager = task.module_manager
    if manager is None: return None
    record = manager.get_module("openjarvis")
    instance = record.get("instance") if record and record.get("enabled") else None
    if instance is None: return None
    parsed = command(owner_text)
    if parsed and parsed["action"] != "task":
        if parsed["action"] == "stop": instance.bridge.cancel(); return "OpenJarvis stop requested. Saved receipts remain available."
        return json.dumps(instance.run(parsed["action"], {}), indent=2, default=str)
    status = instance.bridge.status()
    if not parsed and (not status["ready"] or not status["enabled"]): return None
    if parsed and not status["ready"]: return status["message"]
    if getattr(task, "work_mode", "Chat") != "Chat" and not parsed: return None
    bridge = instance.bridge
    task._openjarvis_bridge = bridge
    def event(value):
        if value["type"] == "tool_started": task.signals.tool_started.emit(value["name"])
        elif value["type"] == "tool_finished": task.signals.tool_used.emit(value["name"], json.dumps(value["result"], default=str))
    try:
        if task._cancelled: return ""
        result = bridge.run_task(parsed["query"] if parsed else owner_text, manager=manager, client=task.client,
            messages=task.messages, on_chunk=task.signals.chunk.emit, on_event=event)
        if not result.get("streamed"): task.signals.chunk.emit(result["content"])
        return result["content"]
    finally: task._openjarvis_bridge = None
