"""Human-controlled Apollo Foundry frontend for Phase 1 coding.

Workers never execute drafts. The owner can explicitly launch a reviewed app
in a separate, UNSANDBOXED local process after static checks and warnings.
"""
import json
import sys
from pathlib import Path

from apollo_project_studio import StudioStore
from apollo_foundry_artifacts import save_bundle
from apollo_foundry_meetings import hold_meeting
from apollo_project_workers import (
    draft_for_task, model_from_config, propose_subtasks, validate_subtask_plan
)
from project_studio_view_model import project_metrics, task_actions, issue_actions


class Module:
    def __init__(self, context=None):
        context = context or {}
        self.base = Path(context.get("base_dir", ".")).resolve()
        self.store = StudioStore(self.base, memory=bool(context.get("validation")))

    def tools(self):
        # AI can read projects and queue a non-executing change request only.
        # Drafting, approving, closing issues, and all code changes remain UI-controlled.
        integer = {"type": "integer"}
        return [
            {"name": "list_app_projects", "description": "Read user-created app development projects.",
             "parameters": {"type": "object", "properties": {}}},
            {"name": "app_project_status", "description": "Read tasks, subtasks and issues for one project.",
             "parameters": {"type": "object", "properties": {"project_id": integer}, "required": ["project_id"]}},
            {"name": "queue_app_change",
             "description": "Queue a requested project change as a reviewable task. Requires exact project ID. Never edits or runs code.",
             "parameters": {"type": "object", "properties": {
                 "project_id": integer,
                 "request": {"type": "string"},
                 "task_id": integer,
             }, "required": ["project_id", "request"]}},
        ]

    def run(self, action, arguments):
        args = arguments or {}
        if action == "list_app_projects":
            return {"projects": self.store.list_projects()}
        if action == "app_project_status":
            return self.store.details(args["project_id"])
        if action == "queue_app_change":
            return self.store.request_change(
                args["project_id"], args["request"], args.get("task_id")
            )
        raise KeyError(action)

    def self_test(self):
        if self.store.db_path == ":memory:":
            data = self.store.add_project("Check", "Synthetic, local validation")
            assert len(data["tasks"]) == 5
            assert all(t["state"] == "todo" for t in data["tasks"])
        return "Foundry tracks project drafts and queued changes. No auto-execution or approvals."

    def close(self):
        self.store.close()

    def build_ui(self, parent=None, ui_context=None):
        from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, QTimer, QProcess
        from apollo_foundry_diagram import ApolloTeamFlow, flow_snapshot
        from PySide6.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGridLayout,
            QLineEdit, QProgressBar, QGroupBox,
            QListWidget, QListWidgetItem, QSplitter, QTabWidget,
            QTreeWidget, QTreeWidgetItem, QPlainTextEdit, QMessageBox,
            QInputDialog, QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox, QScrollArea,
        )

        class WorkerSignal(QObject):
            finished = Signal(int, str, str)
            update = Signal(str)

        class DraftJob(QRunnable):
            def __init__(self, item, state, model, signals, repair="", research=False):
                super().__init__()
                self.item, self.state, self.model, self.signals = item, state, model, signals
                self.repair, self.research = repair, research

            def run(self):
                try:
                    context = self.repair
                    if self.research:
                        from apollo_foundry_research import collect_research
                        self.signals.update.emit("Research: Looking up public documentation after repeated failures...")
                        try:
                            sources = collect_research(self.repair)
                            self.signals.update.emit(
                                "Research: " + str(sources["query"]) + "\n" +
                                "\n".join(source["url"] for source in sources["sources"]))
                            context += "\nUntrusted public documentation search snippets (check accuracy):\n"
                            context += json.dumps(sources["sources"])[:1700]
                        except Exception as search_error:
                            self.signals.update.emit("Research unavailable: " + str(search_error)[:180])
                    text = draft_for_task(self.state, self.item, self.model, repair_context=context)
                    self.signals.finished.emit(self.item, text, "")
                except Exception as error:
                    self.signals.finished.emit(self.item, "", f"{type(error).__name__}: {error}")

        class SandboxJob(QRunnable):
            def __init__(self, project_id, kind, store, signals):
                super().__init__()
                self.project_id = project_id
                self.kind = kind
                self.store = store
                self.signals = signals

            def run(self):
                try:
                    report = self.store.run_sandbox_tests(self.project_id, self.kind)
                    self.signals.finished.emit(self.project_id, json.dumps(report), "")
                except Exception as error:
                    self.signals.finished.emit(
                        self.project_id, "", f"{type(error).__name__}: {error}"
                    )

        class PlanJob(QRunnable):
            def __init__(self, item, state, model, signals):
                super().__init__()
                self.item = item
                self.state = state
                self.model = model
                self.signals = signals

            def run(self):
                try:
                    tasks = propose_subtasks(self.state, self.item, self.model)
                    proposal = json.dumps({"tasks": tasks}, indent=2)
                    self.signals.finished.emit(self.item, proposal, "")
                except Exception as error:
                    self.signals.finished.emit(self.item, "", f"{type(error).__name__}: {error}")

        class MeetingSignals(QObject):
            finished = Signal(int, object, str)
            spoke = Signal(int, str, str)

        class MeetingJob(QRunnable):
            def __init__(self, pid, state, model, topic, signals):
                super().__init__()
                self.pid, self.state, self.model, self.topic, self.signals = (
                    pid, state, model, topic, signals)

            def run(self):
                try:
                    report = hold_meeting(
                        self.state, self.model, topic=self.topic,
                        on_message=lambda role, message:
                            self.signals.spoke.emit(self.pid, role, message))
                    self.signals.finished.emit(self.pid, report, "")
                except Exception as exc:
                    self.signals.finished.emit(
                        self.pid, None, f"{type(exc).__name__}: {exc}")

        page = QWidget(parent)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)
        heading = QLabel("Apollo Foundry  |  Project Studio")
        heading.setStyleSheet("font-size:24px;font-weight:700;")
        page.setObjectName("projectStudioPage")
        outer.addWidget(heading)
        summary = QLabel(
            "Plan apps, assign specialists, request changes and check UI-to-code links. "
            "Static checks and optional isolated Docker tests. No generated code executes, installs, or publishes without your approval."
        )
        summary.setWordWrap(True)
        outer.addWidget(summary)

        split = QSplitter(Qt.Horizontal)
        outer.addWidget(split, 1)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Your app projects"))
        project_search = QLineEdit()
        project_search.setPlaceholderText("Find a project...")
        project_search.setClearButtonEnabled(True)
        project_search.setAccessibleName("Search app projects")
        left_layout.addWidget(project_search)
        projects = QListWidget()
        projects.setAccessibleName("Saved app projects")
        projects.setToolTip("Select a project to view tasks, issues and activity.")
        left_layout.addWidget(projects, 1)
        new_project = QPushButton("+ New App Project")
        refresh_btn = QPushButton("Refresh")
        left_layout.addWidget(new_project)
        left_layout.addWidget(refresh_btn)
        left.setMinimumWidth(190)
        split.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        project_heading = QLabel("Select or create a project")
        project_heading.setStyleSheet("font-size:17px;font-weight:600;")
        right_layout.addWidget(project_heading)
        path_label = QLabel("Projects are saved in workspace/app_development/")
        path_label.setWordWrap(True)
        right_layout.addWidget(path_label)
        overview = QLabel("No project selected. Create one to begin.")
        overview.setWordWrap(True)
        overview.setStyleSheet("color:#9fcfc6; font-weight:600; padding:4px 0;")
        right_layout.addWidget(overview)
        completion = QProgressBar()
        completion.setRange(0, 100)
        completion.setValue(0)
        completion.setTextVisible(True)
        completion.setFormat("%p% tasks reviewed")
        completion.setAccessibleName("Project task completion")
        right_layout.addWidget(completion)
        # Simple entry point: describe a project and let the manager plan it.
        quick_intro = QLabel("What should Apollo build or change?")
        quick_intro.setStyleSheet("font-size:15px;font-weight:600;")
        right_layout.addWidget(quick_intro)
        quick_request = QPlainTextEdit()
        quick_request.setPlaceholderText(
            "Example: Build a calculus calculator with a simple UI, tests and error handling.")
        quick_request.setMaximumHeight(92)
        right_layout.addWidget(quick_request)
        quick_actions = QHBoxLayout()
        quick_start = QPushButton("Plan My Project")
        quick_start.setObjectName("primaryAction")
        quick_actions.addWidget(quick_start)
        research_toggle = QCheckBox("Research public docs after 2 failed attempts")
        research_toggle.setChecked(True)
        research_toggle.setToolTip("Sends only a generic technical query to public search, never your project text.")
        quick_actions.addWidget(QLabel("Select a project to add a change, or create a new one."))
        right_layout.addLayout(quick_actions)
        right_layout.addWidget(research_toggle)
        session_controls = QHBoxLayout()
        continuous_start = QPushButton("Start Continuous Build")
        continuous_start.setObjectName("foundryContinuousStart")
        continuous_pause = QPushButton("Pause")
        continuous_pause.setObjectName("foundryContinuousPause")
        continuous_resume = QPushButton("Resume")
        continuous_resume.setObjectName("foundryContinuousResume")
        continuous_stop = QPushButton("Stop")
        continuous_stop.setObjectName("foundryContinuousStop")
        for control in (continuous_start, continuous_pause, continuous_resume, continuous_stop):
            session_controls.addWidget(control)
        right_layout.addLayout(session_controls)
        session_status = QLabel("Continuous mode: off. Docker tests require one explicit session approval.")
        session_status.setObjectName("foundryContinuousStatus")
        session_status.setWordWrap(True)
        right_layout.addWidget(session_status)
        worker_feed = QPlainTextEdit()
        worker_feed.setReadOnly(True)
        worker_feed.setMaximumHeight(230)
        worker_feed.setPlaceholderText("Worker activity and decisions will appear here.")
        right_layout.addWidget(QLabel("Worker activity"))
        right_layout.addWidget(worker_feed)
        def feed(message):
            worker_feed.appendPlainText(str(message))
        tabs = QTabWidget()
        right_layout.addWidget(tabs, 1)
        split.addWidget(right)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 4)

        # This is a real project snapshot, not a decorative worker conversation.
        flow_tab = QWidget()
        flow_layout = QVBoxLayout(flow_tab)
        flow_header = QHBoxLayout()
        team_meeting_btn = QPushButton("Hold Team Meeting")
        team_meeting_btn.setObjectName("foundryTeamMeeting")
        team_meeting_btn.setToolTip(
            "Ask each specialist to discuss this project, then save the manager's decisions.")
        flow_header.addWidget(team_meeting_btn)
        flow_header.addStretch()
        flow_layout.addLayout(flow_header)
        meeting_status = QLabel("No team meeting recorded for this project.")
        meeting_status.setWordWrap(True)
        flow_layout.addWidget(meeting_status)
        diagram_scroll = QScrollArea()
        diagram_scroll.setWidgetResizable(False)
        diagram_scroll.setFrameShape(QScrollArea.NoFrame)
        diagram_scroll.setMinimumHeight(305)
        team_flow = ApolloTeamFlow()
        diagram_scroll.setWidget(team_flow)
        flow_layout.addWidget(diagram_scroll)
        flow_layout.addWidget(QLabel("Meeting transcript and manager decisions"))
        team_transcript = QPlainTextEdit()
        team_transcript.setReadOnly(True)
        team_transcript.setAccessibleName("Saved worker meeting transcripts and decisions")
        team_transcript.setPlaceholderText("Choose a project, then hold a team meeting.")
        flow_layout.addWidget(team_transcript, 1)
        tabs.addTab(flow_tab, "Workflow & Meetings")

        tasks_tab = QWidget()
        tasks_layout = QVBoxLayout(tasks_tab)
        task_buttons = QHBoxLayout()
        task_buttons.setSpacing(8)
        add_subtask = QPushButton("+ Subtask")
        change_request = QPushButton("Request a Change")
        plan_subtasks = QPushButton("Plan with AI")
        start_worker = QPushButton("Run Selected Worker")
        accept_task = QPushButton("Approve Draft")
        rework_task = QPushButton("Request Changes")
        retry_task = QPushButton("Retry / Reopen")
        for button in (plan_subtasks, start_worker, accept_task, change_request):
            task_buttons.addWidget(button)
        tasks_layout.addLayout(task_buttons)
        advanced_toggle = QPushButton("Show advanced task options")
        advanced_toggle.setCheckable(True)
        tasks_layout.addWidget(advanced_toggle)
        advanced_tasks = QGroupBox("Advanced task controls")
        advanced_tasks.setVisible(False)
        advanced_toggle.toggled.connect(advanced_tasks.setVisible)
        advanced_layout = QHBoxLayout(advanced_tasks)
        for button in (add_subtask, rework_task, retry_task):
            advanced_layout.addWidget(button)
        tasks_layout.addWidget(advanced_tasks)
        task_tree = QTreeWidget()
        task_tree.setHeaderLabels(["Task", "Worker", "Status", "Iteration"])
        task_tree.setColumnWidth(0, 270)
        task_tree.setAccessibleName("Project worker tasks and subtasks")
        task_tree.setAlternatingRowColors(False)
        task_tree.setStyleSheet("QTreeWidget { background:#142229; color:#e7eef3; alternate-background-color:#142229; } QTreeWidget::item:selected { background:#23655c; color:#ffffff; }")
        tasks_layout.addWidget(task_tree, 2)
        result_text = QPlainTextEdit()
        result_text.setReadOnly(True)
        result_text.setAccessibleName("Selected task instructions and draft")
        result_text.setPlaceholderText("Select a task to see its instructions, draft and review feedback.")
        tasks_layout.addWidget(result_text, 1)
        tabs.addTab(tasks_tab, "1. Build")

        bugs_tab = QWidget()
        bugs_layout = QVBoxLayout(bugs_tab)
        bug_buttons = QGridLayout()
        report_bug = QPushButton("+ Report Issue")
        assign_fix = QPushButton("Create Fix Task")
        resolve_bug = QPushButton("Close Reviewed Issue")
        for index, button in enumerate((report_bug, assign_fix, resolve_bug)):
            bug_buttons.addWidget(button, index // 2, index % 2)
        bugs_layout.addLayout(bug_buttons)
        issue_table = QTableWidget(0, 4)
        issue_table.setHorizontalHeaderLabels(["ID", "Issue", "Status", "Fix task"])
        issue_table.setSelectionBehavior(QTableWidget.SelectRows)
        issue_table.setAlternatingRowColors(False)
        issue_table.setStyleSheet("QTableWidget { background:#142229; color:#e7eef3; gridline-color:#34434a; } QTableWidget::item:selected { background:#23655c; color:#ffffff; }")
        issue_table.setAccessibleName("Reported project bugs and fix tasks")
        issue_table.setEditTriggers(QTableWidget.NoEditTriggers)
        issue_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        bugs_layout.addWidget(issue_table)
        tabs.addTab(bugs_tab, "3. Fix Issues")

        checks_tab = QWidget()
        checks_layout = QVBoxLayout(checks_tab)
        checks_intro = QLabel("Static checks: Python syntax, UI buttons, signals, handlers and backend links. "
                              "These checks DO NOT launch generated software. A real GUI test remains required.")
        checks_intro.setWordWrap(True)
        checks_layout.addWidget(checks_intro)
        checks_buttons = QHBoxLayout()
        starter_btn = QPushButton("Create Starter UI")
        run_checks_btn = QPushButton("Run UI & Code Checks")
        run_checks_btn.setObjectName("primaryAction")
        fix_checks_btn = QPushButton("Request Fix for Failures")
        show_folder_btn = QPushButton("Open Project Folder")
        for button in (starter_btn, run_checks_btn, fix_checks_btn, show_folder_btn):
            checks_buttons.addWidget(button)
        checks_layout.addLayout(checks_buttons)
        checks_status = QLabel("No checks run. Add code and foundry.json, then run checks.")
        checks_status.setWordWrap(True)
        checks_layout.addWidget(checks_status)
        checks_report = QPlainTextEdit()
        checks_report.setReadOnly(True)
        checks_report.setAccessibleName("Stored static project check report")
        checks_layout.addWidget(checks_report, 1)
        tabs.addTab(checks_tab, "2. Check Code")

        sandbox_tab = QWidget()
        sandbox_layout = QVBoxLayout(sandbox_tab)
        sandbox_intro = QLabel(
            "Run generated project code only inside an isolated Docker container. "
            "No network, read-only app snapshot, bounded memory/CPU, no direct host Python fallback. "
            "Requires Docker Desktop and preinstalled trusted images."
        )
        sandbox_intro.setWordWrap(True)
        sandbox_layout.addWidget(sandbox_intro)
        sandbox_buttons = QHBoxLayout()
        sandbox_unit = QPushButton("Run Tests in Sandbox")
        sandbox_gui = QPushButton("GUI Launch Smoke Test")
        sandbox_fix = QPushButton("Send Failures to Worker")
        for button in (sandbox_unit, sandbox_gui, sandbox_fix):
            sandbox_buttons.addWidget(button)
        sandbox_layout.addLayout(sandbox_buttons)
        sandbox_status = QLabel("No sandbox run recorded for this project.")
        sandbox_status.setWordWrap(True)
        sandbox_layout.addWidget(sandbox_status)
        sandbox_report = QPlainTextEdit()
        sandbox_report.setReadOnly(True)
        sandbox_report.setAccessibleName("Isolated Foundry runtime test report")
        sandbox_layout.addWidget(sandbox_report, 1)

        # Explicit, separate host preview: NEVER part of autonomous worker flow.
        # Docker tests above remain the preferred untrusted-code testing path.
        preview_box = QGroupBox("Interactive Local Preview (Trusted Code Only)")
        preview_layout = QVBoxLayout(preview_box)
        preview_warning = QLabel(
            "WARNING: Launching a generated app on Windows is NOT sandboxed. "
            "The program can access your files and network with your user permissions. "
            "Review its source and run Docker tests first. Nothing starts automatically."
        )
        preview_warning.setWordWrap(True)
        preview_layout.addWidget(preview_warning)
        preview_controls = QHBoxLayout()
        preview_launch = QPushButton("Launch App Window (Local)")
        preview_launch.setObjectName("foundryLocalPreviewLaunch")
        preview_stop = QPushButton("Stop App")
        preview_stop.setObjectName("foundryLocalPreviewStop")
        preview_stop.setEnabled(False)
        preview_controls.addWidget(preview_launch)
        preview_controls.addWidget(preview_stop)
        preview_layout.addLayout(preview_controls)
        preview_status = QLabel("No app preview running.")
        preview_status.setWordWrap(True)
        preview_layout.addWidget(preview_status)
        preview_output = QPlainTextEdit()
        preview_output.setObjectName("foundryLocalPreviewOutput")
        preview_output.setReadOnly(True)
        preview_output.setMaximumHeight(140)
        preview_output.setAccessibleName("Generated app preview output")
        preview_layout.addWidget(preview_output)
        sandbox_layout.addWidget(preview_box)
        preview_process = QProcess(page)
        preview_process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        preview_state = {"pid": None}
        tabs.addTab(sandbox_tab, "4. Sandbox")

        history_tab = QWidget()
        history_layout = QVBoxLayout(history_tab)
        timeline = QPlainTextEdit()
        timeline.setReadOnly(True)
        history_layout.addWidget(timeline)
        tabs.addTab(history_tab, "History")
        tabs.tabBar().moveTab(tabs.indexOf(flow_tab), 0)
        tabs.tabBar().moveTab(tabs.indexOf(tasks_tab), 1)
        tabs.tabBar().moveTab(tabs.indexOf(checks_tab), 2)
        tabs.tabBar().moveTab(tabs.indexOf(bugs_tab), 3)

        footer = QGridLayout()
        approve_project = QPushButton("Approve Reviewed Project")
        reopen_project = QPushButton("Reopen Project")
        recover_workers = QPushButton("Recover Interrupted Jobs")
        footer.addWidget(approve_project, 0, 0)
        footer.addWidget(reopen_project, 0, 1)
        footer.addWidget(recover_workers, 1, 0, 1, 2)
        approve_project.setToolTip("Only after every task is reviewed and every issue is closed; no app is executed.")
        recover_workers.setToolTip("Safely mark interrupted worker drafts as blocked, ready for manual retry.")
        project_options = QPushButton("Show project approval and recovery")
        project_options.setCheckable(True)
        right_layout.addWidget(project_options)
        advanced_project = QGroupBox("Project approval and recovery")
        advanced_project.setVisible(False)
        project_options.toggled.connect(advanced_project.setVisible)
        advanced_project.setLayout(footer)
        right_layout.addWidget(advanced_project)

        active_jobs = []
        meeting_queue = {"pid": None, "auto_continue": False}
        auto = {
            "project": None, "remaining": 0, "started": set(), "attempts": {},
            "continuous": False, "paused": False, "testing": False,
            "meeting_after": 5, "since_meeting": 0, "repair_count": 0,
            "waiting": False, "sandbox_stage": None, "poll_token": 0,
        }

        def update_session_status():
            if not auto["continuous"]:
                session_status.setText("Continuous mode: off. No background work is scheduled.")
            elif auto["paused"]:
                session_status.setText("Continuous mode: PAUSED. Current operation may finish; no new work will start.")
            elif auto["waiting"]:
                session_status.setText("Continuous mode: WAITING for new tasks or your review. Session remains active.")
            else:
                session_status.setText("Continuous mode: RUNNING. Automatic Docker tests and team meetings enabled.")
            running = auto["continuous"]
            continuous_start.setEnabled(not running and not active_jobs)
            continuous_pause.setEnabled(running and not auto["paused"])
            continuous_resume.setEnabled(running and auto["paused"])
            continuous_stop.setEnabled(running)

        def continuous_poll(token):
            if (not auto["continuous"] or auto["paused"]
                    or auto["poll_token"] != token):
                return
            if auto["waiting"] and not active_jobs:
                auto["waiting"] = False
                QTimer.singleShot(0, advance_auto)
            QTimer.singleShot(30000, lambda: continuous_poll(token))

        for button, tip in (
            (change_request, "Request a change for this task, or the whole project if no task is selected."),
            (plan_subtasks, "Ask the local AI manager to propose editable subtasks. Nothing is queued until you approve."),
            (run_checks_btn, "Check syntax and declared UI/backend links without executing project code."),
            (starter_btn, "Create a sample Qt app with a working save button and backend. Never overwrite files."),
            (fix_checks_btn, "Turn failed static checks into a reviewable implementation task."),
            (start_worker, "Ask the local model for a draft. It cannot execute generated code."),
            (accept_task, "Only a submitted draft can be accepted after your review."),
            (rework_task, "Send a submitted draft back for corrections."),
            (retry_task, "Reopen an accepted, blocked or reviewed task for another attempt."),
            (assign_fix, "Create an implementation task from the selected open issue."),
            (resolve_bug, "Close an issue only after its fix task is accepted."),
            (sandbox_unit, "Run project's unittest discovery inside a locked-down Docker container."),
            (sandbox_gui, "Start launch.py in a PySide6 Docker image and check for early startup failure; no GUI interactions are verified."),
            (sandbox_fix, "Queue failures from the last sandbox run as a human-reviewable fix task."),
            (continuous_start, "Start an owner-approved session: sequential coding, team meetings and Docker tests; no host execution or automatic approval."),
            (continuous_pause, "Pause new work after the current Ollama/Docker operation finishes."),
            (continuous_resume, "Resume a paused session without repeating setup authorization."),
            (continuous_stop, "Stop the session after its current operation; keep project files and test history."),
            (preview_launch, "Open the generated app in a separate Windows window, only after explicit informed consent. NOT sandboxed."),
            (preview_stop, "Stop the local preview process; Apollo itself stays open."),
        ):
            button.setToolTip(tip)

        def alert(message):
            QMessageBox.warning(page, "Project Studio", str(message))

        def project_id():
            item = projects.currentItem()
            return item.data(Qt.UserRole) if item else None

        def task_id():
            item = task_tree.currentItem()
            return item.data(0, Qt.UserRole) if item else None

        def issue_id():
            row = issue_table.currentRow()
            if row < 0:
                return None
            cell = issue_table.item(row, 0)
            return int(cell.text()) if cell else None

        def refresh_projects(select_id=None):
            """Keep context while filtering or refreshing the saved project list."""
            previous = select_id if select_id is not None else project_id()
            query = project_search.text().strip().casefold()
            projects.blockSignals(True)
            projects.clear()
            chosen = None
            for item in self.store.list_projects():
                if query and query not in (item["title"] + " " + item["brief"]).casefold():
                    continue
                state_name = "Approved" if item["state"] == "approved" else "In progress"
                row = QListWidgetItem(f"{item['title']}   ·   {state_name}")
                row.setData(Qt.UserRole, item["id"])
                row.setToolTip(f"Project #{item['id']}, last updated {item['updated_at']}")
                projects.addItem(row)
                if item["id"] == previous:
                    chosen = row
            if chosen:
                projects.setCurrentItem(chosen)
            elif projects.count():
                projects.setCurrentRow(0)
            projects.blockSignals(False)
            refresh_details()

        def update_actions(project_state=None):
            """Contextual buttons stay disabled until there is a valid choice.

            Reuse the current project snapshot on UI refresh rather than
            needlessly fetching the same full task/issue tables again.
            """
            pid = project_id()
            if pid is None:
                for control in (add_subtask, change_request, plan_subtasks, start_worker, accept_task,
                                rework_task, retry_task, report_bug, assign_fix, resolve_bug,
                                approve_project, reopen_project, recover_workers,
                                starter_btn, run_checks_btn, fix_checks_btn, show_folder_btn,
                                sandbox_unit, sandbox_gui, sandbox_fix, preview_launch):
                    control.setEnabled(False)
                update_session_status()
                return
            state = project_state if project_state is not None else self.store.details(pid)
            selected_task = next((t for t in state["tasks"] if t["id"] == task_id()), None)
            choices = task_actions(selected_task, state, bool(active_jobs))
            for button, action in ((add_subtask, "subtask"), (start_worker, "draft"),
                                   (accept_task, "accept"), (rework_task, "rework"),
                                   (retry_task, "retry")):
                button.setEnabled(choices[action])
            change_request.setEnabled(state["project"]["state"] != "approved")
            plan_subtasks.setEnabled(
                state["project"]["state"] != "approved" and not active_jobs
                and selected_task is not None and selected_task["parent_id"] is None
                and selected_task["state"] == "todo"
            )
            starter_btn.setEnabled(state["project"]["state"] != "approved")
            run_checks_btn.setEnabled(True)
            show_folder_btn.setEnabled(True)
            sandbox_unit.setEnabled(not active_jobs)
            sandbox_gui.setEnabled(not active_jobs)
            preview_launch.setEnabled(
                not active_jobs and preview_process.state() == QProcess.ProcessState.NotRunning
            )
            preview_stop.setEnabled(preview_process.state() != QProcess.ProcessState.NotRunning)
            update_session_status()
            sandbox_runs = self.store.sandbox_history(pid, 1)
            sandbox_fix.setEnabled(
                state["project"]["state"] != "approved"
                and bool(sandbox_runs)
                and sandbox_runs[0]["status"] in ("failed", "timeout")
                and not active_jobs
            )
            recent_checks = self.store.check_history(pid, 1)
            fix_checks_btn.setEnabled(
                state["project"]["state"] != "approved"
                and bool(recent_checks)
                and recent_checks[0]["status"] == "failed"
            )
            report_bug.setEnabled(state["project"]["state"] != "approved")
            selected_issue = next((i for i in state["issues"] if i["id"] == issue_id()), None)
            issue_choices = issue_actions(selected_issue, state)
            assign_fix.setEnabled(issue_choices["assign"])
            resolve_bug.setEnabled(issue_choices["close"])
            can_approve = (state["project"]["state"] != "approved"
                           and bool(state["tasks"])
                           and all(t["state"] == "accepted" for t in state["tasks"])
                           and all(i["state"] == "closed" for i in state["issues"]))
            approve_project.setEnabled(can_approve)
            reopen_project.setEnabled(state["project"]["state"] == "approved")
            recover_workers.setEnabled(
                not active_jobs and any(t["state"] == "running" for t in state["tasks"])
                and state["project"]["state"] != "approved"
            )

        def refresh_details():
            """Rebuild changed rows without losing the worker or issue selection."""
            pid = project_id()
            previous_task = task_id()
            previous_issue = issue_id()
            task_tree.blockSignals(True)
            issue_table.blockSignals(True)
            task_tree.clear()
            issue_table.setRowCount(0)
            timeline.clear()
            if pid is None:
                project_heading.setText(
                    "No matches. Clear the search." if projects.count() == 0 and project_search.text()
                    else "Select or create an app project"
                )
                path_label.setText("Projects stay on this computer.")
                overview.setText("Create a project to assign tasks, review drafts and track fixes.")
                completion.setValue(0)
                checks_status.setText("Select an app project to see its test results.")
                checks_report.clear()
                sandbox_status.setText("Select a project to see sandbox test results.")
                sandbox_report.clear()
                result_text.clear()
                team_transcript.clear()
                meeting_status.setText("No project selected.")
                team_flow.update_flow(flow_snapshot({"tasks": []}))
                team_meeting_btn.setEnabled(False)
                task_tree.blockSignals(False)
                issue_table.blockSignals(False)
                update_actions()
                return
            state = self.store.details(pid)
            project = state["project"]
            metrics = project_metrics(state)
            project_heading.setText(f"{project['title']}  ·  {project['state'].title()}")
            path_label.setText("Saved locally: workspace/app_development/" + project["folder"])
            overview.setText(
                f"{metrics['accepted']} of {metrics['total']} tasks accepted"
                f"   •   {metrics['running']} running"
                f"   •   {metrics['review']} awaiting review"
                f"   •   {metrics['blocked']} blocked"
                f"   •   {metrics['open_issues']} open issues"
            )
            completion.setValue(metrics["percent"])
            meetings = self.store.meetings(pid, 5)
            events = self.store.audit(pid, 100)
            team_flow.update_flow(flow_snapshot(state, meetings, events))
            team_meeting_btn.setEnabled(
                not active_jobs and state["project"]["state"] != "approved")
            if meetings:
                recent_meeting = meetings[0]
                meeting_status.setText(
                    f"Last meeting: {recent_meeting['created_at']}  ·  "
                    f"{recent_meeting['topic']}  ·  {len(recent_meeting['turns'])} participants")
                transcript = []
                for meeting in meetings:
                    transcript.append(f"TEAM MEETING #{meeting['id']}  ·  {meeting['created_at']}\n"
                                      f"Topic: {meeting['topic']}")
                    transcript.extend(
                        f"{turn.get('at', meeting['created_at'])[:19]}  "
                        f"{turn['role'].upper()} → TEAM: {turn['message']}"
                        for turn in meeting["turns"] if turn["role"] != "manager")
                    manager_turn = meeting["turns"][-1]
                    transcript.append(
                        f"{manager_turn.get('at', meeting['created_at'])[:19]}  "
                        "MANAGER DECISION RECORD:\n" + meeting["decisions"])
                    transcript.append("──────────────────")
                team_transcript.setPlainText("\n\n".join(transcript))
            else:
                meeting_status.setText("No team meeting recorded yet.")
                team_transcript.setPlainText(
                    "Hold a team meeting to exchange actual Ollama responses. "
                    "Only completed meetings are saved as decisions.")

            recent_checks = self.store.check_history(pid, 1)
            if recent_checks:
                latest = recent_checks[0]["report"]
                checks_status.setText(
                    f"Latest static check: {latest['status'].upper()}  •  "
                    "Runtime UI: NOT TESTED  •  Project code: NOT EXECUTED"
                )
                checks_report.setPlainText("\n".join(
                    f"[{item['status'].upper()}] {item['check']}: {item['detail']}"
                    for item in latest['checks']
                ) + "\n\n" + latest['note'])
            else:
                checks_status.setText("No checks run. Add Python files and foundry.json to the project folder.")
                checks_report.setPlainText(
                    "Phase 1 checks Python syntax and declared UI-to-backend signals. "
                    "A green result is not proof that your generated app can launch. "
                    "Use the reference contract format from Foundry documentation."
                )
            recent_sandbox = self.store.sandbox_history(pid, 1)
            if recent_sandbox:
                recent = recent_sandbox[0]["report"]
                sandbox_status.setText(
                    f"{recent['kind']}: {recent['status'].upper()}  •  "
                    f"Code executed: {'YES, in Docker' if recent.get('executed_project_code') else 'NO'}"
                )
                sandbox_report.setPlainText(
                    f"Date: {recent['created_at']}\n"
                    f"Image: {recent.get('image', 'not available')}\n"
                    f"Reason: {recent.get('reason', '')}\n"
                    f"GUI interactions verified: {'YES' if recent.get('passed_ui_interactions') else 'NO'}\n\n"
                    + recent.get("output", "")
                )
            else:
                sandbox_status.setText("No isolated test has run. Docker Desktop and approved images are required.")
                sandbox_report.setPlainText(
                    "Run Tests in Sandbox uses Python unittest tests. "
                    "GUI Launch Smoke Test checks whether launch.py stays alive for three seconds. "
                    "Neither test grants generated code access to Apollo's files or network."
                )
            nodes = {}
            for task in state["tasks"]:
                display_state = {
                    "todo": "To do", "running": "Working", "review": "Needs review",
                    "accepted": "Accepted", "blocked": "Blocked"
                }.get(task["state"], task["state"])
                node = QTreeWidgetItem([
                    task["title"], task["role"].title(), display_state, str(task["iteration"])
                ])
                node.setData(0, Qt.UserRole, task["id"])
                nodes[task["id"]] = node
                parent = nodes.get(task["parent_id"]) if task["parent_id"] else None
                if parent:
                    parent.addChild(node)
                else:
                    task_tree.addTopLevelItem(node)
            task_tree.expandAll()
            if previous_task in nodes:
                task_tree.setCurrentItem(nodes[previous_task])
            issue_table.setRowCount(len(state["issues"]))
            for i, issue in enumerate(state["issues"]):
                for j, value in enumerate((
                    str(issue["id"]), issue["title"], issue["state"].replace("_", " ").title(),
                    str(issue["assigned_task"] or "Unassigned")
                )):
                    issue_table.setItem(i, j, QTableWidgetItem(value))
                if issue["id"] == previous_issue:
                    issue_table.selectRow(i)
            timeline.setPlainText("\n".join(
                f"{e['created_at']}  {e['kind']}  {e['detail']}"
                for e in events[:60]
            ) or "No activity yet. Start by assigning a worker.")
            task_tree.blockSignals(False)
            issue_table.blockSignals(False)
            display_task(update_controls=False)
            update_actions(state)

        def display_task(update_controls=True):
            tid = task_id()
            if tid is None:
                result_text.setPlainText(
                    "Select a task to view instructions, request a local AI draft, "
                    "or read the feedback from the last review."
                )
                if update_controls:
                    update_actions()
                return
            task = self.store._task(tid)
            result_text.setPlainText(
                f"WORKER: {task['role'].title()}    STATUS: {task['state'].title()}\n\n"
                f"JOB\n{task['brief']}\n\n"
                f"DRAFT (NOT EXECUTED)\n{task['result'] or 'Start this task to request a draft.'}\n\n"
                f"REVIEW FEEDBACK\n{task['feedback'] or 'No review yet.'}\n\n"
                f"EVIDENCE\n{task['evidence'] or 'Evidence has not been attached.'}"
            )
            if update_controls:
                update_actions()

        def add_project_action():
            title, ok = QInputDialog.getText(page, "New App Project", "Project name:")
            if not ok or not title.strip():
                return
            brief, ok = QInputDialog.getMultiLineText(page, "Project Brief", "What should this app do?")
            if not ok or not brief.strip():
                return
            try:
                data = self.store.add_project(title, brief)
                project_search.clear()
                refresh_projects(data["project"]["id"])
            except (ValueError, OSError) as exc:
                alert(exc)

        def add_subtask_action():
            tid = task_id()
            if tid is None:
                return alert("Select a parent task first.")
            title, ok = QInputDialog.getText(page, "New Subtask", "Subtask name:")
            if not ok or not title.strip():
                return
            brief, ok = QInputDialog.getMultiLineText(page, "Subtask Instructions", "Describe the worker's job:")
            if not ok or not brief.strip():
                return
            role, ok = QInputDialog.getItem(
                page, "Assign Worker", "Specialist:", ["manager", "architect", "implementer",
                "tester", "reviewer", "integrator"], 2, False)
            if not ok:
                return
            try:
                self.store.add_subtask(tid, title, brief, role)
                refresh_details()
            except (ValueError, KeyError) as exc:
                alert(exc)

        def finished_manager_plan(tid, proposal, error):
            active_jobs[:] = [item for item in active_jobs if item[0] != f"plan:{tid}"]
            if error:
                feed("Manager: Planning failed: " + error[:300])
                alert("Manager proposal could not be produced: " + error[:500])
                update_actions()
                return
            feed("Manager: Proposed subtasks (review required): " + proposal[:900])
            edited, ok = QInputDialog.getMultiLineText(
                page, "Review AI Manager Plan",
                "Review and edit this JSON proposal. Nothing is added until you accept.",
                proposal
            )
            if not ok:
                update_actions()
                return
            try:
                data = json.loads(edited)
                tasks = validate_subtask_plan(data)
                self.store.add_subtasks(tid, tasks)
                feed("Manager: You approved " + str(len(tasks)) + " subtasks. Workers are ready.")
                refresh_details()
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                alert("Subtask plan was NOT added: " + str(exc))
            finally:
                update_actions()

        def propose_manager_plan_action():
            tid, pid = task_id(), project_id()
            if tid is None or pid is None:
                return alert("Select a top-level task to divide into subtasks.")
            if active_jobs:
                return alert("Finish the current local model job before starting another.")
            try:
                model = model_from_config(self.base)
                state = self.store.details(pid)
                target = next((t for t in state["tasks"] if t["id"] == tid), None)
                if not target or target["parent_id"] is not None or target["state"] != "todo":
                    raise ValueError("Choose a not-started top-level task for the manager.")
                signals = WorkerSignal()
                signals.finished.connect(finished_manager_plan)
                active_jobs.append((f"plan:{tid}", signals))
                QThreadPool.globalInstance().start(PlanJob(tid, state, model, signals))
                update_actions()
            except (ValueError, KeyError, OSError) as exc:
                alert(exc)


        def meeting_spoke(pid, role, message):
            # A live response from the actual running local model, not simulated text.
            if pid == project_id():
                team_flow.note_speaker(role)
            feed(f"Team meeting · {role.title()}: {message[:350]}")
            if pid == project_id():
                team_transcript.appendPlainText(role.upper() + ": " + message + "\n")
                meeting_status.setText("Team meeting in progress: " + role.title())

        def meeting_finished(pid, report, error):
            team_flow.finish_meeting()
            active_jobs[:] = [item for item in active_jobs if item[0] != f"meeting:{pid}"]
            should_continue = (meeting_queue["pid"] == pid
                               and meeting_queue["auto_continue"])
            meeting_queue.update({"pid": None, "auto_continue": False})
            if error:
                feed("Manager: Team meeting failed: " + error[:340])
                meeting_status.setText("Meeting failed. No group decisions saved.")
                if auto["continuous"] and auto["project"] == pid:
                    auto["paused"] = True
                else:
                    auto["project"] = None
            else:
                try:
                    self.store.save_meeting(pid, report)
                    feed("Manager: Team decisions saved and distributed to future workers.")
                    if pid == project_id():
                        refresh_details()
                        tabs.setCurrentWidget(flow_tab)
                except (ValueError, KeyError, OSError) as exc:
                    feed("Manager: Meeting could not be saved: " + str(exc))
                    should_continue = False
            if should_continue and not error:
                if auto["continuous"]:
                    if auto["project"] == pid and not auto["paused"]:
                        QTimer.singleShot(0, advance_auto)
                elif pid == project_id():
                    QTimer.singleShot(0, lambda: start_auto(pid))
            else:
                if auto["continuous"] and auto["project"] == pid and error:
                    auto["paused"] = True
                    feed("Manager: Continuous session paused because the team meeting failed.")
                update_actions()

        def start_team_meeting(pid, topic, *, auto_continue=False):
            if pid is None:
                return alert("Select a project before starting a team meeting.")
            if active_jobs:
                return alert("Wait until the current worker or meeting finishes.")
            try:
                state = self.store.details(pid)
                if state["project"]["state"] == "approved":
                    raise ValueError("Reopen this approved project before further planning.")
                signals = MeetingSignals()
                signals.spoke.connect(meeting_spoke)
                signals.finished.connect(meeting_finished)
                active_jobs.append((f"meeting:{pid}", signals))
                meeting_queue.update({"pid": pid, "auto_continue": auto_continue})
                meeting_status.setText("Meeting in progress: checking shared requirements...")
                team_flow.begin_meeting()
                team_transcript.setPlainText("Live meeting responses (saved after full completion):\n")
                feed("Manager: Starting a real six-turn team meeting about " + topic[:150])
                tabs.setCurrentWidget(flow_tab)
                QThreadPool.globalInstance().start(
                    MeetingJob(pid, state, model_from_config(self.base), topic, signals))
                update_actions()
            except (OSError, ValueError, KeyError) as exc:
                meeting_queue.update({"pid": None, "auto_continue": False})
                active_jobs[:] = [a for a in active_jobs if a[0] != f"meeting:{pid}"]
                alert("Could not start team meeting: " + str(exc))

        def manual_team_meeting():
            pid = project_id()
            if pid is None:
                return alert("Select a project first.")
            topic, ok = QInputDialog.getText(
                page, "Foundry Team Meeting", "What should the team discuss?",
                text="Architecture, blockers, test findings and next steps")
            if ok and topic.strip():
                start_team_meeting(pid, topic.strip())

        def advance_auto():
            """One sequential worker at a time; continuous sessions idle safely.

            Never auto-approve projects or execute code on the host.
            """
            pid = auto["project"]
            if pid is None or active_jobs or auto["testing"] or auto["paused"]:
                return
            if not auto["continuous"] and (auto["remaining"] <= 0 or pid != project_id()):
                auto["project"] = None
                feed("Manager: Draft cycle paused. Review worker results before continuing.")
                return
            try:
                state = self.store.details(pid)
                # Start with the newest owner change, not stale template tasks.
                candidates = [t for t in state["tasks"]
                              if t["state"] == "todo" and t["id"] not in auto["started"]
                              and (t["role"] not in ("reviewer", "integrator", "tester") or any(x["role"] == "implementer" and x["state"] in ("review", "accepted") and "static checks passed" in x["evidence"].lower() for x in state["tasks"]))]
                # A new project must produce runnable source before cycling
                # through architecture essays and meeting commentary.
                # Respect an explicitly queued owner change first.
                candidates.sort(key=lambda t: (
                    0 if t["title"].startswith(("Revise", "Fix:")) else
                    1 if t["role"] == "implementer" else
                    2 if t["role"] == "architect" else 3,
                    t["id"]))
                if not candidates:
                    if auto["continuous"]:
                        if not auto["waiting"]:
                            feed("Manager: No ready tasks. Waiting for your review or new instructions; session remains active.")
                        auto["waiting"] = True
                        update_session_status()
                    else:
                        auto["project"] = None
                        feed("Manager: Drafts ready for review. Reviewer and integrator are held until implementation is verified.")
                    return
                if auto["continuous"] and auto["since_meeting"] >= auto["meeting_after"]:
                    auto["since_meeting"] = 0
                    feed("Manager: Scheduling automatic team checkpoint before more work.")
                    start_team_meeting(pid, "Automatic checkpoint: review code, test findings, blockers and next tasks",
                                       auto_continue=True)
                    return
                task = candidates[0]
                model = model_from_config(self.base)
                auto["started"].add(task["id"])
                auto["remaining"] -= 1
                auto["waiting"] = False
                update_session_status()
                feed("Manager: Assigning " + task["title"] + " to " + task["role"] + ".")
                self.store.start_task(task["id"])
                self.store.record_handoff(pid, "manager", task["role"],
                                          "Assigned: " + task["title"][:120], task["id"])
                signal = WorkerSignal()
                signal.finished.connect(finished_job)
                signal.update.connect(feed)
                active_jobs.append((task["id"], signal))
                QThreadPool.globalInstance().start(
                    DraftJob(task["id"], self.store.details(pid), model, signal))
                refresh_details()
            except (OSError, ValueError, KeyError) as exc:
                if auto["continuous"]:
                    auto["paused"] = True
                else:
                    auto["project"] = None
                feed("Manager: Automatic work paused: " + str(exc))
                alert("Automatic worker failed: " + str(exc))
                update_session_status()

        def start_auto(pid):
            if active_jobs or auto["continuous"]:
                return alert("A worker or continuous session is already active.")
            auto.update({"project": pid, "remaining": 5, "started": set(), "attempts": {}})
            feed("Manager: Starting up to five sequential worker drafts. Human review remains required.")
            QTimer.singleShot(0, advance_auto)

        def start_continuous_action():
            pid = project_id()
            if pid is None:
                return alert("Select or create a project first.")
            if active_jobs or auto["continuous"] or auto["project"] is not None:
                return alert("Another worker or development session is active.")
            try:
                state = self.store.details(pid)
                if state["project"]["state"] == "approved":
                    return alert("Reopen the approved project before building more code.")
                from apollo_foundry_sandbox import availability
                check = availability("unit")
                if not check["ok"]:
                    return alert(
                        "Docker is not ready: " + check["reason"] +
                        "\nInstall with Setup/14_INSTALL_DOCKER_DESKTOP.bat, "
                        "then run Setup/09_SETUP_FOUNDRY_SANDBOX.bat."
                    )
            except (OSError, ValueError, KeyError) as exc:
                return alert("Continuous session cannot start: " + str(exc))
            if QMessageBox.warning(
                page, "Authorize Continuous Foundry Session",
                "Start a continuous coding session for this project?\n\n"
                "Apollo will hold team meetings, generate and revise source files, "
                "and automatically execute project tests inside restricted Docker "
                "containers (network disabled, read-only source snapshot). "
                "Generated code is untrusted; Docker isolation is not absolute.\n\n"
                "This permission lasts only until you Stop or close Apollo. "
                "No generated code runs directly on Windows, no apps are installed, "
                "and no drafts or projects are approved automatically.\n\n"
                "Pause/Stop take effect after the current worker or test finishes. "
                "When there are no ready tasks, the team waits for your input.\n\n"
                "Start this session?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            ) != QMessageBox.Yes:
                return
            auto.update({
                "project": pid, "remaining": 1000000000, "started": set(),
                "attempts": {}, "continuous": True, "paused": False,
                "testing": False, "since_meeting": 0, "repair_count": 0,
                "waiting": False, "sandbox_stage": None,
                "poll_token": auto["poll_token"] + 1,
            })
            feed("Manager: Continuous development authorized. Docker tests and periodic team meetings enabled.")
            update_session_status()
            token = auto["poll_token"]
            QTimer.singleShot(30000, lambda: continuous_poll(token))
            start_team_meeting(pid, "Continuous kickoff: deliver runnable code, tests, and review checkpoints",
                               auto_continue=True)

        def pause_continuous_action():
            if auto["continuous"]:
                auto["paused"] = True
                auto["poll_token"] += 1
                feed("Owner: Pause requested. No new jobs after the current operation.")
                update_session_status()

        def resume_continuous_action():
            if auto["continuous"] and auto["paused"]:
                auto["paused"] = False
                auto["poll_token"] += 1
                token = auto["poll_token"]
                feed("Owner: Continuous session resumed.")
                update_session_status()
                QTimer.singleShot(30000, lambda: continuous_poll(token))
                if not active_jobs and not auto["testing"]:
                    QTimer.singleShot(0, advance_auto)

        def stop_continuous_action():
            if auto["continuous"]:
                auto.update({
                    "continuous": False, "paused": False, "project": None,
                    "waiting": False, "poll_token": auto["poll_token"] + 1,
                })
                meeting_queue.update({"pid": None, "auto_continue": False})
                feed("Owner: Session stopped. Current operation may finish, but no more work will start.")
                update_session_status()

        def retry_generation(tid, problem):
            pid = auto["project"]
            if pid is None:
                return
            try:
                state = self.store.details(pid)
                signal = WorkerSignal()
                signal.finished.connect(finished_job)
                signal.update.connect(feed)
                active_jobs.append((tid, signal))
                attempt = auto["attempts"].get(tid, 0)
                with_research = research_toggle.isChecked() and attempt >= 2
                feed("Manager: Repair attempt " + str(attempt + 1) + "/3 for task " + str(tid) + ".")
                QThreadPool.globalInstance().start(DraftJob(
                    tid, state, model_from_config(self.base), signal,
                    repair=problem, research=with_research))
            except (ValueError, KeyError, OSError) as exc:
                if auto["continuous"]:
                    auto["paused"] = True
                else:
                    auto["project"] = None
                self.store.fail_task(tid, str(exc)[:2200])
                feed("Manager: Repair halted: " + str(exc))
                refresh_details()

        def finished_job(tid, draft, error):
            pending_retry = False
            try:
                task = self.store._task(tid)
                evidence = "Local Ollama draft only; code not executed."
                if not error and task["role"] == "implementer":
                    try:
                        saved = save_bundle(self.store.project_folder(task["project_id"]), draft)
                        feed("Implementer: Created/revised " + ", ".join(saved["files"]))
                        report = self.store.run_checks(task["project_id"])
                        findings = [item["detail"] for item in report.get("checks", [])
                                    if item["status"] != "pass"]
                        if report["status"] != "passed":
                            raise ValueError("Static checks " + report["status"] + ": " + "; ".join(findings)[:800])
                        evidence = "Project source files staged; static checks passed. Runtime NOT tested."
                        draft = "Source files: " + ", ".join(saved["files"]) + "\n" + saved["summary"] + "\n" + evidence
                        feed("Tester: Static checks passed. Isolated runtime/GUI tests still require approval.")
                    except (ValueError, OSError, TypeError, KeyError) as exc:
                        error = "File generation or verification failed: " + str(exc)
                if error and auto["project"] == task["project_id"]:
                    attempts = auto["attempts"].get(tid, 0) + 1
                    auto["attempts"][tid] = attempts
                    if attempts < 3:
                        feed("Manager: Attempt " + str(attempts) + "/3 failed. Diagnosing and retrying: " + error[:350])
                        active_jobs[:] = [x for x in active_jobs if x[0] != tid]
                        pending_retry = True
                        QTimer.singleShot(0, lambda tid=tid, issue=error: retry_generation(tid, issue))
                        refresh_details()
                        return
                if error:
                    feed("Worker: Task " + str(tid) + " blocked after retries: " + error[:380])
                    if auto["continuous"]:
                        auto["paused"] = True
                    else:
                        auto["project"] = None
                    self.store.fail_task(tid, error[:2300])
                    alert("Worker stopped safely. Review the failure and generated files.\n\n" + error[:850])
                    if task["project_id"] == project_id():
                        QTimer.singleShot(0, lambda pid=task["project_id"], issue=error:
                            start_team_meeting(pid, "Blocked worker: diagnose " + issue[:420]))
                else:
                    feed("Worker: Task " + str(tid) + " ready for review: " + draft[:500])
                    self.store.submit_task(tid, draft[:14000], evidence)
                    self.store.record_handoff(task["project_id"], task["role"], "manager",
                                              "Draft submitted for review: " + task["title"][:115], tid)
                    if auto["continuous"] and auto["project"] == task["project_id"]:
                        auto["since_meeting"] += 1
                        if task["role"] == "implementer":
                            auto["testing"] = True
                            auto["sandbox_stage"] = "unit"
                            feed("Tester: Automatic Docker unit and GUI startup checks queued.")
                            QTimer.singleShot(0, lambda pid=task["project_id"]:
                                              start_auto_sandbox(pid, "unit"))
            except (ValueError, KeyError, OSError) as exc:
                if auto["continuous"]:
                    auto["paused"] = True
                else:
                    auto["project"] = None
                alert("Worker result could not be saved: " + str(exc))
            finally:
                active_jobs[:] = [x for x in active_jobs if x[0] != tid]
                refresh_details()
                if auto["project"] is not None and not pending_retry and not auto["testing"]:
                    QTimer.singleShot(0, advance_auto)
                update_session_status()

        def draft_action():
            tid, pid = task_id(), project_id()
            if tid is None or pid is None:
                return alert("Select a task before drafting.")
            try:
                state = self.store.details(pid)
                model = model_from_config(self.base)
                self.store.start_task(tid)
                feed("Worker: Starting task " + str(tid) + " with " + model + "...")
                state = self.store.details(pid)
                signal = WorkerSignal()
                signal.finished.connect(finished_job)
                signal.update.connect(feed)
                active_jobs.append((tid, signal))
                QThreadPool.globalInstance().start(DraftJob(tid, state, model, signal))
                refresh_details()
            except (ValueError, KeyError, OSError) as exc:
                alert(exc)

        def review_action(approved):
            tid = task_id()
            if tid is None:
                return alert("Select a reviewed draft first.")
            feedback, ok = QInputDialog.getMultiLineText(
                page, "Accept Draft" if approved else "Request Changes",
                "Evidence and review notes:" if approved else "What needs fixing?")
            if not ok or not feedback.strip():
                return
            try:
                self.store.review_task(tid, approved, feedback)
                feed("Review: " + ("Accepted " if approved else "Changes requested for ") + "task " + str(tid) + ".")
                refresh_details()
            except (ValueError, KeyError) as exc:
                alert(exc)

        def retry_action():
            tid = task_id()
            if tid is None:
                return alert("Select a task to retry.")
            reason, ok = QInputDialog.getText(page, "Retry Selected Task", "Why is this task being reopened?")
            if not ok or not reason.strip():
                return
            try:
                self.store.reopen_task(tid, reason)
                refresh_details()
            except (ValueError, KeyError) as exc:
                alert(exc)

        def recover_action():
            pid = project_id()
            if pid is None:
                return alert("Select a project first.")
            if active_jobs:
                return alert("Workers are still running in this Apollo session. Wait for them to finish.")
            if QMessageBox.question(
                page, "Recover Interrupted Workers",
                "Mark any jobs stuck on Running as Blocked so you can inspect and retry them? "
                "This does not discard existing drafts.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            ) != QMessageBox.Yes:
                return
            count = self.store.recover_interrupted_tasks(pid)
            refresh_details()
            QMessageBox.information(page, "Recovery Complete", f"Recovered {count} interrupted job(s).")

        def request_change_action():
            pid = project_id()
            if pid is None:
                return alert("Select an app project first.")
            tid = task_id()
            subject = self.store._task(tid)["title"] if tid else "Entire app project"
            change, ok = QInputDialog.getMultiLineText(
                page, "Request a Change", f"What would you like changed?\nTarget: {subject}"
            )
            if not ok or not change.strip():
                return
            try:
                queued = self.store.request_change(pid, change, tid)
                refresh_details()
                tabs.setCurrentWidget(tasks_tab)
                for idx in range(task_tree.topLevelItemCount()):
                    node = task_tree.topLevelItem(idx)
                    if node.data(0, Qt.UserRole) == queued["task_id"]:
                        task_tree.setCurrentItem(node)
                        break
            except (ValueError, KeyError) as exc:
                alert(exc)

        def create_starter_action():
            pid = project_id()
            if pid is None:
                return alert("Select a project first.")
            if QMessageBox.question(
                page, "Create Starter UI",
                "Create a small Qt UI + Python backend for this project? "
                "Existing source files are never overwritten and nothing is launched.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            ) != QMessageBox.Yes:
                return
            try:
                self.store.create_starter_ui(pid)
                refresh_details()
                tabs.setCurrentWidget(checks_tab)
            except (FileExistsError, OSError, ValueError, KeyError) as exc:
                alert(exc)

        def run_static_checks_action():
            pid = project_id()
            if pid is None:
                return alert("Select an app project first.")
            run_checks_btn.setEnabled(False)
            try:
                report = self.store.run_checks(pid)
                refresh_details()
                tabs.setCurrentWidget(checks_tab)
                if report["status"] == "failed":
                    QMessageBox.warning(
                        page, "Foundry checks found problems",
                        "UI/code link checks failed. The recorded findings can be "
                        "sent to an implementer using Request Fix for Failures."
                    )
            except (OSError, ValueError, KeyError, UnicodeError) as exc:
                alert("The test run could not start: " + str(exc))
            finally:
                update_actions()

        def sandbox_finished(pid, raw_report, error):
            active_jobs[:] = [x for x in active_jobs if x[0] != f"sandbox:{pid}"]
            if error:
                sandbox_status.setText("Sandbox failed before a report could be saved.")
                sandbox_report.setPlainText(error)
                alert("Sandbox could not start: " + error[:450])
            else:
                try:
                    report = json.loads(raw_report)
                except (ValueError, TypeError):
                    report = {"status": "failed", "reason": "Malformed sandbox report"}
                if report.get("status") in ("unavailable", "incomplete"):
                    sandbox_status.setText(
                        "Sandbox not run: " + report.get("reason", "Missing prerequisite")
                    )
                if report.get("status") in ("failed", "timeout"):
                    sandbox_status.setText(
                        "Sandbox detected a failure. Review logs and use Send Failures to Worker."
                    )
            refresh_details()
            tabs.setCurrentWidget(sandbox_tab)

        def run_sandbox_action(kind):
            pid = project_id()
            if pid is None:
                return alert("Select an app project first.")
            if active_jobs:
                return alert("A worker or sandbox run is already active.")
            what = ("project unit tests" if kind == "unit" else "a three-second GUI startup smoke test")
            if QMessageBox.question(
                page, "Run Isolated Foundry Sandbox",
                f"Run {what} in a Docker container?\n\n"
                "Untrusted project code will execute inside a restricted container "
                "with no network or access to Apollo's storage. "
                "Docker's isolation is not an absolute security guarantee. "
                "No fallback will run on the host if Docker is unavailable.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            ) != QMessageBox.Yes:
                return
            signals = WorkerSignal()
            signals.finished.connect(sandbox_finished)
            active_jobs.append((f"sandbox:{pid}", signals))
            sandbox_status.setText("Starting isolated Docker test…")
            sandbox_report.setPlainText(
                "Preparing a read-only project snapshot. Generated code is never "
                "launched directly by Apollo's Python interpreter."
            )
            QThreadPool.globalInstance().start(SandboxJob(pid, kind, self.store, signals))
            update_actions()

        def preview_output_ready():
            data = bytes(preview_process.readAllStandardOutput()).decode(
                "utf-8", errors="replace"
            )
            if data:
                # Bound console history to avoid unlimited RAM usage.
                preview_output.appendPlainText(data[:8000].rstrip())
                if len(preview_output.toPlainText()) > 16000:
                    preview_output.setPlainText(preview_output.toPlainText()[-12000:])

        def preview_finished(code, _status):
            preview_output_ready()
            preview_status.setText(
                f"App preview exited (code {code}). "
                "Review console output; use Report Issue to send problems to Foundry."
            )
            preview_state["pid"] = None
            update_actions()

        def preview_error(_error):
            preview_status.setText("Local preview failed: " + preview_process.errorString())
            update_actions()

        def launch_local_preview_action():
            pid = project_id()
            if pid is None:
                return alert("Select a project to preview.")
            if active_jobs:
                return alert("Wait for the current worker or sandbox test to finish.")
            if preview_process.state() != QProcess.ProcessState.NotRunning:
                return alert("Stop the existing app preview first.")
            try:
                from apollo_foundry_preview import prepare_local_preview
                target = prepare_local_preview(self.store.project_folder(pid))
            except (ValueError, OSError, UnicodeError, KeyError) as exc:
                return alert("Cannot launch app: " + str(exc))
            if QMessageBox.warning(
                page, "UNSANDBOXED Windows App Preview",
                "This launches GENERATED Python code directly on your PC.\n\n"
                "It is NOT isolated. It can read, modify or delete files, "
                "use your network, and act with your Windows user permissions.\n\n"
                "Only proceed if you have reviewed the source and trust it. "
                "Prefer Run Tests in Sandbox first.\n\n"
                "Launch this app locally now?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            ) != QMessageBox.Yes:
                return
            preview_state["pid"] = pid
            preview_output.clear()
            preview_status.setText(
                "Starting app in a separate Windows window (UNSANDBOXED)..."
            )
            preview_process.setWorkingDirectory(str(target.parent))
            # No shell, no command-line arguments supplied by generated code.
            # -B avoids bytecode files; it is NOT a security boundary.
            preview_process.start(sys.executable, ["-B", str(target)])
            tabs.setCurrentWidget(sandbox_tab)
            update_actions()

        def stop_local_preview_action():
            if preview_process.state() != QProcess.ProcessState.NotRunning:
                preview_status.setText("Stopping app preview...")
                preview_process.kill()

        preview_process.readyReadStandardOutput.connect(preview_output_ready)
        preview_process.started.connect(
            lambda: preview_status.setText(
                "App window process running (UNSANDBOXED). "
                "Interact with its separate window; click Stop App when finished."
            )
        )
        preview_process.finished.connect(preview_finished)
        preview_process.errorOccurred.connect(preview_error)
        preview_launch.clicked.connect(launch_local_preview_action)
        preview_stop.clicked.connect(stop_local_preview_action)

        def sandbox_fix_action():
            pid = project_id()
            if pid is None:
                return alert("Select a project first.")
            history = self.store.sandbox_history(pid, 1)
            if not history or history[0]["status"] not in ("failed", "timeout"):
                return alert("Run a sandbox test that identifies a failure first.")
            report = history[0]["report"]
            note = (
                f"Foundry isolated {report['kind']} test reported {report['status']}.\n"
                f"Cause: {report.get('reason', '')}\n"
                f"Output:\n{report.get('output', '')[-3200:]}\n"
                "Propose a source fix and appropriate regression tests. "
                "Do not claim a passing test or apply changes without approval."
            )
            if QMessageBox.question(
                page, "Send Sandbox Failures to Worker",
                "Create a new reviewed coding task from the last sandbox failure?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            ) != QMessageBox.Yes:
                return
            try:
                self.store.request_change(pid, note)
                refresh_details()
                tabs.setCurrentWidget(tasks_tab)
            except (ValueError, KeyError) as error:
                alert(error)

        def request_check_fix_action():
            pid = project_id()
            if pid is None:
                return alert("Select a project first.")
            history = self.store.check_history(pid, 1)
            if not history or history[0]["status"] != "failed":
                return alert("Only a failed, saved check run can create a fix task.")
            failures = [
                f"{item['check']}: {item['detail']}"
                for item in history[0]["report"]["checks"] if item["status"] == "fail"
            ]
            instructions = (
                "Correct these static syntax/UI-to-code check failures:\n"
                + "\n".join(failures)[:3800]
                + "\nConfirm the changes with another static check. "
                  "Do not claim this proves runtime GUI functionality."
            )
            if QMessageBox.question(
                page, "Create Fix Task", "Assign the detected UI/code failures to an implementer?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            ) != QMessageBox.Yes:
                return
            try:
                self.store.request_change(pid, instructions)
                refresh_details()
                tabs.setCurrentWidget(tasks_tab)
            except (ValueError, KeyError) as exc:
                alert(exc)

        def open_project_folder_action():
            pid = project_id()
            if pid is None:
                return alert("Select a project first.")
            try:
                from PySide6.QtCore import QUrl
                from PySide6.QtGui import QDesktopServices
                folder = self.store.project_folder(pid)
                if not folder.is_dir():
                    raise FileNotFoundError("The saved project folder is missing.")
                if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
                    raise RuntimeError("The desktop could not open the project folder.")
            except (ValueError, OSError, RuntimeError, KeyError) as exc:
                alert(exc)

        def issue_action():
            pid = project_id()
            if pid is None:
                return alert("Select a project first.")
            title, ok = QInputDialog.getText(page, "Report Issue", "Bug or issue title:")
            if not ok or not title.strip():
                return
            details, ok = QInputDialog.getMultiLineText(page, "Issue Details", "What failed? What should happen?")
            if not ok or not details.strip():
                return
            try:
                self.store.report_issue(pid, title, details)
                refresh_details()
                QTimer.singleShot(0, lambda pid=pid, subject=title:
                    start_team_meeting(pid, "Issue review: " + subject[:150]))
            except (ValueError, KeyError) as exc:
                alert(exc)

        def issue_transition(close):
            ident = issue_id()
            if ident is None:
                return alert("Select an issue first.")
            try:
                if close:
                    self.store.close_issue(ident)
                else:
                    self.store.assign_issue(ident)
                refresh_details()
            except (ValueError, KeyError) as exc:
                alert(exc)

        def project_transition(reopen):
            pid = project_id()
            if pid is None:
                return alert("Select a project first.")
            if reopen:
                reason, ok = QInputDialog.getText(page, "Reopen App Project", "Why reopen?")
                if not ok or not reason.strip():
                    return
                self.store.reopen_project(pid, reason)
            else:
                if QMessageBox.question(page, "Approve Reviewed Project",
                   "Every task must be accepted and every issue closed. This marks a workflow approved only; "
                   "it does not run, install or publish the app.",
                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                    return
                try:
                    self.store.approve_project(pid)
                except (ValueError, KeyError) as exc:
                    return alert(exc)
            refresh_projects(pid)

        def quick_start_action():
            request = quick_request.toPlainText().strip()
            if not request:
                return alert("Describe what Apollo should build first.")
            if len(request) > 5000:
                return alert("Keep the request under 5000 characters.")
            pid = project_id()
            try:
                if pid is None:
                    title = request.splitlines()[0][:78].strip(". :") or "New Apollo Project"
                    new_data = self.store.add_project(title, request)
                    pid = new_data["project"]["id"]
                    refresh_projects(pid)
                    feed("You: " + request[:500])
                    feed("Manager: Project created with architecture, coding, testing and review stages.")
                else:
                    self.store.request_change(pid, request)
                    refresh_details()
                    feed("You: " + request[:500])
                    feed("Manager: Change request added to the selected project for review.")
                quick_request.clear()
                tabs.setCurrentWidget(flow_tab)
                start_team_meeting(pid, "Kickoff: architecture, dependencies and acceptance tests",
                                   auto_continue=True)
            except (OSError, ValueError, KeyError) as exc:
                alert(exc)

        quick_start.clicked.connect(quick_start_action)
        team_meeting_btn.clicked.connect(manual_team_meeting)
        new_project.clicked.connect(add_project_action)
        refresh_btn.clicked.connect(lambda: refresh_projects())
        project_search.textChanged.connect(lambda _: refresh_projects())
        projects.itemSelectionChanged.connect(refresh_details)
        task_tree.itemSelectionChanged.connect(display_task)
        issue_table.itemSelectionChanged.connect(update_actions)
        add_subtask.clicked.connect(add_subtask_action)
        start_worker.clicked.connect(draft_action)
        accept_task.clicked.connect(lambda: review_action(True))
        rework_task.clicked.connect(lambda: review_action(False))
        retry_task.clicked.connect(retry_action)
        change_request.clicked.connect(request_change_action)
        plan_subtasks.clicked.connect(propose_manager_plan_action)
        starter_btn.clicked.connect(create_starter_action)
        run_checks_btn.clicked.connect(run_static_checks_action)
        fix_checks_btn.clicked.connect(request_check_fix_action)
        show_folder_btn.clicked.connect(open_project_folder_action)
        sandbox_unit.clicked.connect(lambda: run_sandbox_action("unit"))
        sandbox_gui.clicked.connect(lambda: run_sandbox_action("gui"))
        sandbox_fix.clicked.connect(sandbox_fix_action)
        recover_workers.clicked.connect(recover_action)
        report_bug.clicked.connect(issue_action)
        assign_fix.clicked.connect(lambda: issue_transition(False))
        resolve_bug.clicked.connect(lambda: issue_transition(True))
        approve_project.clicked.connect(lambda: project_transition(False))
        reopen_project.clicked.connect(lambda: project_transition(True))
        refresh_projects()
        return page
