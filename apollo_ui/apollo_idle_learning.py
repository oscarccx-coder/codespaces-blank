"""Process-local Apollo interaction gate; observes no screen content or other apps."""
import threading
import time
_lock=threading.RLock()
_last_activity=time.monotonic()
_attached=False
_busy=False
_tracker=None
IDLE_SECONDS=300

def activity():
    global _last_activity
    with _lock: _last_activity=time.monotonic()

def chat_busy(value):
    global _busy
    with _lock: _busy=bool(value)
    activity()

def idle_ready(now=None):
    with _lock:
        return _attached and not _busy and (time.monotonic() if now is None else now)-_last_activity>=IDLE_SECONDS

def foreground_busy():
    with _lock: return _busy

def install_tracker():
    global _tracker,_attached
    if _tracker is not None: return
    from PySide6.QtCore import QObject,QEvent
    from PySide6.QtWidgets import QApplication
    app=QApplication.instance()
    if app is None: return
    class Tracker(QObject):
        def eventFilter(self,obj,event):
            if event.type() in (QEvent.KeyPress,QEvent.MouseButtonPress,QEvent.Wheel,QEvent.TouchBegin): activity()
            return False
    _tracker=Tracker(app); app.installEventFilter(_tracker)
    with _lock: _attached=True
    activity()
