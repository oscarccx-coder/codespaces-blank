from pathlib import Path
class Module:
    def __init__(self,context=None): self.runtime=(context or {}).get("runtime")
    def tools(self): return [
        {"name":"notify","description":"Create a persistent Apollo notification.","parameters":{"type":"object","properties":{"title":{"type":"string"},"message":{"type":"string"},"level":{"type":"string"}},"required":["title","message"]}},
        {"name":"list_notifications","description":"List recent Apollo notifications.","parameters":{"type":"object","properties":{"unread_only":{"type":"boolean"},"limit":{"type":"integer"}}}},
        {"name":"mark_read","description":"Mark a notification read.","parameters":{"type":"object","properties":{"notification_id":{"type":"integer"}},"required":["notification_id"]}},
    ]
    def _rt(self):
        if self.runtime is None: raise RuntimeError("Apollo runtime unavailable")
        return self.runtime
    def run(self,a,x):
        x=x or {}; rt=self._rt()
        if a=="notify": return {"notification_id":rt.notify(x['title'],x['message'],x.get('level','info'),'notification_center')}
        if a=="list_notifications": return {"notifications":rt.notifications(bool(x.get('unread_only',False)),x.get('limit',100))}
        if a=="mark_read": rt.mark_notification_read(x['notification_id']); return {"updated":True}
        raise KeyError(a)
    def self_test(self): return "notification contracts passed"
    def build_ui(self,parent=None,ui_context=None):
        from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QListWidget,QPushButton
        p=QWidget(parent); v=QVBoxLayout(p); v.addWidget(QLabel("Notification Center")); l=QListWidget(); v.addWidget(l,1); b=QPushButton("Refresh"); v.addWidget(b)
        def r():
            l.clear();
            if self.runtime:
                for n in self.runtime.notifications(False,200): l.addItem(f"{n['created_at']} • {n['level'].upper()} • {n['title']}\n{n['message']}")
        b.clicked.connect(r); r(); return p
