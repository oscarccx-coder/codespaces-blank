"""Human-controlled Apollo Foundry frontend for Phase 1 coding.

Workers generate drafts in a bounded background thread; only the owner can
accept tasks, close issues or approve projects. No draft is ever executed.
"""
import json
from pathlib import Path

from apollo_project_studio import StudioStore
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
        from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal
        from PySide6.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGridLayout,
            QLineEdit, QProgressBar, QGroupBox,
            QListWidget, QListWidgetItem, QSplitter, QTabWidget,
            QTreeWidget, QTreeWidgetItem, QPlainTextEdit, QMessageBox,
            QInputDialog, QTableWidget, QTableWidgetItem, QHeaderView,
        )

        class WorkerSignal(QObject):
            finished = Signal(int, str, str)

        class DraftJob(QRunnable):
            def __init__(self, item, state, model, signals):
                super().__init__()
                self.item = item
                self.state = state
                self.model = model
                self.signals = signals

            def run(self):
                try:
                    text = draft_for_task(self.state, self.item, self.model)
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
        tabs = QTabWidget()
        right_layout.addWidget(tabs, 1)
        split.addWidget(right)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 4)

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
        task_tree.setAlternatingRowColors(True)
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
        tabs.addTab(sandbox_tab, "4. Sandbox")

        history_tab = QWidget()
        history_layout = QVBoxLayout(history_tab)
        timeline = QPlainTextEdit()
        timeline.setReadOnly(True)
        history_layout.addWidget(timeline)
        tabs.addTab(history_tab, "History")
        tabs.tabBar().moveTab(tabs.indexOf(checks_tab), 1)
        tabs.tabBar().moveTab(tabs.indexOf(bugs_tab), 2)

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
                                sandbox_unit, sandbox_gui, sandbox_fix):
                    control.setEnabled(False)
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
                for e in self.store.audit(pid)
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
                alert("Manager proposal could not be produced: " + error[:500])
                update_actions()
                return
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

        def finished_job(tid, draft, error):
            try:
                if error:
                    self.store.fail_task(tid, error[:2300])
                    alert("Worker could not finish. Your project is safe.\n\n" + error[:900])
                else:
                    self.store.submit_task(tid, draft, "Local Ollama draft only. User must review and run real tests.")
            except (ValueError, KeyError) as exc:
                alert(exc)
            finally:
                # The finished job must leave the active queue before UI state
                # is derived, otherwise subsequent worker buttons stay disabled.
                active_jobs[:] = [x for x in active_jobs if x[0] != tid]
                refresh_details()

        def draft_action():
            tid, pid = task_id(), project_id()
            if tid is None or pid is None:
                return alert("Select a task before drafting.")
            try:
                state = self.store.details(pid)
                model = model_from_config(self.base)
                self.store.start_task(tid)
                state = self.store.details(pid)
                signal = WorkerSignal()
                signal.finished.connect(finished_job)
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
