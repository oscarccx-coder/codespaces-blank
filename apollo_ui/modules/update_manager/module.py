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
        from PySide6.QtCore import QObject, Signal, QTimer, QProcess
        from PySide6.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
            QPushButton, QCheckBox, QPlainTextEdit, QFileDialog, QMessageBox,
            QProgressBar,
        )

        page = QWidget(parent)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(11)
        title = QLabel("Apollo Updates")
        title.setStyleSheet("font-size:22px;font-weight:700;")
        layout.addWidget(title)
        note = QLabel("Secure code updates without redownloading voice models or replacing saved projects.")
        note.setWordWrap(True)
        layout.addWidget(note)

        advanced_toggle = QPushButton("Advanced options ▸")
        advanced_panel = QWidget()
        advanced_layout = QVBoxLayout(advanced_panel)
        advanced_panel.setVisible(False)

        status = QLabel()
        status.setWordWrap(True)
        status.setObjectName("updateStatus")
        status.setStyleSheet("padding:12px;border:1px solid #17675d;"
                             "border-radius:10px;background:#0b282a;font-weight:600;")
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
            advanced_layout.addLayout(row)

        configuration_row("Update source", source)
        configuration_row("Server URL", server)
        advanced_layout.addWidget(auto_check)
        source.currentIndexChanged.connect(
            lambda _: server.setEnabled(source.currentData() == "server")
        )

        channel_row = QHBoxLayout()
        channel_label = QLabel("Release channel")
        channel_label.setToolTip("Stable is recommended for daily use; Beta includes experimental features.")
        channel.setToolTip("Select stable or signed beta updates.")
        channel_row.addWidget(channel_label)
        channel_row.addWidget(channel, 1)
        layout.addLayout(channel_row)

        actions = QHBoxLayout()
        combined_btn = QPushButton("Update Apollo")
        combined_btn.setMinimumHeight(44)
        combined_btn.setObjectName("primaryAction")
        combined_btn.setToolTip("Check, download, verify and install a newer signed release.")
        actions.addWidget(combined_btn)
        git_btn = QPushButton("Update from Git (main)")
        git_btn.setMinimumHeight(44)
        actions.addWidget(git_btn)
        actions.addStretch()
        layout.addLayout(actions)

        save_btn = QPushButton("Save update settings")
        check_btn = QPushButton("Check for updates only")
        stage_btn = QPushButton("Download & Verify")
        install_btn = QPushButton("Install staged update")
        advanced_actions = QHBoxLayout()
        for control in (save_btn, stage_btn, install_btn):
            advanced_actions.addWidget(control)
        check_btn.setText("Check only")
        check_btn.setMinimumHeight(44)
        actions.insertWidget(1, check_btn)
        advanced_layout.addLayout(advanced_actions)

        trust_row = QHBoxLayout()
        trust_github_btn = QPushButton("Trust GitHub Signing Key (one-time)")
        trust_local_btn = QPushButton("Import Public Key File")
        trust_row.addWidget(trust_github_btn)
        trust_row.addWidget(trust_local_btn)
        advanced_layout.addLayout(trust_row)

        progress = QLabel("No update operation running.")
        progress.setWordWrap(True)
        progress.setAccessibleName("Update activity and error status")
        layout.addWidget(progress)
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        progress_bar.setFormat("%p% downloaded")
        progress_bar.setAccessibleName("Update download progress")
        progress_bar.hide()
        layout.addWidget(progress_bar)
        advanced_toggle.setToolTip("Settings, signing-key setup and diagnostic information.")
        layout.addWidget(advanced_toggle)
        advanced_layout.addWidget(QLabel("Update details and diagnostics"))
        output = QPlainTextEdit()
        output.setReadOnly(True)
        output.setMinimumHeight(180)
        advanced_layout.addWidget(output, 1)
        layout.addWidget(advanced_panel, 1)
        layout.addStretch()

        def toggle_advanced():
            visible = not advanced_panel.isVisible()
            advanced_panel.setVisible(visible)
            advanced_toggle.setText("Advanced options ▾" if visible else "Advanced options ▸")

        advanced_toggle.clicked.connect(toggle_advanced)

        class UpdateSignals(QObject):
            finished = Signal(str, object)
            failed = Signal(str, str)
            progress = Signal(str)
            transferred = Signal(int, int)

        signals = UpdateSignals(page)
        state = {"busy": False}
        controls = (git_btn, save_btn, check_btn, stage_btn, install_btn,
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
                f"Installed: Apollo {info['current_version']}\n"
                f"Source: {'GitHub Releases' if settings.get('source') == 'github' else 'Local server'}"
                f"  •  Signing: {'Trusted key' if info['trusted_key'] else 'Setup needed'}"
            )
            latest = info.get("last_install")
            if latest and latest.get("ok") is False:
                progress.setText(
                    "Previous update failed. Review the logs under Advanced options."
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
            channel.setEnabled(not yes)
            source.setEnabled(not yes)
            server.setEnabled(not yes and source.currentData() == "server")

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
            progress_bar.setValue(0)
            progress_bar.setVisible(kind in {"stage", "combined"})
            progress.setText("Checking signed releases..." if kind == "check"
                             else "Preparing a verified Apollo update...")

            def report(amount, total):
                signals.transferred.emit(int(amount), int(total))
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
            progress_bar.setVisible(False)
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
            # A successful check with available=False is not an installable update.
            # Never install a stale staged package after Apollo says it is current.
            if kind in {"stage", "combined"} and not result.get("stage_dir"):
                progress.setText(result.get("reason") or "No newer signed update available.")
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
            progress_bar.setVisible(False)
            progress.setText(f"{kind} failed: {message}")
            pretty({"ok": False, "error": message})

        signals.finished.connect(finished)
        signals.failed.connect(failed)
        signals.progress.connect(progress.setText)

        def update_download_progress(amount, total):
            if total > 0:
                progress_bar.setRange(0, 100)
                progress_bar.setValue(min(100, int(amount * 100 / total)))
            else:
                progress_bar.setRange(0, 0)

        signals.transferred.connect(update_download_progress)

        # Git mode is for existing source checkouts, not signed distribution packages.
        # Run the trusted local Git client without a shell; never execute remote scripts.
        git_process = QProcess(page)
        git_process.setProcessChannelMode(QProcess.MergedChannels)
        git_state = {"output": "", "changed": False}

        def git_update():
            if state["busy"]:
                return
            checkout = self.base
            if not (checkout.parent / ".git").exists() and not (checkout / ".git").exists():
                QMessageBox.warning(page, "Git update unavailable",
                                    "Apollo is not running from a Git checkout. Use signed releases instead.")
                return
            if QMessageBox.question(
                page, "Update Apollo source",
                "Pull verified Git objects from origin/main into this local checkout?\\n"
                "This is a source-development update, not a signed Apollo release. "
                "Uncommitted local changes will not be overwritten.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            ) != QMessageBox.Yes:
                return
            set_busy(True)
            git_state["output"] = ""
            git_state["changed"] = False
            progress_bar.setRange(0, 0)  # Git provides no reliable byte total.
            progress_bar.setVisible(True)
            progress.setText("Updating Apollo from origin/main...")
            git_process.setWorkingDirectory(str(checkout))
            git_process.setProgram("git")
            git_process.setArguments(["-c", "pull.rebase=false", "pull", "--ff-only", "--progress", "origin", "main"])
            git_process.start()
            if not git_process.waitForStarted(1500):
                set_busy(False)
                progress_bar.hide()
                progress.setText("Git could not start. Check that Git for Windows is installed.")

        def git_output():
            chunk = bytes(git_process.readAllStandardOutput()).decode("utf-8", errors="replace")
            git_state["output"] = (git_state["output"] + chunk)[-24000:]
            lines = git_state["output"].replace("\\r", "\\n").splitlines()
            if lines:
                progress.setText(lines[-1][:220])
                output.setPlainText("\\n".join(lines[-120:]))
            if "Updating " in git_state["output"] or "Fast-forward" in git_state["output"]:
                git_state["changed"] = True

        def git_finished(exit_code, _status):
            git_output()
            set_busy(False)
            progress_bar.setRange(0, 100)
            progress_bar.setValue(100 if exit_code == 0 else 0)
            if exit_code != 0:
                progress.setText("Git update failed. See the details below.")
                QMessageBox.warning(page, "Apollo update failed",
                                    "Git did not update Apollo. Check the output under Advanced options. "
                                    "Local files were not intentionally discarded.")
                advanced_panel.show()
                return
            if "Already up to date." in git_state["output"] and not git_state["changed"]:
                progress.setText("Apollo source is already up to date.")
                return
            progress.setText("New Apollo source received. Restart required to load changes.")
            answer = QMessageBox.question(page, "Restart Apollo?",
                "Apollo source updated. Restart Apollo now to load the new code?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if answer == QMessageBox.Yes:
                import subprocess
                import sys
                launcher = self.base / "Setup" / "02_START_APOLLO.bat"
                try:
                    if not launcher.is_file():
                        raise FileNotFoundError(str(launcher))
                    if window is None:
                        raise RuntimeError("Apollo main window is unavailable.")
                    subprocess.Popen(["cmd.exe", "/c", str(launcher)], cwd=str(self.base),
                                     creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
                    QTimer.singleShot(200, window.close)
                except (OSError, RuntimeError) as exc:
                    QMessageBox.warning(page, "Restart manually",
                                        "Source updated; please close Apollo and start it again.\\n" + str(exc))

        git_process.readyReadStandardOutput.connect(git_output)
        git_process.finished.connect(git_finished)
        git_btn.clicked.connect(git_update)

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
            if not self.service.status().get("trusted_key"):
                advanced_panel.setVisible(True)
                advanced_toggle.setText("Advanced options ▾")
                QMessageBox.information(
                    page, "Set up secure updates",
                    "Before the first update, use Advanced options to trust the "
                    "verified Apollo release-signing public key. This is a one-time step."
                )
                return
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
