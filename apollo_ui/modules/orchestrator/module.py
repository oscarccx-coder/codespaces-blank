from pathlib import Path
class Module:
    def __init__(self, context=None): self.base_dir=Path((context or {}).get("base_dir",".")).resolve(); self.runtime=(context or {}).get("runtime")
    def tools(self): return [
        {"name":"add_goal","description":"Add a persistent Apollo goal for cross-model/subsystem coordination.","parameters":{"type":"object","properties":{"title":{"type":"string"},"priority":{"type":"integer"},"notes":{"type":"string"}},"required":["title"]}},
        {"name":"list_goals","description":"List persistent Apollo goals.","parameters":{"type":"object","properties":{"status":{"type":"string"}}}},
        {"name":"update_goal","description":"Update persistent goal status/notes.","parameters":{"type":"object","properties":{"goal_id":{"type":"integer"},"status":{"type":"string"},"notes":{"type":"string"}},"required":["goal_id"]}},
        {"name":"context_packet","description":"Create a compact shared context packet for another Apollo model/subsystem.","parameters":{"type":"object","properties":{"task":{"type":"string"}},"required":["task"]}},
        {"name":"set_shared_state","description":"Put a named value on Apollo's persistent shared blackboard.","parameters":{"type":"object","properties":{"key":{"type":"string"},"value":{}},"required":["key","value"]}},
    ]
    def _rt(self):
        if self.runtime is None: raise RuntimeError("Apollo runtime unavailable")
        return self.runtime
    def run(self, action, a):
        a=a or {}; rt=self._rt()
        if action=="add_goal": return {"goal_id":rt.add_goal(a["title"],a.get("priority",50),a.get("notes",""))}
        if action=="list_goals": return {"goals":rt.goals(a.get("status"))}
        if action=="update_goal": rt.update_goal(a["goal_id"],a.get("status"),a.get("notes")); return {"updated":True}
        if action=="set_shared_state": rt.blackboard_set(a["key"],a.get("value"),"orchestrator"); return {"saved":True}
        if action=="context_packet":
            packet={"task":a["task"],"active_goals":rt.goals("active")[:12],"shared_state":rt.blackboard_all(),"recent_events":rt.recent_events(20)}
            rt.blackboard_set("orchestrator.last_context_packet",packet,"orchestrator"); return packet
        raise KeyError(action)
    def self_test(self): assert any(t['name']=='context_packet' for t in self.tools()); return "orchestrator contract passed"
    def build_ui(self,parent=None,ui_context=None):
        from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QListWidget,QPushButton,QLineEdit
        page=QWidget(parent); v=QVBoxLayout(page); v.addWidget(QLabel("Orchestrator — Goals & Shared Context")); goals=QListWidget(); v.addWidget(goals,1); entry=QLineEdit(); entry.setPlaceholderText("New Apollo goal..."); v.addWidget(entry); add=QPushButton("Add Goal"); v.addWidget(add)
        def refresh():
            goals.clear();
            if self.runtime:
                for g in self.runtime.goals(): goals.addItem(f"#{g['id']} [{g['status']}] P{g['priority']} — {g['title']}\n{g['notes']}")
        def create():
            if self.runtime and entry.text().strip(): self.runtime.add_goal(entry.text().strip()); entry.clear(); refresh()
        add.clicked.connect(create); refresh(); return page
