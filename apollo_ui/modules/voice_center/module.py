class Module:
    def __init__(self, context=None):
        context = context or {}
        self.runtime = context.get("runtime")
        self.base = context.get("base_dir", ".")

    def tools(self):
        return [{
            "name": "voice_center_status",
            "description": "Return the status of Apollo's unified voice modules.",
            "parameters": {"type": "object", "properties": {}},
        }]

    def _record(self, module_id):
        manager = getattr(self.runtime, "_manager", None) if self.runtime else None
        return manager.get_module(module_id) if manager else None

    def _instance(self, module_id):
        record = self._record(module_id)
        return record.get("instance") if record else None

    def run(self, action, arguments):
        if action != "voice_center_status":
            raise KeyError(action)
        tts = self._instance("text_to_speech")
        imprint = self._instance("voice_imprint_trainer")
        active = imprint._active() if imprint is not None and hasattr(imprint, "_active") else {}
        worker = imprint._xtts_worker_status() if imprint is not None and hasattr(imprint, "_xtts_worker_status") else {}
        return {
            "text_to_speech_loaded": tts is not None,
            "voice_imprint_loaded": imprint is not None,
            "active_voice_imprint": active,
            "xtts_worker": worker,
        }

    def self_test(self):
        assert any(t["name"] == "voice_center_status" for t in self.tools())
        return "Unified Voice Center contract passed."

    def build_ui(self, parent=None, ui_context=None):
        from PySide6.QtWidgets import (
            QWidget, QVBoxLayout, QLabel, QTabWidget, QMessageBox,
            QPushButton, QHBoxLayout
        )

        page = QWidget(parent)
        root = QVBoxLayout(page)
        root.setSpacing(10)

        title = QLabel("Voice Center")
        title.setStyleSheet("font-size:26px;font-weight:800;color:#e7fffb;")
        root.addWidget(title)
        subtitle = QLabel(
            "One place for Apollo's voice selection, fallback speech controls, Voice Imprint profiles, "
            "XTTS tuning and performance. Neural Voice Imprint takes priority when activated; Windows speech remains the fallback."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color:#8fcfc3;")
        root.addWidget(subtitle)

        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        def add_module_tab(module_id, label):
            instance = self._instance(module_id)
            if instance is None or not hasattr(instance, "build_ui"):
                placeholder = QWidget()
                layout = QVBoxLayout(placeholder)
                msg = QLabel(f"{label} module is unavailable or disabled.")
                msg.setWordWrap(True)
                layout.addWidget(msg)
                layout.addStretch(1)
                tabs.addTab(placeholder, label)
                return
            try:
                child = instance.build_ui(parent=tabs, ui_context=ui_context or {})
                tabs.addTab(child, label)
            except Exception as exc:
                placeholder = QWidget()
                layout = QVBoxLayout(placeholder)
                msg = QLabel(f"Could not build {label}: {type(exc).__name__}: {exc}")
                msg.setWordWrap(True)
                layout.addWidget(msg)
                layout.addStretch(1)
                tabs.addTab(placeholder, label)

        add_module_tab("text_to_speech", "Voice Control & Selection")
        add_module_tab("voice_imprint_trainer", "Voice Imprint Lab")

        perf = QWidget()
        perf_layout = QVBoxLayout(perf)
        perf_status = QLabel()
        perf_status.setWordWrap(True)
        refresh = QPushButton("Refresh Voice Performance Status")
        unload = QPushButton("Unload XTTS / Free GPU Memory")
        row = QHBoxLayout()
        row.addWidget(refresh)
        row.addWidget(unload)
        row.addStretch(1)
        perf_layout.addWidget(perf_status)
        perf_layout.addLayout(row)
        perf_layout.addStretch(1)
        tabs.addTab(perf, "Performance")

        def refresh_perf():
            try:
                info = self.run("voice_center_status", {})
                worker = info.get("xtts_worker", {})
                active = info.get("active_voice_imprint", {})
                perf_status.setText(
                    "Voice Imprint: " + (str(active.get("profile_name") or active.get("profile_id")) if active.get("enabled") else "OFF / Windows fallback")
                    + "\nXTTS isolation: " + ("ON" if worker.get("process_isolation", True) else "OFF")
                    + "\nXTTS worker: " + (f"running (PID {worker.get('pid')})" if worker.get("running") else "stopped / cold")
                    + "\nWorker log: " + str(worker.get("log") or "")
                    + "\n\nOptimization policy:\n"
                    + "• PyTorch/XTTS model never needs to load into the Qt GUI process.\n"
                    + "• The worker runs below normal Windows priority with limited CPU threads.\n"
                    + "• Speaker conditioning is cached inside the worker.\n"
                    + "• Long replies are split below XTTS's token limit without spaCy.\n"
                    + "• Speech requests are coalesced while the neural engine is busy."
                )
            except Exception as exc:
                perf_status.setText(f"Could not read voice performance status: {type(exc).__name__}: {exc}")

        def unload_worker():
            imprint = self._instance("voice_imprint_trainer")
            if imprint is None:
                return
            try:
                imprint.run("unload_xtts_worker", {})
                refresh_perf()
            except Exception as exc:
                QMessageBox.warning(page, "Voice Center", str(exc))

        refresh.clicked.connect(refresh_perf)
        unload.clicked.connect(unload_worker)
        tabs.currentChanged.connect(lambda _index: refresh_perf())
        refresh_perf()
        return page
