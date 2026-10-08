"""Apollo in-app GitHub updater UI backed by signed release packages.

Only an explicit button click may install/restart the application. An LLM tool
is not allowed to launch a core update or silently trust new signing keys.
"""
from pathlib import Path
from apollo_update import UpdateService
from apollo_github_updates import latest_release, download_release_asset


class Module:
    def __init__(self, context=None):
        self.context = context or {}
        self.base = Path(self.context.get("base_dir", ".")).resolve()
        self.service = UpdateService(self.base)

    def tools(self):
        return [
            {"name": "update_status", "description": "Read Apollo update settings/status.",
             "parameters": {"type": "object", "properties": {}}},
            {"name": "configure_update_source",
             "description": "Choose the update transport and release channel. Does not install an update.",
             "parameters": {"type": "object", "properties": {
                 "source": {"type": "string", "enum": ["github", "server"]},
                 "server_url": {"type": "string"},
                 "channel": {"type": "string", "enum": ["stable", "beta", "development", "pinned"]},
                 "auto_check": {"type": "boolean"},
             }}},
            {"name": "check_for_updates",
             "description": "Check if a newer signed Apollo release is offered.",
             "parameters": {"type": "object", "properties": {}}},
        ]

    def run(self, action, arguments):
        arguments = arguments or {}
        if action == "update_status":
            return self.service.status()
        if action == "configure_update_source":
            return self.service.configure(
                server_url=arguments.get("server_url"),
                source=arguments.get("source"),
                channel=arguments.get("channel"),
                auto_check=arguments.get("auto_check") if "auto_check" in arguments else None,
                device_name=arguments.get("device_name"),
            )
        if action == "check_for_updates":
            return self.service.check_for_updates()
        if action in {"install_staged_update", "import_update_public_key", "stage_update"}:
            raise PermissionError("Installing, trusting and staging updates requires direct user interaction in Update Manager.")
        raise KeyError(action)

    def self_test(self):
        data = self.service.status()
        assert data["settings"]["source"] in {"github", "server"}
        return "Apollo update service and trust state ready"

    def build_ui(self, parent=None, ui_context=None):
        import hashlib
        import json
        import threading
        from PySide6.QtCore import QObject, Signal, QTimer
        from PySide6.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
            QPushButton, QCheckBox, QPlainTextEdit, QFileDialog, QMessageBox,
        )

        page = QWidget(parent)
        layout = QVBoxLayout(page)
        layout.setSpacing(10)
        title = QLabel("Apollo Update Centre")
        title.setStyleSheet("font-size:22px;font-weight:700;")
        layout.addWidget(title)

        status = QLabel()
        status.setWordWrap(True)
        layout.addWidget(status)

        source = QComboBox()
        source.addItem("GitHub Releases (recommended)", "github")
        source.addItem("Local signed update server", "server")
        server = QLineEdit()
        server.setPlaceholderText("https://your-local-update-server/")
        channel = QComboBox()
        channel.addItems(["stable", "beta", "development", "pinned"])
        auto_check = QCheckBox("Check for updates when Update Centre opens")

        def configuration_row(label_text, widget):
            row = QHBoxLayout()
            label = QLabel(label_text)
            label.setMinimumWidth(105)
            row.addWidget(label)
            row.addWidget(widget, 1)
            layout.addLayout(row)

        configuration_row("Update source", source)
        configuration_row("Server URL", server)
        configuration_row("Channel", channel)
        layout.addWidget(auto_check)
        source.currentIndexChanged.connect(
            lambda _: server.setEnabled(source.currentData() == "server")
        )

        actions = QHBoxLayout()
        save_btn = QPushButton("Save Source")
        check_btn = QPushButton("Check GitHub")
        stage_btn = QPushButton("Download & Verify")
        install_btn = QPushButton("Install & Restart")
        combined_btn = QPushButton("Update & Restart")
        actions.addWidget(save_btn)
        actions.addWidget(check_btn)
        actions.addWidget(stage_btn)
        actions.addWidget(install_btn)
        actions.addWidget(combined_btn)
        layout.addLayout(actions)

        trust_row = QHBoxLayout()
        trust_github_btn = QPushButton("Trust GitHub Signing Key (one-time)")
        trust_local_btn = QPushButton("Import Public Key File")
        trust_row.addWidget(trust_github_btn)
        trust_row.addWidget(trust_local_btn)
        layout.addLayout(trust_row)

        progress = QLabel("No update operation running.")
        progress.setWordWrap(True)
        layout.addWidget(progress)
        output = QPlainTextEdit()
        output.setReadOnly(True)
        output.setMinimumHeight(210)
        layout.addWidget(output, 1)

        class UpdateSignals(QObject):
            finished = Signal(str, object)
            failed = Signal(str, str)
            progress = Signal(str)

        signals = UpdateSignals(page)
        state = {"busy": False}
        controls = (save_btn, check_btn, stage_btn, install_btn,
                    combined_btn, trust_github_btn, trust_local_btn)
        window = (ui_context or {}).get("apollo_window") if isinstance(ui_context, dict) else None

        def pretty(data):
            output.setPlainText(json.dumps(data, indent=2, default=str))

        def refresh():
            info = self.service.status()
            settings = info["settings"]
            ix = source.findData(settings.get("source", "github"))
            source.setCurrentIndex(max(0, ix))
            server.setText(str(settings.get("server_url", "")))
            channel.setCurrentText(str(settings.get("channel", "stable")))
            auto_check.setChecked(bool(settings.get("auto_check", False)))
            status.setText(
                f"Apollo {info['current_version']}   •   GitHub: {info['github_repository']}"
                f"   •   Signing key: {'TRUSTED' if info['trusted_key'] else 'NOT CONFIGURED'}"
            )
            latest = info.get("last_install")
            if latest and latest.get("ok") is False:
                progress.setText(
                    "Last update FAILED and rollback was attempted. See Apollo's update logs."
                )
            pretty(info)

        def save():
            try:
                result = self.service.configure(
                    source=source.currentData(), server_url=server.text().strip(),
                    channel=channel.currentText(), auto_check=auto_check.isChecked()
                )
                refresh()
                pretty(result)
            except Exception as exc:
                QMessageBox.warning(page, "Update settings", str(exc))

        def set_busy(yes):
            state["busy"] = bool(yes)
            for btn in controls:
                btn.setEnabled(not yes)

        def run_async(kind):
            if state["busy"]:
                return
            # Save UI settings before the request so it checks the selected channel.
            if kind in {"check", "stage", "combined", "key"}:
                try:
                    self.service.configure(
                        source=source.currentData(), server_url=server.text().strip(),
                        channel=channel.currentText(), auto_check=auto_check.isChecked()
                    )
                except Exception as exc:
                    QMessageBox.warning(page, "Update settings", str(exc))
                    return
            set_busy(True)
            progress.setText("Checking GitHub releases..." if kind == "check"
                             else "Preparing signed update...")

            def report(amount, total):
                if total:
                    signals.progress.emit(
                        f"Downloaded {amount / 1048576:.1f} / {total / 1048576:.1f} MiB"
                    )
                else:
                    signals.progress.emit(f"Downloaded {amount / 1048576:.1f} MiB")

            def background():
                try:
                    if kind == "check":
                        result = self.service.check_for_updates()
                    elif kind in {"stage", "combined"}:
                        result = self.service.stage_update(progress=report)
                    elif kind == "key":
                        current = self.service.settings()
                        if current["source"] != "github":
                            raise ValueError("Select GitHub Releases as the update source.")
                        candidate = latest_release(current["channel"])
                        if not candidate or not candidate.get("key_url"):
                            raise ValueError("No GitHub Release signing key asset has been published for this channel.")
                        dest = self.service.download_dir / "github_release_public.pem"
                        download_release_asset(candidate["key_url"], dest, max_bytes=65536)
                        from cryptography.hazmat.primitives.serialization import load_pem_public_key
                        data = dest.read_bytes()
                        key = load_pem_public_key(data)
                        if key.__class__.__name__ != "Ed25519PublicKey":
                            # Algorithm verification is also enforced by signature verification.
                            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
                            if not isinstance(key, Ed25519PublicKey):
                                raise ValueError("Expected an Ed25519 release-signing public key.")
                        result = {"key_path": str(dest), "fingerprint": hashlib.sha256(data).hexdigest()}
                    else:
                        raise ValueError("Unknown updater operation.")
                    signals.finished.emit(kind, result)
                except Exception as exc:
                    signals.failed.emit(kind, f"{type(exc).__name__}: {exc}")

            threading.Thread(target=background, name="ApolloReleaseUpdate", daemon=True).start()

        def launch_installer():
            result = self.service.launch_installer(restart=True)
            pretty(result)
            if result.get("ok"):
                progress.setText("Installer launched. Closing Apollo to permit the update and restart.")
                if window is not None:
                    QTimer.singleShot(150, window.close)
                else:
                    QMessageBox.information(page, "Close Apollo",
                                            "Close Apollo now so the external installer can finish and restart it.")
            else:
                progress.setText("Installer could not start: " + result.get("error", "Unknown error"))

        def finished(kind, result):
            set_busy(False)
            pretty(result)
            if kind == "key":
                fingerprint = result["fingerprint"]
                answer = QMessageBox.question(
                    page, "Trust GitHub Release Signing Key",
                    "Trust this public signing key for FUTURE Apollo code updates?\n"
                    "Check the fingerprint against a separate trusted source before accepting.\n\n"
                    "SHA-256: " + fingerprint,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                try:
                    if answer == QMessageBox.StandardButton.Yes:
                        pretty(self.service.import_trusted_key(result["key_path"]))
                        progress.setText("Public signing key installed for future signed updates.")
                    else:
                        progress.setText("Signing key not trusted. No change made.")
                finally:
                    Path(result["key_path"]).unlink(missing_ok=True)
                refresh()
                return
            if not result.get("ok"):
                progress.setText(result.get("error") or result.get("reason") or "No update available.")
                return
            if kind == "check":
                progress.setText("New release available." if result.get("available")
                                 else "Apollo is up to date for the chosen channel.")
                return
            if kind == "stage":
                progress.setText("Signed update downloaded and verified. Ready to install.")
                return
            if kind == "combined":
                progress.setText("Release verified. Handing off to the external updater...")
                launch_installer()

        def failed(kind, message):
            set_busy(False)
            progress.setText(f"{kind} failed: {message}")
            pretty({"ok": False, "error": message})

        signals.finished.connect(finished)
        signals.failed.connect(failed)
        signals.progress.connect(progress.setText)

        def do_install():
            confirmation = QMessageBox.question(
                page, "Install signed Apollo update",
                "Install the latest VERIFIED staged release and restart Apollo?\n"
                "The external installer backs up code and rolls back on health-check failure.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirmation == QMessageBox.StandardButton.Yes:
                launch_installer()

        def do_combined():
            confirmation = QMessageBox.question(
                page, "Update Apollo from GitHub",
                "Download and verify a signed Apollo update, then close Apollo, install it and restart?\n"
                "Your voice models and user data will not be replaced.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirmation == QMessageBox.StandardButton.Yes:
                run_async("combined")

        def local_trust():
            file, _ = QFileDialog.getOpenFileName(
                page, "Select trusted Apollo signing key", "",
                "PEM public keys (*.pem);;All files (*)"
            )
            if file:
                try:
                    from cryptography.hazmat.primitives.serialization import load_pem_public_key
                    data = Path(file).read_bytes()
                    load_pem_public_key(data)
                    fingerprint = hashlib.sha256(data).hexdigest()
                    if QMessageBox.question(
                        page, "Trust signing key", f"Accept SHA-256 fingerprint?\n{fingerprint}",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No
                    ) == QMessageBox.Yes:
                        pretty(self.service.import_trusted_key(file))
                        refresh()
                except Exception as exc:
                    QMessageBox.warning(page, "Signing key", str(exc))

        save_btn.clicked.connect(save)
        check_btn.clicked.connect(lambda: run_async("check"))
        stage_btn.clicked.connect(lambda: run_async("stage"))
        install_btn.clicked.connect(do_install)
        combined_btn.clicked.connect(do_combined)
        trust_github_btn.clicked.connect(lambda: run_async("key"))
        trust_local_btn.clicked.connect(local_trust)
        refresh()
        if self.service.settings().get("auto_check"):
            QTimer.singleShot(300, lambda: run_async("check"))
        return page
