"""Interactive Foundry workflow status, rendered from actual project and meeting records.

Dashed arrows represent expected handoffs. Solid green arrows represent
logged handoffs / recorded team participation, never invented communication.
"""
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

ROLES = ("manager", "architect", "implementer", "tester", "reviewer", "integrator")
STATUSES = {
    "todo": ("Waiting", "#758c93"),
    "running": ("Working", "#56c6f5"),
    "review": ("Review needed", "#e5be65"),
    "accepted": ("Accepted", "#64dfb7"),
    "blocked": ("Blocked", "#f18a83"),
}


def flow_snapshot(project, meetings=(), audit=()):
    tasks = project.get("tasks", [])
    latest = meetings[0] if meetings else None
    linked = {entry["role"] for entry in latest["turns"]} if latest else set()
    status = {}
    for role in ROLES:
        relevant = [t for t in tasks if t.get("role") == role]
        states = [t["state"] for t in relevant]
        if "running" in states:
            current = "running"
        elif "blocked" in states:
            current = "blocked"
        elif "review" in states:
            current = "review"
        elif "todo" in states:
            current = "todo"
        elif "accepted" in states:
            current = "accepted"
        else:
            current = "todo"
        status[role] = {"state": current, "count": len(relevant),
                        "meeting": role in linked}
    handoffs = set()
    for event in audit:
        if event.get("kind") != "handoff":
            continue
        detail = str(event.get("detail", ""))
        for sender in ROLES:
            for recipient in ROLES:
                if detail.startswith(sender + " → " + recipient + ":"):
                    handoffs.add((sender, recipient))
    return {"roles": status, "handoffs": handoffs,
            "meeting": bool(latest), "meeting_at": latest["created_at"] if latest else None}


class ApolloTeamFlow(QWidget):
    """Paint one readable, horizontally scrollable workflow diagram."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.snapshot = flow_snapshot({"tasks": []})
        self.setMinimumSize(1030, 286)
        self.setAccessibleName("Worker coordination flow: meeting responses and recorded handoffs")
        self.setToolTip("Dashed lines: expected workflow. Solid teal: logged handoff or meeting response.")

    def update_flow(self, snapshot):
        self.snapshot = snapshot
        self.update()

    @staticmethod
    def _status(snapshot, role):
        return snapshot["roles"].get(role, {"state": "todo", "meeting": False, "count": 0})

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0e1e24"))
        layout = {
            "manager": QRectF(452, 18, 158, 70),
            "architect": QRectF(25, 168, 156, 70),
            "implementer": QRectF(221, 168, 156, 70),
            "tester": QRectF(417, 168, 156, 70),
            "reviewer": QRectF(613, 168, 156, 70),
            "integrator": QRectF(809, 168, 156, 70),
        }
        status = self.snapshot
        connected = status.get("handoffs", set())

        def arrow(start, end, actual):
            pen = QPen(QColor("#4ce1c0" if actual else "#526974"), 2.5 if actual else 1.5)
            pen.setStyle(Qt.SolidLine if actual else Qt.DashLine)
            painter.setPen(pen)
            painter.drawLine(start, end)
            painter.setBrush(QColor("#4ce1c0" if actual else "#526974"))
            painter.setPen(Qt.NoPen)
            dx = end.x() - start.x()
            dy = end.y() - start.y()
            length = max(1.0, (dx * dx + dy * dy) ** 0.5)
            ux, uy = dx / length, dy / length
            tip = end
            back = QPointF(tip.x() - 9 * ux, tip.y() - 9 * uy)
            perp = QPointF(-uy * 4, ux * 4)
            painter.drawPolygon(QPolygonF([tip, back + perp, back - perp]))

        for a, b in zip(ROLES[1:-1], ROLES[2:]):
            left, right = layout[a], layout[b]
            arrow(QPointF(left.right() + 3, left.center().y()),
                  QPointF(right.left() - 7, right.center().y()), (a, b) in connected)
        manager = layout["manager"]
        # Conversation edges have real evidence only if both roles took part in a saved meeting.
        for role in ROLES[1:]:
            worker = layout[role]
            participants = self._status(status, role)
            actual = bool(status["meeting"] and participants["meeting"])
            arrow(QPointF(manager.center().x(), manager.bottom() + 2),
                  QPointF(worker.center().x(), worker.top() - 9), actual)

        for role, rect in layout.items():
            item = self._status(status, role)
            state_label, color = STATUSES.get(item["state"], STATUSES["todo"])
            painter.setBrush(QColor("#1d3139"))
            painter.setPen(QPen(QColor(color), 2))
            painter.drawRoundedRect(rect, 13, 13)
            painter.setPen(QColor("#edf7f5"))
            painter.setFont(QFont("Segoe UI", 11, QFont.Bold))
            painter.drawText(QRectF(rect.left()+8, rect.top()+8, rect.width()-16, 22),
                             Qt.AlignCenter, role.title())
            painter.setFont(QFont("Segoe UI", 9))
            painter.setPen(QColor(color))
            count = item["count"]
            caption = state_label + (f" · {count} tasks" if count else "")
            painter.drawText(QRectF(rect.left()+6, rect.top()+36, rect.width()-12, 24),
                             Qt.AlignCenter, caption)
        painter.setPen(QColor("#91bdb6"))
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(QRectF(25, 248, 980, 23), Qt.AlignLeft,
                         "Solid teal: recorded meeting response / handoff     "
                         "Dashed grey: expected coordination (not yet completed)")
        painter.end()
