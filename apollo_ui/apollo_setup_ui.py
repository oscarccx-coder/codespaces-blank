"""Apollo's first-run Setup Centre. Heavy checks run in worker threads."""
from pathlib import Path
import json
import threading
from datetime import datetime, timezone

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QWidget,
    QPushButton, QComboBox, QPlainTextEdit, QFileDialog, QMessageBox
)

from apollo_setup_core import PROFILES, read_profile, save_profile, system_checks
from apollo_backup import make_backup, inspect_backup


def completed_path(base):
    return Path(base) / "storage" / "state" / "setup_completed.json"


def show_setup(parent, base, first_run=False):
    base = Path(base).resolve()
    dialog = QDialog(parent)
    dialog.setWindowTitle("Apollo Setup & Recovery")
    dialog.resize(760, 560)
    dialog.setMinimumSize(530, 420)
    layout = QVBoxLayout(dialog)
    header = QLabel("Welcome to Apollo" if first_run else "Apollo Setup & Recovery")
    header.setStyleSheet("font-size:23px;font-weight:700;")
    layout.addWidget(header)
    caption = QLabel(
        "Check your device and voice, keep a backup, and change setup preferences. "
        "Nothing is downloaded or repaired without your action."
    )
    caption.setWordWrap(True)
    layout.addWidget(caption)
    tabs = QTabWidget()
    layout.addWidget(tabs, 1)

    device_page = QWidget()
    dv = QVBoxLayout(device_page)
    dv.addWidget(QLabel("Which device is running Apollo?"))
    profiles = QComboBox()
    for key, value in PROFILES.items():
        profiles.addItem(value["title"], key)
    profiles.setCurrentIndex(max(0, profiles.findData(read_profile(base))))
    profile_explain = QLabel()
    profile_explain.setWordWrap(True)
    def show_recommendation(_=None):
        record = PROFILES[profiles.currentData()]
        profile_explain.setText(
            record["description"] + "\nSuggested model: " + record["model_hint"] +
            "\nThis saves setup preferences only. It does not silently download models or reconfigure Ollama."
        )
    profiles.currentIndexChanged.connect(show_recommendation)
    show_recommendation()
    save_choice = QPushButton("Save Device Preference")
    def apply_profile():
        try:
            save_profile(base, profiles.currentData())
            QMessageBox.information(dialog, "Device preference", "Saved. This does not change your installed AI model.")
        except Exception as exc:
            QMessageBox.warning(dialog, "Device preference", str(exc))
    save_choice.clicked.connect(apply_profile)
    dv.addWidget(profiles)
    dv.addWidget(profile_explain)
    dv.addWidget(save_choice)
    dv.addStretch()
    tabs.addTab(device_page, "Device")

    health_page = QWidget()
    hv = QVBoxLayout(health_page)
    buttons = QHBoxLayout()
    scan = QPushButton("Check Apollo")
    deep = QPushButton("Check XTTS Imports (30s timeout)")
    buttons.addWidget(scan)
    buttons.addWidget(deep)
    hv.addLayout(buttons)
    checks_text = QPlainTextEdit()
    checks_text.setReadOnly(True)
    checks_text.setPlainText("Select Check Apollo for Ollama, Python, models and XTTS status.")
    hv.addWidget(checks_text, 1)
    tabs.addTab(health_page, "Diagnostics")

    backup_page = QWidget()
    bv = QVBoxLayout(backup_page)
    notice = QLabel(
        "Backups include saved memory, SQLite databases, research, voice profiles and "
        "workspace projects. They DO NOT include AI model weights, Python packages or "
        "update signing keys. Backups are NOT encrypted: store them privately.\n\n"
        "Restore is intentionally a separate operation while Apollo is closed. "
        "Use Setup/07_RESTORE_BACKUP.bat to preview and confirm an archive."
    )
    notice.setWordWrap(True)
    bv.addWidget(notice)
    backup_btn = QPushButton("Create a Local Backup")
    inspect_btn = QPushButton("Inspect Existing Backup")
    bv.addWidget(backup_btn)
    bv.addWidget(inspect_btn)
    backup_status = QPlainTextEdit()
    backup_status.setReadOnly(True)
    backup_status.setPlainText("No backup operation running.")
    bv.addWidget(backup_status, 1)
    tabs.addTab(backup_page, "Backup & Restore")

    class JobSignals(QObject):
        success = Signal(str, object)
        failure = Signal(str, str)
    signals = JobSignals(dialog)
    busy = {"value": False}

    def begin(kind, runner):
        if busy["value"]:
            return
        busy["value"] = True
        for btn in (scan, deep, backup_btn):
            btn.setEnabled(False)
        if kind == "backup":
            backup_status.setPlainText("Backing up local Apollo files... Do not close Apollo during this step.")
        else:
            checks_text.setPlainText("Inspecting local Apollo setup and XTTS health...")
        def worker():
            try:
                signals.success.emit(kind, runner())
            except Exception as exc:
                signals.failure.emit(kind, f"{type(exc).__name__}: {exc}")
        threading.Thread(target=worker, daemon=True, name="ApolloSetup-" + kind).start()

    def complete(kind, result):
        busy["value"] = False
        for btn in (scan, deep, backup_btn):
            btn.setEnabled(True)
        if kind == "backup":
            backup_status.setPlainText(json.dumps(result, indent=2))
        else:
            checks_text.setPlainText(json.dumps(result, indent=2, default=str))
    signals.success.connect(complete)
    signals.failure.connect(lambda kind, message: complete(kind, {"error": message}))
    scan.clicked.connect(lambda: (tabs.setCurrentWidget(health_page), begin("diagnostics", lambda: system_checks(base))))
    deep.clicked.connect(lambda: begin("diagnostics", lambda: system_checks(base, deep_voice=True)))

    def backup_now():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        initial = str(base / "storage" / "backups" / "exports" / ("Apollo-" + stamp + ".zip"))
        filename, _ = QFileDialog.getSaveFileName(dialog, "Save Apollo data backup", initial, "ZIP Archives (*.zip)")
        if filename:
            begin("backup", lambda: make_backup(base, filename))
    backup_btn.clicked.connect(backup_now)

    def inspect():
        filename, _ = QFileDialog.getOpenFileName(dialog, "Inspect an Apollo backup", "", "ZIP Archives (*.zip)")
        if filename:
            try:
                summary = inspect_backup(filename)
                backup_status.setPlainText(json.dumps({k: v for k, v in summary.items() if k != "entries"}, indent=2))
            except Exception as exc:
                QMessageBox.warning(dialog, "Backup inspection failed", str(exc))
    inspect_btn.clicked.connect(inspect)

    footer = QHBoxLayout()
    finish = QPushButton("Finish Setup" if first_run else "Close")
    footer.addStretch()
    footer.addWidget(finish)
    layout.addLayout(footer)
    def end():
        if busy["value"]:
            QMessageBox.warning(dialog, "Operation running", "Finish the current diagnostic or backup first.")
            return
        if first_run:
            flag = completed_path(base)
            flag.parent.mkdir(parents=True, exist_ok=True)
            flag.write_text(json.dumps({"completed_at": datetime.now(timezone.utc).isoformat()}) + "\n", encoding="utf-8")
        dialog.accept()
    finish.clicked.connect(end)
    dialog.show()
    return dialog


def maybe_show_first_run(parent, base):
    if completed_path(base).is_file():
        return None
    return show_setup(parent, base, first_run=True)
