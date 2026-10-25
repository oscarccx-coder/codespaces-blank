"""JARVIS Director UI and read-only AI tools. Missions start only via owner controls."""
from __future__ import annotations

from pathlib import Path

from apollo_jarvis_director import DEFAULT_BRIEF, Director, ROLES


class Module:
    def __init__(self, context=None):
        self.context = context or {}
        self.base = Path(self.context.get("base_dir") or ".").resolve()
        self.validation = bool(self.context.get("validation"))
        self.director = Director(self.base, validation=self.validation)

    def tools(self):
        return [
            {"name": "jarvis_mission_status",
             "description": "Read current owner-approved local JARVIS missions, budgets and states. No execution or publication.",
             "parameters": {"type": "object", "properties": {}}},
            {"name": "jarvis_mission_detail",
             "description": "Inspect a mission's locally saved specialist drafts and unverified candidate paths. Does not run code.",
             "parameters": {"type": "object", "properties": {"mission_id": {"type": "integer"}},
                            "required": ["mission_id"]}},
            {"name": "jarvis_roles",
             "description": "Show specialist agent roles and safe autonomy contracts; only the owner can start or control an agent mission.",
             "parameters": {"type": "object", "properties": {}}},
        ]

    def run(self, action, arguments):
        arguments = arguments or {}
        if action == "jarvis_mission_status":
            return {"missions": self.director.store.list(),
                    "note": "Only owner-approved local Ollama drafting; no cloud or deployments."}
        if action == "jarvis_mission_detail":
            return self.director.store.detail(arguments["mission_id"])
        if action == "jarvis_roles":
            return {"roles": ROLES, "mode": "local Ollama via existing Foundry workers",
                    "limits": "Maximum 8 specialists in a planning round, at most 60 model calls per mission, no production writes.",
                    "approval": "Owner-only mission start, pause, resume and stop. Generated code remains a static, untested candidate."}
        raise KeyError(action)

    def close(self):
        self.director.close()

    def self_test(self):
        assert len(ROLES) >= 4
        assert not any(x["name"] in {"jarvis_start", "jarvis_resume", "jarvis_deploy",
                                     "jarvis_run_code", "jarvis_install"} for x in self.tools())
        assert not self.director.store.list()
        return "JARVIS Director owner-only controls and local draft-only agent protocol verified."

    def build_ui(self, parent=None, ui_context=None):
        from PySide6.QtCore import Qt, QTimer
        from PySide6.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit,
            QLineEdit, QPushButton, QListWidget, QListWidgetItem, QComboBox,
            QSpinBox, QMessageBox, QTabWidget
        )

        page = QWidget(parent)
        outer = QVBoxLayout(page)
        heading = QLabel("JARVIS Director | Apollo's local engineering team")
        heading.setStyleSheet("font-size:22px;font-weight:800;")
        outer.addWidget(heading)
        intro = QLabel(
            "An autonomous, local-first specialist team. Apollo can plan tasks, draft code, "
            "request test plans and critique candidates using Ollama, even when ChatGPT "
            "is unavailable. Generated files are staged only in Workspace. "
            "No automatic shell execution, Git merge, updater installation or release.")
        intro.setWordWrap(True)
        outer.addWidget(intro)
        tabs = QTabWidget()
        outer.addWidget(tabs, 1)

        plan_page = QWidget()
        plan_layout = QVBoxLayout(plan_page)
        title = QLineEdit("Apollo reliability and self-improvement")
        objective = QPlainTextEdit()
        objective.setPlainText(DEFAULT_BRIEF)
        objective.setMaximumHeight(160)
        plan_layout.addWidget(QLabel("Mission title"))
        plan_layout.addWidget(title)
        plan_layout.addWidget(QLabel("Engineering objective (kept local)"))
        plan_layout.addWidget(objective)
        opts = QHBoxLayout()
        opts.addWidget(QLabel("Mission mode"))
        mode = QComboBox()
        mode.addItem("One bounded improvement cycle", "fixed")
        mode.addItem("Continue until stopped or budget exhausted", "until_stop")
        opts.addWidget(mode)
        opts.addWidget(QLabel("Maximum model calls"))
        calls = QSpinBox()
        calls.setRange(2, 60)
        calls.setValue(16)
        opts.addWidget(calls)
        opts.addWidget(QLabel("Seconds between calls"))
        interval = QSpinBox()
        interval.setRange(30, 3600)
        interval.setValue(60)
        opts.addWidget(interval)
        plan_layout.addLayout(opts)
        start = QPushButton("Authorise and start LOCAL engineering mission")
        plan_layout.addWidget(start)
        policy = QLabel(
            "Each model call consumes one budget unit, including a failed call. "
            "The team may generate candidate source files but never runs them. "
            "A repeated failure blocks the mission for review. "
            "Pausing and stopping remain available during work.")
        policy.setWordWrap(True)
        plan_layout.addWidget(policy)
        plan_layout.addStretch(1)
        tabs.addTab(plan_page, "Start a mission")

        work_page = QWidget()
        work_layout = QVBoxLayout(work_page)
        mission_list = QListWidget()
        mission_list.setMaximumHeight(140)
        work_layout.addWidget(QLabel("Saved engineering missions"))
        work_layout.addWidget(mission_list)
        buttons = QHBoxLayout()
        pause = QPushButton("Pause")
        resume = QPushButton("Resume")
        stop = QPushButton("Stop")
        run_next = QPushButton("Request next step")
        refresh = QPushButton("Refresh")
        for b in (pause, resume, stop, run_next, refresh):
            buttons.addWidget(b)
        work_layout.addLayout(buttons)
        status = QLabel()
        status.setWordWrap(True)
        work_layout.addWidget(status)
        results = QPlainTextEdit()
        results.setReadOnly(True)
        work_layout.addWidget(results, 1)
        tabs.addTab(work_page, "Mission console")

        def selected_id():
            item = mission_list.currentItem()
            return int(item.data(Qt.UserRole)) if item is not None else None

        def refresh_view():
            old = selected_id()
            mission_list.clear()
            for mission in self.director.store.list():
                caption = "#{id} {title} | {state} | {calls_used}/{max_calls} calls".format(**mission)
                item = QListWidgetItem(caption)
                item.setData(Qt.UserRole, mission["id"])
                mission_list.addItem(item)
                if mission["id"] == old:
                    mission_list.setCurrentItem(item)
            if mission_list.currentItem() is None and mission_list.count():
                mission_list.setCurrentRow(0)
            mid = selected_id()
            if mid is None:
                status.setText("No missions created.")
                results.setPlainText("")
                return
            detail = self.director.store.detail(mid)
            m = detail["mission"]
            status.setText("Mission #{id} | {state} | {calls_used}/{max_calls} Ollama calls | Round {round} | Model: {model} | {last_error}".format(**m))
            lines = [
                "OBJECTIVE (local only): " + m["objective"],
                "",
                "SPECIALISTS / RESULTS (drafts, not executed):"
            ]
            for agent in detail["agents"]:
                lines.extend(["", "%s / %s / %s / attempts %s" % (
                    agent["role"].upper(), agent["title"], agent["state"],
                    agent["attempts"]),
                    agent["result_preview"][:1300] or "Not yet drafted",
                    ("Candidate files: " + agent["candidate_path"]) if agent["candidate_path"] else ""])
            lines.extend(["", "RECENT EVENTS:"])
            for event in detail["events"][:18]:
                lines.append("%s %s: %s" % (event["created"], event["kind"], event["detail"]))
            results.setPlainText("\n".join(lines)[:35000])

        def begin():
            answer = QMessageBox.question(
                page, "Authorise local JARVIS agents?",
                "Start this specific mission using only your configured local Ollama model? "
                "It can generate isolated, untested source candidates and use up to %s model calls. "
                "No shell commands, code application, installs, external API billing or release actions."
                % calls.value(), QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
            try:
                created = self.director.owner_begin(
                    title.text(), objective.toPlainText(),
                    mode=mode.currentData(), max_calls=calls.value(),
                    interval_seconds=interval.value())
            except (OSError, RuntimeError, ValueError) as exc:
                QMessageBox.warning(page, "Could not start mission", str(exc))
                return
            refresh_view()
            for index in range(mission_list.count()):
                item = mission_list.item(index)
                if item.data(Qt.UserRole) == created["id"]:
                    mission_list.setCurrentItem(item)
                    break
            tabs.setCurrentWidget(work_page)

        def control(action):
            mid = selected_id()
            if mid is None:
                return
            try:
                self.director.owner_control(mid, action)
            except (OSError, ValueError) as exc:
                QMessageBox.warning(page, "Mission control", str(exc))
            refresh_view()

        def step_now():
            mid = selected_id()
            if mid is None:
                return
            try:
                self.director.request_next(mid)
            except (OSError, RuntimeError, ValueError, PermissionError) as exc:
                QMessageBox.warning(page, "Unable to queue next step", str(exc))
            refresh_view()

        start.clicked.connect(begin)
        pause.clicked.connect(lambda: control("pause"))
        resume.clicked.connect(lambda: control("resume"))
        stop.clicked.connect(lambda: control("stop"))
        run_next.clicked.connect(step_now)
        refresh.clicked.connect(refresh_view)
        mission_list.currentItemChanged.connect(lambda _current, _previous: refresh_view())
        # Avoid list signals recursively rebuilding the list on every refresh.
        mission_list.currentItemChanged.disconnect()
        mission_list.currentItemChanged.connect(lambda current, previous:
                                                render_selection(current))

        def render_selection(current):
            if current is None:
                return
            detail = self.director.store.detail(int(current.data(Qt.UserRole)))
            m = detail["mission"]
            status.setText("Mission #{id} | {state} | {calls_used}/{max_calls} calls | Round {round} | Model {model}".format(**m))
            rows = ["OBJECTIVE: " + m["objective"], "", "SPECIALISTS (drafts, untested):"]
            for agent in detail["agents"]:
                rows += ["%s: %s [%s; attempts %s]" % (
                    agent["role"], agent["title"], agent["state"], agent["attempts"]),
                         agent["result_preview"][:1300]]
                if agent["candidate_path"]:
                    rows.append("Staged: " + agent["candidate_path"])
            rows += ["", "EVENTS:"]
            rows += ["%s: %s" % (event["kind"], event["detail"])
                     for event in detail["events"][:20]]
            results.setPlainText("\n\n".join(rows)[:35000])
        refresher = QTimer(page)
        refresher.setInterval(3500)
        refresher.timeout.connect(refresh_view)
        refresher.start()
        refresh_view()
        return page
