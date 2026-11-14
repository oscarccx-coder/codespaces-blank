"""Apollo-native VoiceStudio controls. All heavy actions stay off the Qt UI thread.

VoiceStudio is a separately licensed local backend: Apollo controls only its
own explicitly launched process and communicates on loopback. No cloud setup,
model download or voice cloning happens without owner interaction.
"""
from __future__ import annotations

from pathlib import Path
import threading


def build_view(base, runtime=None, parent=None):
    from PySide6.QtCore import QObject, Signal
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
        QLineEdit, QFileDialog, QCheckBox, QPlainTextEdit, QMessageBox
    )
    from apollo_capabilities import service
    from apollo_voicestudio import probe, list_voices, create_clone
    from apollo_voicestudio_runtime import start_backend, stop_backend, backend_status, prepare_backend, find_downloaded_checkout

    svc = service(base, runtime)
    conf = svc.settings()
    panel = QWidget(parent)
    layout = QVBoxLayout(panel)
    intro = QLabel(
        "VoiceStudio is Apollo's local speech/voice-cloning engine. "
        "It runs in a separate environment so it never replaces Apollo's Python, Ollama or XTTS files."
    )
    intro.setWordWrap(True)
    layout.addWidget(intro)

    url = QLineEdit(conf["voicestudio_url"])
    url.setPlaceholderText("http://127.0.0.1:3900")
    layout.addWidget(QLabel("VoiceStudio local backend address"))
    layout.addWidget(url)
    initial_path = find_downloaded_checkout(base, conf.get("voicestudio_checkout", ""))
    source = QLineEdit(initial_path or conf.get("voicestudio_checkout", ""))
    source.setPlaceholderText("e.g. F:\\Apollo\\VoiceStudio")
    browse = QPushButton("Browse…")
    auto_find = QPushButton("Find downloaded files")
    source_row = QHBoxLayout()
    source_row.addWidget(source, 1)
    source_row.addWidget(auto_find)
    source_row.addWidget(browse)
    layout.addLayout(source_row)

    setup = QPushButton("Prepare VoiceStudio runtime (Bun / uv)")
    start = QPushButton("Start VoiceStudio backend (prepared source)")
    stop_backend_btn = QPushButton("Stop Apollo-owned VoiceStudio backend")
    connect = QPushButton("Test connection")
    lifecycle = QHBoxLayout()
    for btn in (setup, start, stop_backend_btn, connect):
        lifecycle.addWidget(btn)
    layout.addLayout(lifecycle)

    selection = QHBoxLayout()
    layout.addWidget(QLabel("VoiceStudio voice profile and speech engine"))
    voices = QComboBox()
    models = QComboBox()
    models.addItem("Active VoiceStudio engine", "tts-1")
    voices.addItem("Default engine voice", "default")
    selection.addWidget(voices, 2)
    selection.addWidget(models, 1)
    layout.addLayout(selection)
    use = QPushButton("Use selected voice for Apollo replies")
    refresh = QPushButton("Load VoiceStudio voices & engines")
    preview = QPushButton("Speak a test sentence")
    actions = QHBoxLayout()
    for btn in (refresh, use, preview):
        actions.addWidget(btn)
    layout.addLayout(actions)

    dictation = QCheckBox("Also use VoiceStudio for Apollo microphone transcription")
    dictation.setChecked(conf.get("transcription") == "voicestudio")
    layout.addWidget(dictation)
    layout.addWidget(QLabel("Create a reusable voice clone (authorized recordings only)"))
    clone_name = QLineEdit()
    clone_name.setPlaceholderText("Name for your new voice profile")
    clone_path = QLineEdit()
    clone_path.setReadOnly(True)
    choose_audio = QPushButton("Choose reference audio")
    recording = QHBoxLayout()
    recording.addWidget(clone_path, 1)
    recording.addWidget(choose_audio)
    layout.addWidget(clone_name)
    layout.addLayout(recording)
    ref_text = QLineEdit()
    ref_text.setPlaceholderText("Optional transcript of the reference recording")
    layout.addWidget(ref_text)
    consent = QCheckBox("I own this voice or have the speaker's permission to clone it")
    layout.addWidget(consent)
    clone = QPushButton("Create VoiceStudio voice profile")
    layout.addWidget(clone)

    info = QLabel("VoiceStudio connection not checked.")
    info.setWordWrap(True)
    layout.addWidget(info)
    output = QPlainTextEdit()
    output.setReadOnly(True)
    output.setMinimumHeight(160)
    layout.addWidget(output, 1)

    class Signals(QObject):
        finished = Signal(str, object)
        failed = Signal(str, str)
    signals = Signals(panel)
    busy = {"value": False}
    operation_buttons = (setup, start, stop_backend_btn, connect, refresh, use, preview, clone)

    def report(message):
        output.appendPlainText(str(message))
        info.setText(str(message))

    def work(action, callable_):
        if busy["value"]:
            return
        busy["value"] = True
        for control in operation_buttons:
            control.setEnabled(False)
        report(action + "…")
        def execute():
            try:
                signals.finished.emit(action, callable_())
            except Exception as exc:
                signals.failed.emit(action, f"{type(exc).__name__}: {exc}")
        threading.Thread(target=execute, name="ApolloVoiceStudioUI", daemon=True).start()

    def settings_now():
        # UI access only on the Qt thread.
        return svc.configure(voicestudio_url=url.text().strip(),
                             voicestudio_checkout=source.text().strip(),
                             voicestudio_voice=str(voices.currentData() or "default"),
                             voicestudio_model=str(models.currentData() or "tts-1"))

    def configure_voice():
        try:
            svc.configure(voicestudio_url=url.text().strip(),
                          voicestudio_checkout=source.text().strip(),
                          voicestudio_voice=str(voices.currentData() or "default"),
                          voicestudio_model=str(models.currentData() or "tts-1"),
                          voice="voicestudio",
                          transcription="voicestudio" if dictation.isChecked() else "existing")
            report("VoiceStudio is selected for Apollo's spoken replies. XTTS remains available but is not loaded for these requests.")
        except Exception as exc:
            report(f"Voice selection failed: {exc}")

    def choose_folder():
        folder = QFileDialog.getExistingDirectory(panel, "Choose VoiceStudio Git folder", source.text())
        if folder:
            source.setText(folder)

    def find_folder():
        folder = find_downloaded_checkout(base, source.text())
        if folder:
            source.setText(folder)
            report("Found your existing VoiceStudio source: " + folder +
                   ". Nothing was downloaded or copied.")
        else:
            report("No matching VoiceStudio folder found beside Apollo. "
                   "Extract it to F:\\Apollo\\VoiceStudio, or use Browse to point to its package.json folder.")

    def choose_file():
        file, _ = QFileDialog.getOpenFileName(panel, "Choose authorized reference audio", "",
                                            "Audio files (*.wav *.mp3 *.flac *.ogg *.m4a)")
        if file:
            clone_path.setText(file)

    def load_catalogue():
        address = url.text().strip()
        work("Loading voices", lambda: list_voices(address))

    def begin_clone():
        if not consent.isChecked():
            QMessageBox.warning(panel, "Voice permission required",
                                "Confirm that you own this voice or have the speaker's permission.")
            return
        audio, name = clone_path.text(), clone_name.text().strip()
        address, transcript = url.text().strip(), ref_text.text()
        work("Creating profile", lambda: create_clone(address, audio, name,
             transcript=transcript, consent_confirmed=True))

    def test_tts():
        configure_voice()
        if svc.settings()["voice"] != "voicestudio":
            return
        manager = getattr(runtime, "_manager", None)
        tts = manager.get_module("text_to_speech") if manager else None
        instance = tts.get("instance") if tts else None
        if instance is None:
            report("Enable Apollo's Text to Speech module to preview playback.")
            return
        try:
            result = instance.run("speak_text", {
                "text": "VoiceStudio online. Apollo voice systems are ready.",
                "use_voice_imprint": False,
            })
            report("Test speech queued: " + str(result))
        except Exception as exc:
            report(f"Speech test failed: {exc}")

    def done(action, result):
        busy["value"] = False
        for control in operation_buttons:
            control.setEnabled(True)
        if action == "Loading voices":
            entries = result.get("voices", [])
            engines = result.get("engines", [])
            saved_voice = svc.settings()["voicestudio_voice"]
            saved_model = svc.settings()["voicestudio_model"]
            voices.clear()
            voices.addItem("Default engine voice", "default")
            for item in entries:
                if not isinstance(item, dict):
                    continue
                ident = item.get("voice_id") or item.get("id")
                if ident and len(str(ident)) <= 200:
                    label = str(item.get("name") or ident)
                    voices.addItem(label[:130], str(ident))
            models.clear()
            models.addItem("Active VoiceStudio engine", "tts-1")
            for item in engines:
                if not isinstance(item, dict):
                    continue
                ident = item.get("engine_id") or item.get("id")
                if ident and len(str(ident)) <= 100:
                    models.addItem(str(item.get("name") or ident)[:120], str(ident))
            ix = voices.findData(saved_voice)
            if ix >= 0:
                voices.setCurrentIndex(ix)
            ix = models.findData(saved_model)
            if ix >= 0:
                models.setCurrentIndex(ix)
            report(f"VoiceStudio: {len(entries)} available voices, {len(engines)} engine entries.")
        elif action == "Creating profile":
            report("Voice profile created: " + str(result.get("name", "")) +
                   " (" + str(result.get("id", "")) + "). Refresh to select it.")
            consent.setChecked(False)
        elif action == "Testing connection":
            report("VoiceStudio online: " + str(result))
        elif action == "Preparing backend":
            report("VoiceStudio runtime setup: " + str(result))
        elif action == "Starting backend":
            report("VoiceStudio backend launch: " + str(result))
        elif action == "Stopping backend":
            report("VoiceStudio backend stop: " + str(result))
        else:
            report(action + ": " + str(result))

    def failed(action, message):
        busy["value"] = False
        for control in operation_buttons:
            control.setEnabled(True)
        report(action + " failed: " + message)

    signals.finished.connect(done)
    signals.failed.connect(failed)
    browse.clicked.connect(choose_folder)
    auto_find.clicked.connect(find_folder)
    choose_audio.clicked.connect(choose_file)
    refresh.clicked.connect(load_catalogue)
    def test_connection():
        address = url.text().strip()
        work("Testing connection", lambda: probe(address))
    def launch_checkout():
        folder = source.text().strip()
        work("Starting backend", lambda: start_backend(folder, Path(base) / "storage" / "logs"))
    connect.clicked.connect(test_connection)
    def install_checkout():
        folder = source.text().strip()
        if QMessageBox.question(
            panel, "Install third-party runtime",
            "Run VoiceStudio's own Bun and Python setup scripts in the chosen folder?\n"
            "These scripts can download several gigabytes of dependencies and execute "
            "third-party code on this PC. Apollo's Python environment will not be changed.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        work("Preparing backend", lambda: prepare_backend(folder, Path(base) / "storage" / "logs"))
    setup.clicked.connect(install_checkout)
    start.clicked.connect(launch_checkout)
    stop_backend_btn.clicked.connect(lambda: work("Stopping backend", stop_backend))
    use.clicked.connect(configure_voice)
    preview.clicked.connect(test_tts)
    clone.clicked.connect(begin_clone)
    report(("Detected VoiceStudio at " + initial_path + ". " if initial_path else
           "Place the extracted VoiceStudio Git files beside Apollo, e.g. F:\\Apollo\\VoiceStudio. ") +
           "Apollo-owned backend: " + str(backend_status()) +
           ". No files will be copied into Apollo's Git repository.")
    return panel
