"""Human-controlled Project Studio frontend for Apollo.

Workers generate drafts in a bounded background thread; only the owner can
accept tasks, close issues or approve projects. No draft is ever executed.
"""
from pathlib import Path

from apollo_project_studio import StudioStore
from apollo_project_workers import draft_for_task, model_from_config


class Module:
    def __init__(self, context=None):
        context = context or {}
        self.base = Path(context.get("base_dir", ".")).resolve()
        self.store = StudioStore(self.base, memory=bool(context.get("validation")))

    def tools(self):
        # Read-only tools; creating projects, drafting, changes and approvals
        # are exclusively explicit user actions through the UI.
        integer = {"type": "integer"}
        return [
            {"name": "list_app_projects", "description": "Read user-created app development projects.",
             "parameters": {"type": "object", "properties": {}}},
            {"name": "app_project_status", "description": "Read tasks, subtasks and issues for one project.",
             "parameters": {"type": "object", "properties": {"project_id": integer}, "required": ["project_id"]}},
        ]

    def run(self, action, arguments):
        args = arguments or {}
        if action == "list_app_projects":
            return {"projects": self.store.list_projects()}
        if action == "app_project_status":
            return self.store.details(args["project_id"])
        raise KeyError(action)

    def self_test(self):
        if self.store.db_path == ":memory:":
            data = self.store.add_project("Check", "Synthetic, local validation")
            assert len(data["tasks"]) == 5
            assert all(t["state"] == "todo" for t in data["tasks"])
        return "Project Studio stores staged local projects. AI tools are read-only."

    def close(self):
        self.store.close()

    def build_ui(self, parent=None, ui_context=None):
        from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal
        from PySide6.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
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

        page = QWidget(parent)
        outer = QVBoxLayout(page)
        heading = QLabel("Project Studio")
        heading.setStyleSheet("font-size:24px;font-weight:700;")
        outer.addWidget(heading)
        summary = QLabel(
            "Build apps with specialist AI drafts. Create a project, divide it into tasks, "
            "assign a worker, review the result and reopen bugs. "
            "No generated code executes, installs or publishes without your approval."
        )
        summary.setWordWrap(True)
        outer.addWidget(summary)

        split = QSplitter(Qt.Horizontal)
        outer.addWidget(split, 1)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Your app projects"))
        projects = QListWidget()
        left_layout.addWidget(projects, 1)
        new_project = QPushButton("+ New App Project")
        refresh_btn = QPushButton("Refresh")
        left_layout.addWidget(new_project)
        left_layout.addWidget(refresh_btn)
        split.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        project_heading = QLabel("Select or create a project")
        project_heading.setStyleSheet("font-size:17px;font-weight:600;")
        right_layout.addWidget(project_heading)
        path_label = QLabel("Projects are saved in workspace/app_development/")
        path_label.setWordWrap(True)
        right_layout.addWidget(path_label)
        tabs = QTabWidget()
        right_layout.addWidget(tabs, 1)
        split.addWidget(right)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 4)

        tasks_tab = QWidget()
        tasks_layout = QVBoxLayout(tasks_tab)
        task_buttons = QHBoxLayout()
        add_subtask = QPushButton("+ Subtask")
        start_worker = QPushButton("Draft with Local AI")
        accept_task = QPushButton("Accept Draft")
        rework_task = QPushButton("Request Changes")
        retry_task = QPushButton("Retry / Reopen")
        for b in (add_subtask, start_worker, accept_task, rework_task, retry_task):
            task_buttons.addWidget(b)
        tasks_layout.addLayout(task_buttons)
        task_tree = QTreeWidget()
        task_tree.setHeaderLabels(["Task", "Worker", "Status", "Iteration"])
        task_tree.setColumnWidth(0, 270)
        tasks_layout.addWidget(task_tree, 2)
        result_text = QPlainTextEdit()
        result_text.setReadOnly(True)
        result_text.setPlaceholderText("Select a task to see its instructions, draft and review feedback.")
        tasks_layout.addWidget(result_text, 1)
        tabs.addTab(tasks_tab, "Tasks & Workers")

        bugs_tab = QWidget()
        bugs_layout = QVBoxLayout(bugs_tab)
        bug_buttons = QHBoxLayout()
        report_bug = QPushButton("+ Report Issue")
        assign_fix = QPushButton("Create Fix Task")
        resolve_bug = QPushButton("Close Reviewed Issue")
        for b in (report_bug, assign_fix, resolve_bug):
            bug_buttons.addWidget(b)
        bugs_layout.addLayout(bug_buttons)
        issue_table = QTableWidget(0, 4)
        issue_table.setHorizontalHeaderLabels(["ID", "Issue", "Status", "Fix task"])
        issue_table.setSelectionBehavior(QTableWidget.SelectRows)
        issue_table.setEditTriggers(QTableWidget.NoEditTriggers)
        issue_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        bugs_layout.addWidget(issue_table)
        tabs.addTab(bugs_tab, "Issues & Rework")

        history_tab = QWidget()
        history_layout = QVBoxLayout(history_tab)
        timeline = QPlainTextEdit()
        timeline.setReadOnly(True)
        history_layout.addWidget(timeline)
        tabs.addTab(history_tab, "Activity")

        footer = QHBoxLayout()
        approve_project = QPushButton("Approve Reviewed Project")
        reopen_project = QPushButton("Reopen Project")
        recover_workers = QPushButton("Recover Interrupted Jobs")
        footer.addWidget(approve_project)
        footer.addWidget(reopen_project)
        footer.addWidget(recover_workers)
        right_layout.addLayout(footer)

        active_jobs = []

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
            prior = select_id if select_id is not None else project_id()
            projects.blockSignals(True)
            projects.clear()
            chosen = None
            for item in self.store.list_projects():
                row = QListWidgetItem(f"#{item['id']}  {item['title']}  [{item['state']}]")
                row.setData(Qt.UserRole, item["id"])
                projects.addItem(row)
                if item["id"] == prior:
                    chosen = row
            if chosen is not None:
                projects.setCurrentItem(chosen)
            projects.blockSignals(False)
            refresh_details()

        def refresh_details():
            pid = project_id()
            task_tree.clear()
            issue_table.setRowCount(0)
            timeline.clear()
            if pid is None:
                project_heading.setText("Select or create a project")
                path_label.setText("Projects are stored locally.")
                result_text.clear()
                return
            state = self.store.details(pid)
            p = state["project"]
            project_heading.setText(f"{p['title']}  •  {p['state']}")
            path_label.setText("Saved in workspace/app_development/" + p["folder"])
            nodes = {}
            for task in state["tasks"]:
                node = QTreeWidgetItem([task["title"], task["role"], task["state"], str(task["iteration"])])
                node.setData(0, Qt.UserRole, task["id"])
                nodes[task["id"]] = node
                parent = nodes.get(task["parent_id"]) if task["parent_id"] else None
                if parent is not None:
                    parent.addChild(node)
                else:
                    task_tree.addTopLevelItem(node)
            task_tree.expandAll()
            issue_table.setRowCount(len(state["issues"]))
            for i, issue in enumerate(state["issues"]):
                for j, value in enumerate((str(issue["id"]), issue["title"], issue["state"],
                                           str(issue["assigned_task"] or "Unassigned"))):
                    issue_table.setItem(i, j, QTableWidgetItem(value))
            timeline.setPlainText("\n".join(
                f"{e['created_at']}  {e['kind']}  {e['detail']}"
                for e in self.store.audit(pid)
            ))
            result_text.clear()

        def display_task():
            tid = task_id()
            if tid is None:
                return
            task = self.store._task(tid)
            result_text.setPlainText(
                f"ROLE: {task['role']}\nSTATUS: {task['state']}\n\n"
                f"INSTRUCTIONS\n{task['brief']}\n\n"
                f"DRAFT (NOT EXECUTED)\n{task['result'] or 'No draft yet'}\n\n"
                f"REVIEW / ISSUES\n{task['feedback'] or '(none)'}\n\n"
                f"EVIDENCE\n{task['evidence'] or '(none)'}"
            )

        def add_project_action():
            title, ok = QInputDialog.getText(page, "New App Project", "Project name:")
            if not ok or not title.strip():
                return
            brief, ok = QInputDialog.getMultiLineText(page, "Project Brief", "What should this app do?")
            if not ok or not brief.strip():
                return
            try:
                data = self.store.add_project(title, brief)
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

        def finished_job(tid, draft, error):
            try:
                if error:
                    self.store.fail_task(tid, error[:2300])
                    alert("Worker failed safely: " + error[:350])
                else:
                    self.store.submit_task(tid, draft, "Local Ollama draft only. User must review and run real tests.")
            except (ValueError, KeyError) as exc:
                alert(exc)
            finally:
                refresh_details()
                active_jobs[:] = [x for x in active_jobs if x[0] != tid]

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
        refresh_btn.clicked.connect(refresh_projects)
        projects.itemSelectionChanged.connect(refresh_details)
        task_tree.itemSelectionChanged.connect(display_task)
        add_subtask.clicked.connect(add_subtask_action)
        start_worker.clicked.connect(draft_action)
        accept_task.clicked.connect(lambda: review_action(True))
        rework_task.clicked.connect(lambda: review_action(False))
        retry_task.clicked.connect(retry_action)
        recover_workers.clicked.connect(recover_action)
        report_bug.clicked.connect(issue_action)
        assign_fix.clicked.connect(lambda: issue_transition(False))
        resolve_bug.clicked.connect(lambda: issue_transition(True))
        approve_project.clicked.connect(lambda: project_transition(False))
        reopen_project.clicked.connect(lambda: project_transition(True))
        refresh_projects()
        return page
