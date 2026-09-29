from pathlib import Path
from apollo_update import UpdateService


class Module:
    def __init__(self, context=None):
        self.context = context or {}
        self.base = Path(self.context.get("base_dir", ".")).resolve()
        self.service = UpdateService(self.base)

    def tools(self):
        return [
            {"name":"update_status","description":"Return this Apollo device update configuration/status.","parameters":{"type":"object","properties":{}}},
            {"name":"configure_update_source","description":"Configure Apollo update server/channel/device name.","parameters":{"type":"object","properties":{"server_url":{"type":"string"},"channel":{"type":"string"},"auto_check":{"type":"boolean"},"device_name":{"type":"string"}}}},
            {"name":"check_for_updates","description":"Check the configured signed Apollo release channel.","parameters":{"type":"object","properties":{}}},
            {"name":"stage_update","description":"Download, verify and stage the latest signed Apollo update.","parameters":{"type":"object","properties":{}}},
            {"name":"import_update_public_key","description":"Trust an Apollo release public key PEM file.","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}},
            {"name":"install_staged_update","description":"Launch the external updater for a staged signed release. Apollo must close for core files to restart cleanly.","parameters":{"type":"object","properties":{"version":{"type":"string"},"restart":{"type":"boolean"}}}},
        ]

    def run(self, action, arguments):
        arguments = arguments or {}
        if action == "update_status":
            return self.service.status()
        if action == "configure_update_source":
            return self.service.configure(
                server_url=arguments.get("server_url"),
                channel=arguments.get("channel"),
                auto_check=arguments.get("auto_check") if "auto_check" in arguments else None,
                device_name=arguments.get("device_name"),
            )
        if action == "check_for_updates":
            return self.service.check_for_updates()
        if action == "stage_update":
            return self.service.stage_update()
        if action == "import_update_public_key":
            return self.service.import_trusted_key(arguments.get("path"))
        if action == "install_staged_update":
            return self.service.launch_installer(arguments.get("version") or None, restart=bool(arguments.get("restart", True)))
        raise KeyError(action)

    def self_test(self):
        status = self.service.status()
        return bool(status.get("device") and status.get("settings"))

    def build_ui(self, parent=None, ui_context=None):
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
            QPushButton, QCheckBox, QPlainTextEdit, QFileDialog, QMessageBox
        )

        page = QWidget(parent)
        root = QVBoxLayout(page)
        root.setSpacing(10)
        title = QLabel("Apollo Update Manager")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        root.addWidget(title)

        status_label = QLabel("")
        status_label.setWordWrap(True)
        root.addWidget(status_label)

        server = QLineEdit()
        server.setPlaceholderText("http://192.168.1.100:8765")
        channel = QComboBox()
        channel.addItems(["development", "beta", "stable", "pinned"])
        auto_check = QCheckBox("Check automatically at startup (notification only)")

        row = QHBoxLayout()
        row.addWidget(QLabel("Server"))
        row.addWidget(server, 1)
        root.addLayout(row)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Channel"))
        row2.addWidget(channel)
        row2.addWidget(auto_check)
        row2.addStretch(1)
        root.addLayout(row2)

        buttons = QHBoxLayout()
        save = QPushButton("Save Settings")
        check = QPushButton("Check")
        stage = QPushButton("Stage Update")
        trust = QPushButton("Import Public Key")
        install = QPushButton("Install + Restart")
        for button in (save, check, stage, trust, install):
            buttons.addWidget(button)
        root.addLayout(buttons)

        output = QPlainTextEdit()
        output.setReadOnly(True)
        output.setMinimumHeight(220)
        root.addWidget(output, 1)

        def pretty(value):
            import json
            output.setPlainText(json.dumps(value, indent=2, default=str))

        def refresh():
            info = self.service.status()
            settings = info["settings"]
            server.setText(str(settings.get("server_url", "")))
            channel.setCurrentText(str(settings.get("channel", "development")))
            auto_check.setChecked(bool(settings.get("auto_check", False)))
            device = info["device"]
            status_label.setText(
                f"Device: {device.get('device_name')}  •  Apollo {info.get('current_version')}  •  "
                f"Trusted key: {'YES' if info.get('trusted_key') else 'NO'}"
            )
            pretty(info)

        def save_settings():
            try:
                pretty(self.service.configure(server_url=server.text(), channel=channel.currentText(), auto_check=auto_check.isChecked()))
                refresh()
            except Exception as exc:
                QMessageBox.critical(page, "Update Settings", f"{type(exc).__name__}: {exc}")

        def do_check():
            try: pretty(self.service.check_for_updates())
            except Exception as exc: pretty({"ok":False,"error":f"{type(exc).__name__}: {exc}"})

        def do_stage():
            try: pretty(self.service.stage_update())
            except Exception as exc: pretty({"ok":False,"error":f"{type(exc).__name__}: {exc}"})

        def do_trust():
            path, _ = QFileDialog.getOpenFileName(page, "Select Apollo release public key", "", "PEM files (*.pem);;All files (*)")
            if path:
                try:
                    pretty(self.service.import_trusted_key(path))
                    refresh()
                except Exception as exc:
                    QMessageBox.critical(page, "Trust Key", f"{type(exc).__name__}: {exc}")

        def do_install():
            reply = QMessageBox.question(page, "Install Apollo Update", "Install the newest staged signed update and restart Apollo?")
            if reply != QMessageBox.StandardButton.Yes:
                return
            result = self.service.launch_installer(restart=True)
            pretty(result)
            if result.get("ok"):
                window = (ui_context or {}).get("apollo_window") if isinstance(ui_context, dict) else None
                if window is not None:
                    QTimer.singleShot(600, window.close)

        save.clicked.connect(save_settings)
        check.clicked.connect(do_check)
        stage.clicked.connect(do_stage)
        trust.clicked.connect(do_trust)
        install.clicked.connect(do_install)
        refresh()
        return page
