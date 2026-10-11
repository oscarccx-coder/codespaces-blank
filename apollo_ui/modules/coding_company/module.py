"""Coding Studio: one practical screen for Apollo's staged five-role team."""
import json
from pathlib import Path
from apollo_coding_company import CodingCompany, DemoRoleModel, PHASES


class Module:
    def __init__(self, context=None):
        self.base = Path((context or {}).get("base_dir", ".")).resolve()
        self.store = CodingCompany(self.base)
        self._workers = []

    def tools(self):
        # Local model may inspect project progress but cannot autonomously
        # approve, execute or promote generated candidate files.
        return [
            {"name": "coding_projects", "description": "List local Coding Studio project states (read-only).",
             "parameters": {"type": "object", "properties": {}}},
            {"name": "coding_project_detail", "description": "Inspect Coding Studio progress and agent logs (read-only).",
             "parameters": {"type": "object", "properties": {"project_id": {"type": "integer"}}, "required": ["project_id"]}},
        ]

    def run(self, action, args):
        args = args or {}
        if action == "coding_projects":
            return {"projects": self.store.list_projects()}
        if action == "coding_project_detail":
            return self.store.detail(args["project_id"])
        raise KeyError(action)

    def self_test(self):
        assert len(self.tools()) == 2
        assert PHASES == ("architect", "developer", "tester", "reviewer", "integrator")
        return "Coding Studio read-only tool boundary passed"

    def build_ui(self, parent=None, ui_context=None):
        import threading
        from PySide6.QtCore import QObject, Signal, Qt, QUrl
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
            QPlainTextEdit, QPushButton, QListWidget, QComboBox, QSpinBox,
            QMessageBox, QSplitter
        )

        class Signals(QObject):
            changed = Signal()
            error = Signal(str)

        page = QWidget(parent)
        outer = QVBoxLayout(page)
        outer.addWidget(QLabel("Coding Studio | Manager + Architect + Developer + Tester + Reviewer + Integrator"))
        note = QLabel("Staged projects only. Syntax checks are automatic; generated programs are NOT executed. "
                      "Review candidate code before running it. Apollo core is never edited by this studio.")
        note.setWordWrap(True)
        outer.addWidget(note)

        creation = QHBoxLayout()
        title = QLineEdit()
        title.setPlaceholderText("Project name")
        creation.addWidget(title, 1)
        demo = QComboBox()
        demo.addItems(["Local Ollama", "Safe demo (no GPU)"])
        creation.addWidget(demo)
        max_turns = QSpinBox()
        max_turns.setRange(5, 40)
        max_turns.setValue(20)
        max_turns.setToolTip("Maximum role turns for this project")
        creation.addWidget(QLabel("Turn limit"))
        creation.addWidget(max_turns)
        outer.addLayout(creation)

        request = QPlainTextEdit()
        request.setPlaceholderText("Describe what to build and how you will know it works...")
        request.setMaximumHeight(100)
        outer.addWidget(request)
        new_btn = QPushButton("Create Project")
        outer.addWidget(new_btn)

        split = QSplitter(Qt.Orientation.Horizontal)
        projects = QListWidget()
        split.addWidget(projects)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        status = QLabel("Select a project")
        status.setWordWrap(True)
        right_layout.addWidget(status)
        buttons = QHBoxLayout()
        advance = QPushButton("Next Role")
        full = QPushButton("Run Team (bounded)")
        stop = QPushButton("Stop")
        resume = QPushButton("Resume")
        folder = QPushButton("Open Candidate")
        for b in (advance, full, stop, resume, folder):
            buttons.addWidget(b)
        right_layout.addLayout(buttons)
        log = QTextEdit()
        log.setReadOnly(True)
        right_layout.addWidget(log, 1)
        preview_row = QHBoxLayout()
        file_select = QComboBox()
        preview_row.addWidget(QLabel("Candidate file:"))
        preview_row.addWidget(file_select, 1)
        right_layout.addLayout(preview_row)
        source = QPlainTextEdit()
        source.setReadOnly(True)
        source.setMaximumHeight(180)
        right_layout.addWidget(source)
        feedback = QPlainTextEdit()
        feedback.setPlaceholderText("Bug notes / changes requested, including test results...")
        feedback.setMaximumHeight(75)
        right_layout.addWidget(feedback)
        review_row = QHBoxLayout()
        approve = QPushButton("Approve Candidate")
        changes = QPushButton("Request Changes")
        reject = QPushButton("Reject")
        for b in (approve, changes, reject):
            review_row.addWidget(b)
        right_layout.addLayout(review_row)
        split.addWidget(right)
        split.setStretchFactor(1, 3)
        outer.addWidget(split, 1)

        signals = Signals(page)
        active = {"project": None, "busy": False, "files": {}, "mode": "local"}

        def selected_id():
            item = projects.currentItem()
            return item.data(Qt.ItemDataRole.UserRole) if item else None

        def refresh(select=None):
            active["project"] = select or selected_id()
            projects.blockSignals(True)
            projects.clear()
            for p in self.store.list_projects():
                item_text = "#{} [{}] {} (next: {})".format(p["id"], p["state"], p["title"], p["phase"])
                projects.addItem(item_text)
                item = projects.item(projects.count() - 1)
                item.setData(Qt.ItemDataRole.UserRole, p["id"])
                if p["id"] == active["project"]:
                    projects.setCurrentItem(item)
            projects.blockSignals(False)
            pid = active["project"]
            if pid is None:
                return
            try:
                data = self.store.detail(pid)
                p = data["project"]
                status.setText("Project #{} | {} | {} | iteration {} | turns {}/{} | retries {}/{}{}"
                               .format(pid, p["state"], p["phase"], p["iteration"], p["turns"],
                                       p["max_turns"], p["attempts"], p["max_reworks"],
                                       "\n" + p["last_error"] if p["last_error"] else ""))
                lines = []
                for turn in data["turns"][-25:]:
                    lines.append("{} | {} | {}\n{}".format(
                        turn["created_at"], turn["role"].title(), turn["outcome"],
                        turn["response"][:1800]))
                lines.append("\nVerification: STATIC SYNTAX ONLY; no runtime tests have been executed.")
                log.setPlainText("\n\n".join(lines))
                candidate = self.store._files(pid)
                active["files"] = candidate
                old_file = file_select.currentText()
                file_select.blockSignals(True)
                file_select.clear()
                file_select.addItems(list(candidate))
                if old_file in candidate:
                    file_select.setCurrentText(old_file)
                file_select.blockSignals(False)
                show_file()
                for b in (approve, changes, reject):
                    b.setEnabled(p["state"] == "awaiting_user" and not active["busy"])
                advance.setEnabled(p["state"] == "ready" and not active["busy"])
                full.setEnabled(p["state"] == "ready" and not active["busy"])
                resume.setEnabled(p["state"] in ("paused", "failed") and not active["busy"])
                stop.setEnabled(p["state"] in ("running", "ready") or active["busy"])
            except Exception as exc:
                status.setText(str(exc))

        def show_file():
            source.setPlainText(active["files"].get(file_select.currentText(), ""))

        def create():
            try:
                p = self.store.create(title.text(), request.toPlainText(), max_turns.value(),
                                      mode='demo' if demo.currentIndex() == 1 else 'local')
                title.clear()
                request.clear()
                refresh(p["id"])
            except Exception as exc:
                QMessageBox.warning(page, "Coding Studio", str(exc))

        def invoke(full_run=False):
            pid = selected_id()
            if pid is None or active["busy"]:
                return
            active["busy"] = True
            mode = self.store.detail(pid)['project']['mode']
            # This worker emits signals; Qt widgets are only changed on UI thread.
            def work():
                try:
                    model = DemoRoleModel() if mode == "demo" else None
                    for _ in range(40 if full_run else 1):
                        result = self.store.step(pid, model)
                        signals.changed.emit()
                        if result["project"]["state"] != "ready":
                            break
                except Exception as exc:
                    signals.error.emit(str(exc))
                finally:
                    active["busy"] = False
                    signals.changed.emit()
            thread = threading.Thread(target=work, daemon=True)
            self._workers.append(thread)
            thread.start()
            refresh(pid)

        def request_stop():
            pid = selected_id()
            if pid is not None:
                self.store.pause(pid)
                refresh(pid)

        def do_resume():
            pid = selected_id()
            if pid:
                try:
                    self.store.resume(pid)
                    refresh(pid)
                except Exception as exc:
                    QMessageBox.warning(page, "Resume", str(exc))

        def do_review(decision):
            pid = selected_id()
            if pid is None:
                return
            if decision == "approve":
                if QMessageBox.question(page, "Approve staged candidate",
                        "Mark this candidate reviewed? This does not install or run it."
                        ) != QMessageBox.StandardButton.Yes:
                    return
            try:
                self.store.feedback(pid, decision, feedback.toPlainText())
                feedback.clear()
                refresh(pid)
            except Exception as exc:
                QMessageBox.warning(page, "Review", str(exc))

        def open_folder():
            pid = selected_id()
            if pid is not None:
                path = Path(self.store.detail(pid)["candidate"])
                path.mkdir(parents=True, exist_ok=True)
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

        def report_error(message):
            QMessageBox.warning(page, "Coding Studio", message)
            refresh()

        signals.changed.connect(refresh)
        signals.error.connect(report_error)
        new_btn.clicked.connect(create)
        projects.currentItemChanged.connect(lambda *_: refresh())
        advance.clicked.connect(lambda: invoke(False))
        full.clicked.connect(lambda: invoke(True))
        stop.clicked.connect(request_stop)
        resume.clicked.connect(do_resume)
        folder.clicked.connect(open_folder)
        approve.clicked.connect(lambda: do_review("approve"))
        changes.clicked.connect(lambda: do_review("changes"))
        reject.clicked.connect(lambda: do_review("reject"))
        file_select.currentTextChanged.connect(show_file)
        refresh()
        return page
