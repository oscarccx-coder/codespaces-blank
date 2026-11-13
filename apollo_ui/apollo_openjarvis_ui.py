"""A task-first OpenJarvis page; all long work stays off the Qt event loop."""
import json
from pathlib import Path
import sys
import threading


def build_view(module, parent=None):
    from PySide6.QtCore import QObject, Signal, QProcess, QTimer
    from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QPlainTextEdit, QLineEdit, QComboBox, QCheckBox, QMessageBox)
    class Signals(QObject):
        result = Signal(str)
    page = QWidget(parent); layout = QVBoxLayout(page); signals = Signals(page)
    layout.addWidget(QLabel("OpenJarvis — give Apollo a task"))
    status = QLabel(); status.setWordWrap(True); layout.addWidget(status)
    controls = QHBoxLayout(); setup = QPushButton("Set up / repair"); probe = QPushButton("Check readiness")
    enabled = QCheckBox("Use OpenJarvis in Chat"); enabled.setChecked(module.bridge.settings()["enabled"])
    enabled.toggled.connect(lambda state: module.bridge.configure(enabled=state))
    controls.addWidget(setup); controls.addWidget(probe); controls.addWidget(enabled); layout.addLayout(controls)
    goal = QPlainTextEdit(); goal.setPlaceholderText("Describe the result you want. Apollo will use its tools and save what actually happened.")
    goal.setMaximumHeight(130); layout.addWidget(goal)
    row = QHBoxLayout(); agent = QComboBox()
    agent.addItems(["orchestrator", "native_react", "simple", "deep_research", "operative", "monitor_operative", "native_openhands"])
    agent.setCurrentText(module.bridge.settings()["agent"])
    run = QPushButton("Do task"); stop = QPushButton("Stop"); row.addWidget(agent); row.addWidget(run); row.addWidget(stop)
    layout.addLayout(row)
    actions = QHBoxLayout(); history = QPushButton("Saved runs"); traces = QPushButton("Performance traces")
    skills = QPushButton("Skills"); learn = QPushButton("Suggest routing improvements")
    for button in (history, traces, skills, learn): actions.addWidget(button)
    layout.addLayout(actions)
    output = QPlainTextEdit(); output.setReadOnly(True); output.document().setMaximumBlockCount(1500); layout.addWidget(output, 1)
    signals.result.connect(output.appendPlainText)
    def background(fn):
        def work():
            try: result = fn(); signals.result.emit(json.dumps(result, indent=2, default=str))
            except Exception as exc: signals.result.emit(f"{type(exc).__name__}: {exc}")
        threading.Thread(target=work, daemon=True, name="ApolloOpenJarvisUI").start()
    def refresh():
        value = module.bridge.status()
        status.setText(value["message"] + (" · Task " + value["active_run"] if value["active_run"] else ""))
        run.setEnabled(value["ready"] and value["active_run"] is None)
        setup.setEnabled(value["active_run"] is None and not getattr(page, "installing", False))
    def do_task():
        text = goal.toPlainText().strip()
        if not text: return
        selected = agent.currentText()
        background(lambda: module.bridge.run_task(text, manager=module.manager(), client=module.client(), agent=selected,
            on_event=lambda value: signals.result.emit(json.dumps(value, default=str))))
    run.clicked.connect(do_task); stop.clicked.connect(module.bridge.cancel)
    probe.clicked.connect(lambda: background(lambda: module.run("readiness", {})))
    history.clicked.connect(lambda: background(lambda: module.run("runs", {})))
    traces.clicked.connect(lambda: background(lambda: module.run("trace_summary", {})))
    skills.clicked.connect(lambda: background(lambda: module.run("skills", {})))
    learn.clicked.connect(lambda: background(lambda: module.run("propose_routing", {})))
    def install():
        if QMessageBox.question(page, "Set up OpenJarvis", "Download the pinned source if needed and install its dependencies in a separate environment on Apollo's drive?") != QMessageBox.Yes:
            return
        process = QProcess(page); page.setup_process = process; page.installing = True
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.readyReadStandardOutput.connect(lambda: output.appendPlainText(bytes(process.readAllStandardOutput()).decode("utf-8", "replace")))
        def finished(code, *_args):
            page.installing = False; output.appendPlainText("Setup finished" if code == 0 else "Setup failed; see output above"); refresh()
        process.finished.connect(finished)
        process.errorOccurred.connect(lambda _error: finished(-1))
        import os
        private_python = module.base / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if private_python.is_file(): runner = str(private_python)
        elif not getattr(sys, "frozen", False): runner = sys.executable
        else:
            page.installing = False
            output.appendPlainText("Run Setup/19_SETUP_OPENJARVIS.bat to select a compatible Python interpreter.")
            refresh(); return
        process.start(runner, [str(module.base / "tools/setup_openjarvis.py")])
    setup.clicked.connect(install)
    timer = QTimer(page); timer.setInterval(1000); timer.timeout.connect(refresh); timer.start(); refresh()
    return page
