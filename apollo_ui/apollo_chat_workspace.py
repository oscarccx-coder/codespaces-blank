"""Apollo's integrated chat workspace, backed by real local conversations/tools."""
import html
import json
from pathlib import Path
import re
import secrets
import time

from PySide6.QtCore import Qt, QTimer, QObject, QRunnable, Signal, Slot, QUrl, QByteArray
from PySide6.QtGui import QTextDocument, QTextCursor, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QPlainTextEdit, QTextBrowser, QComboBox, QCheckBox, QListWidget,
    QListWidgetItem, QSplitter, QTabWidget, QMenu, QFileDialog, QInputDialog,
    QMessageBox, QApplication, QDialog)

from apollo_chat_store import ChatStore
from apollo_chat_files import extract_attachment, build_chat_context, table_summary, export_canvas
from apollo_personality import personality_instruction
from ollama_client import OllamaClient
from workers import ChatTask


class Composer(QPlainTextEdit):
    returnPressed = Signal()
    filesDropped = Signal(list)

    def text(self):
        return self.toPlainText()

    def setText(self, text):
        self.setPlainText(text)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not event.modifiers() & Qt.ShiftModifier:
            self.returnPressed.emit(); event.accept()
        else:
            super().keyPressEvent(event)

    def canInsertFromMimeData(self, source):
        return source.hasUrls() or super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        if source.hasUrls():
            paths = [u.toLocalFile() for u in source.urls() if u.isLocalFile()]
            if paths:
                self.filesDropped.emit(paths); return
        super().insertFromMimeData(source)


class SafeTranscript(QTextBrowser):
    """Model output cannot load files/remote images or navigate automatically."""
    def loadResource(self, resource_type, name):
        return QByteArray()


def markdown_html(text):
    # Images are attachments, not auto-fetched resources embedded by a model.
    text = re.sub(r"!\[([^]]*)\]\([^)]*\)", r"[Image: \1]", str(text))
    document = QTextDocument()
    document.setMarkdown(text, QTextDocument.MarkdownDialectGitHub | QTextDocument.MarkdownNoHTML)
    body = document.toHtml()
    return re.search(r"<body[^>]*>(.*)</body>", body, re.S).group(1)


class BackgroundSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)
    completed = Signal()


class BackgroundTask(QRunnable):
    def __init__(self, fn):
        super().__init__(); self.fn = fn; self.signals = BackgroundSignals()

    @Slot()
    def run(self):
        try:
            self.signals.finished.emit(self.fn())
        except Exception as exc:
            self.signals.failed.emit(str(exc))
        finally:
            self.signals.completed.emit()


class ScopedChatManager:
    """Keep existing tools but prohibit implicit recall from the legacy chat pool."""
    def __init__(self, manager):
        self.manager = manager
    def __getattr__(self, name):
        return getattr(self.manager, name)
    def get_module(self, name):
        return None if name == "chat_memory_module" else self.manager.get_module(name)
    def ollama_tools(self):
        return [t for t in self.manager.ollama_tools()
                if not str((t.get("function") or {}).get("name", "")).startswith("chat_memory_module__")]
    def execute(self, module, action, arguments):
        if module == "chat_memory_module":
            raise PermissionError("This chat uses only its own conversation history.")
        return self.manager.execute(module, action, arguments)
    def execute_tool(self, name, arguments):
        if name.startswith("chat_memory_module__"):
            raise PermissionError("This chat uses only its own conversation history.")
        return self.manager.execute_tool(name, arguments)


class ChatWorkspace(QWidget):
    def __init__(self, owner, base_dir):
        super().__init__()
        self.owner, self.base_dir = owner, Path(base_dir)
        self.store = ChatStore(base_dir)
        self.session_store = self.store
        self.temp_store = None
        self.busy = False
        self.io_busy = False
        self.task = None
        self.background_tasks = []
        self.pending_attachments = []
        self.answer_id = None
        self.current_text = ""
        self.rendered_stream = ""
        self.activities = []
        self.packet = {}
        self._action_token = secrets.token_hex(16)
        self._loading = False
        self._has_loaded = False
        self._last_checkpoint = 0
        self._started = 0
        self._cancel_requested = False
        self.project_dialog = None
        self.inspector_dialog = None
        self._nav_choice = None
        legacy = self.store.import_legacy(getattr(owner, "chat_history", []))
        initial = self.store.preference("active_chat")
        try:
            if not initial:
                raise KeyError()
            self.store.chat(initial)
        except KeyError:
            existing = self.store.list_chats()
            initial = legacy or (existing[0]["id"] if existing else self.store.new_chat())
        self.chat_id = initial
        self._build()
        self.stream_timer = QTimer(self); self.stream_timer.setInterval(100)
        self.stream_timer.timeout.connect(self._flush_stream)
        self.draft_timer = QTimer(self); self.draft_timer.setSingleShot(True); self.draft_timer.setInterval(350)
        self.draft_timer.timeout.connect(self.save_draft)
        self.composer.textChanged.connect(self._draft_changed)
        self.canvas.textChanged.connect(self._draft_changed)
        self._refresh_projects(); self.load_chat(initial)

    def _button(self, title, callback, layout):
        button = QPushButton(title); button.clicked.connect(callback); layout.addWidget(button)
        return button

    def _build(self):
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        heading = QHBoxLayout()
        title = QLabel("APOLLO"); title.setStyleSheet("font-size:23px;font-weight:700;color:#7ff0d7;")
        heading.addWidget(title); self.tagline = QLabel("Your local AI workspace"); heading.addWidget(self.tagline); heading.addStretch()
        self.connection_label = QLabel("Your selected Ollama model")
        self.connection_label.setWordWrap(True); self.connection_label.setMaximumWidth(200)
        heading.addWidget(self.connection_label)
        self._button("Chats", self.toggle_navigation, heading)
        self._button("Apps", self.apps_menu, heading)
        self._button("Preferences", self.preferences, heading)
        outer.addLayout(heading)
        splitter = QSplitter(Qt.Horizontal); self.splitter = splitter
        navigation = QWidget(); nav = QVBoxLayout(navigation); nav.setContentsMargins(0, 0, 8, 0)
        self.navigation = navigation; navigation.setMinimumWidth(170); navigation.setMaximumWidth(260)
        row = QHBoxLayout()
        self.new_button = self._button("+ New chat", lambda: self.new_chat(), row)
        self.temporary_button = self._button("Temporary", lambda: self.new_chat(temporary=True), row)
        nav.addLayout(row)
        self.search = QLineEdit(); self.search.setPlaceholderText("Search chats and messages")
        self.search.textChanged.connect(self.refresh_chats); nav.addWidget(self.search)
        row = QHBoxLayout()
        self.project_filter = QComboBox(); self.project_filter.addItem("All projects", "")
        self.project_filter.currentIndexChanged.connect(self.refresh_chats)
        row.addWidget(self.project_filter, 1); self._button("+ Project", self.new_project, row)
        nav.addLayout(row)
        self.show_archived = QCheckBox("Archived chats"); self.show_archived.toggled.connect(self.refresh_chats)
        nav.addWidget(self.show_archived)
        self.chats = QListWidget(); self.chats.setObjectName("apollo_chat_list")
        self.chats.itemClicked.connect(self._chat_selected); nav.addWidget(self.chats, 1)
        self._button("Project instructions & sources", self.project_settings, nav)
        splitter.addWidget(navigation)
        centre = QWidget(); main = QVBoxLayout(centre); main.setContentsMargins(4, 0, 4, 0)
        top = QHBoxLayout()
        self.chat_title = QLabel("New chat"); self.chat_title.setStyleSheet("font-size:17px;font-weight:600;")
        top.addWidget(self.chat_title, 1)
        self._button("Canvas / Sources", self.toggle_inspector, top)
        self._button("Chat menu", self.chat_menu, top)
        main.addLayout(top)
        options = QHBoxLayout()
        self.models = QComboBox(); self.models.setEditable(True); self.models.setMinimumWidth(110)
        self.models.setToolTip("Choose an installed model. Selecting a name does not download it.")
        self.models.addItem(str(self.owner.config.get("model", "")))
        self.models.currentTextChanged.connect(self.save_options)
        options.addWidget(self.models, 1); self.model_refresh = self._button("↻", self.refresh_models, options)
        self.style = QComboBox(); self.style.addItems(["Balanced", "Concise", "Detailed"])
        self.style.currentTextChanged.connect(self.save_options); options.addWidget(self.style)
        self.mode = QComboBox(); self.mode.addItems(["Chat", "Web research", "Coding", "Analyse files"])
        self.mode.setToolTip("Web research explicitly enables web lookup for this request. Coding uses Apollo's existing guarded tools.")
        options.addWidget(self.mode)
        self.memory_check = QCheckBox("Memory"); self.memory_check.setToolTip("Retrieve relevant saved knowledge; project sources remain separate.")
        self.tools_check = QCheckBox("Tools")
        for check in (self.memory_check, self.tools_check):
            check.toggled.connect(self.save_options); options.addWidget(check)
        main.addLayout(options)
        self.transcript = SafeTranscript(); self.transcript.setObjectName("apollo_chat_transcript")
        self.transcript.setOpenExternalLinks(False); self.transcript.setOpenLinks(False)
        self.transcript.anchorClicked.connect(self.anchor_clicked)
        self.transcript.setStyleSheet("QTextBrowser{background:#0b2224;border:1px solid #23514c;border-radius:12px;padding:16px;font-size:14px;}")
        main.addWidget(self.transcript, 1)
        self.attachments_list = QListWidget(); self.attachments_list.setMaximumHeight(55)
        self.attachments_list.setFlow(QListWidget.LeftToRight); self.attachments_list.hide()
        self.attachments_list.setToolTip("Files staged for the next message. Select a file and use Remove file to unstage it.")
        main.addWidget(self.attachments_list)
        self.composer = Composer(); self.composer.setObjectName("apollo_chat_composer")
        self.composer.setPlaceholderText("Ask Apollo… Enter sends · Shift+Enter adds a line · drop files here")
        self.composer.setMinimumHeight(82); self.composer.setMaximumHeight(135)
        self.composer.returnPressed.connect(self.send); self.composer.filesDropped.connect(self.attach_paths)
        main.addWidget(self.composer)
        controls = QHBoxLayout()
        self.attach_button = self._button("+ Files", self.attach_files, controls)
        self.remove_file_button = self._button("Remove", self.unstage_file, controls)
        self._button("Prompts", self.prompt_menu, controls)
        self.mic = self._button("🎙 Dictate", self.owner.start_speech_to_text, controls)
        self.voice = self._button("Voice", self.owner.toggle_speech_mute, controls)
        controls.addStretch()
        self.stop_button = self._button("Stop", self.stop, controls); self.stop_button.setEnabled(False)
        self.send_button = self._button("Send", self.send, controls); self.send_button.setObjectName("primaryAction")
        main.addLayout(controls)
        self.status = QLabel("Ready"); self.status.setWordWrap(True); main.addWidget(self.status)
        splitter.addWidget(centre)
        self.inspector = QTabWidget(); self.inspector.setMinimumWidth(260)
        canvas_page = QWidget(); cv = QVBoxLayout(canvas_page)
        cv.addWidget(QLabel("Canvas · edit here, then export with Save as"))
        self.canvas = QPlainTextEdit(); self.canvas.setObjectName("apollo_chat_canvas")
        self.canvas.setPlaceholderText("Open a response/code block here, edit it, then include it in your next request.")
        cv.addWidget(self.canvas, 1)
        self.include_canvas = QCheckBox("Include canvas in next request"); cv.addWidget(self.include_canvas)
        row = QHBoxLayout()
        self._button("Undo", self.canvas.undo, row); self._button("Redo", self.canvas.redo, row)
        self._button("Save as…", self.save_canvas, row); cv.addLayout(row)
        self.inspector.addTab(canvas_page, "Canvas")
        source_page = QWidget(); sl = QVBoxLayout(source_page)
        self.sources = QListWidget(); self.sources.currentItemChanged.connect(self.source_selected)
        self.source_text = QPlainTextEdit(); self.source_text.setReadOnly(True)
        sl.addWidget(self.sources, 1); sl.addWidget(self.source_text, 2)
        self._button("CSV / TSV statistics", self.quick_stats, sl)
        self.inspector.addTab(source_page, "Sources")
        self.activity = QPlainTextEdit(); self.activity.setReadOnly(True)
        self.inspector.addTab(self.activity, "Activity")
        splitter.addWidget(self.inspector); self.inspector.hide()
        splitter.setSizes([235, 800, 340]); outer.addWidget(splitter, 1)
        # Keep all existing shell/voice launch surfaces wired to this composer.
        self.owner.chat_input = self.composer; self.owner.chat_view = self.transcript
        self.owner.chat_model = self.connection_label; self.owner.chat_send_button = self.send_button
        self.owner.chat_mic_button = self.mic; self.owner.chat_voice_button = self.voice
        if hasattr(self.owner, "_update_speech_buttons"):
            self.owner._update_speech_buttons()
        for key, fn in (("Ctrl+N", lambda: self.new_chat()), ("Ctrl+F", self.search.setFocus),
                        ("Ctrl+Shift+C", self.copy_last), ("Escape", self.stop)):
            shortcut = QShortcut(QKeySequence(key), self); shortcut.setContext(Qt.WidgetWithChildrenShortcut)
            shortcut.activated.connect(fn)

    def _draft_changed(self):
        if not self._loading:
            self.draft_timer.start()

    def save_draft(self):
        if not self._loading:
            self.session_store.update_chat(self.chat_id, draft=self.composer.text(), canvas=self.canvas.toPlainText())

    def save_options(self, *_):
        if self._loading:
            return
        self.session_store.update_chat(self.chat_id, model=self.models.currentText().strip(),
            style=self.style.currentText(), memory=int(self.memory_check.isChecked()), tools=int(self.tools_check.isChecked()))

    def _refresh_projects(self):
        current = self.project_filter.currentData()
        self.project_filter.blockSignals(True); self.project_filter.clear(); self.project_filter.addItem("All projects", "")
        for project in self.store.projects():
            self.project_filter.addItem(project["title"], project["id"])
        self.project_filter.setCurrentIndex(max(0, self.project_filter.findData(current)))
        self.project_filter.blockSignals(False)

    def refresh_chats(self, *_):
        self.chats.clear()
        for chat in self.store.list_chats(self.search.text(), self.project_filter.currentData(), self.show_archived.isChecked()):
            item = QListWidgetItem(("★ " if chat["pinned"] else "") + chat["title"])
            item.setData(Qt.UserRole, chat["id"]); self.chats.addItem(item)
            if self.session_store is self.store and chat["id"] == self.chat_id:
                self.chats.setCurrentItem(item)

    def _chat_selected(self, item):
        if self.busy or self.io_busy:
            return
        self.load_chat(item.data(Qt.UserRole))

    def load_chat(self, chat_id, store=None):
        if self.busy or self.io_busy or getattr(self.owner, "stt_task", None) is not None:
            return
        if hasattr(self, "draft_timer") and self._has_loaded:
            self.draft_timer.stop(); self.save_draft()
        previous_store = self.session_store
        self.session_store = store or self.store; self.chat_id = chat_id
        try:
            saved_pending = json.loads(self.session_store.preference("pending:" + chat_id, "[]"))
        except (ValueError, TypeError):
            saved_pending = []
        owned_ids = {a["id"] for a in self.session_store.attachments(chat_id=chat_id)}
        self.pending_attachments = [i for i in saved_pending if i in owned_ids] if isinstance(saved_pending, list) else []
        self._loading = True
        chat = self.session_store.chat(chat_id)
        self.chat_title.setText(("Temporary · " if self.session_store.temporary else "") + chat["title"])
        self.models.setCurrentText(chat["model"] or self.owner.config.get("model", ""))
        self.style.setCurrentText(chat["style"])
        self.memory_check.setChecked(bool(chat["memory"])); self.tools_check.setChecked(bool(chat["tools"]))
        self.memory_check.setEnabled(not self.session_store.temporary); self.tools_check.setEnabled(not self.session_store.temporary)
        self.mic.setEnabled(not self.session_store.temporary and bool(getattr(self.owner, "_speech_module_ready", lambda: False)()))
        self.voice.setEnabled(not self.session_store.temporary)
        self.composer.setText(chat["draft"]); self.canvas.setPlainText(chat["canvas"])
        self._loading = False
        self._has_loaded = True
        if previous_store.temporary and previous_store is not self.session_store:
            previous_store.close()
            if self.temp_store is previous_store:
                self.temp_store = None
        if self.session_store is self.store:
            self.store.set_preference("active_chat", chat_id)
        self.current_text = ""; self.packet = {}; self.activities = []
        self.activity.clear(); self.refresh_chats(); self.refresh_attachments(); self.render()
        self.refresh_sources()
        self.status.setText("Temporary chat: history, tools and saved-memory retrieval are off." if self.session_store.temporary else "Saved on this computer · choose a model and start talking.")

    def new_chat(self, temporary=False):
        if self.busy or self.io_busy or getattr(self.owner, "stt_task", None) is not None:
            return
        self.save_draft()
        if temporary:
            self.temp_store = ChatStore(self.base_dir, temporary=True)
            ident = self.temp_store.new_chat(model=self.models.currentText())
            self.load_chat(ident, self.temp_store)
        else:
            ident = self.store.new_chat(project_id=self.project_filter.currentData() or None, model=self.models.currentText())
            self.load_chat(ident)

    def new_project(self):
        if self.busy or self.io_busy:
            return
        name, ok = QInputDialog.getText(self, "New project", "Project name:")
        if not ok or not name.strip():
            return
        instructions, ok = QInputDialog.getMultiLineText(self, "Project instructions", "Preferences and context for chats in this project:")
        if ok:
            ident = self.store.create_project(name, instructions)
            self._refresh_projects(); self.project_filter.setCurrentIndex(self.project_filter.findData(ident))
            self.new_chat()

    def project_settings(self):
        project_id = self.project_filter.currentData() or self.session_store.chat(self.chat_id)["project_id"]
        project = self.store.project(project_id) if project_id else None
        if not project:
            self.status.setText("Choose or create a project first."); return
        dialog = QDialog(self); dialog.setWindowTitle(project["title"] + " · instructions & sources"); dialog.resize(650, 550)
        layout = QVBoxLayout(dialog)
        instructions = QPlainTextEdit(project["instructions"]); layout.addWidget(instructions, 1)
        files = QListWidget(); layout.addWidget(files, 1)
        def reload():
            files.clear()
            for data in self.store.attachments(project_id=project_id):
                item = QListWidgetItem(data["name"]); item.setData(Qt.UserRole, data["id"]); files.addItem(item)
        row = QHBoxLayout()
        self._button("Add project sources", lambda: self.attach_files(project_id=project_id), row)
        def remove():
            if files.currentItem():
                self.store.remove_attachment(files.currentItem().data(Qt.UserRole)); reload()
        self._button("Remove selected", remove, row)
        def save():
            self.store.update_project(project_id, instructions.toPlainText()); dialog.accept()
        self._button("Save instructions", save, row); layout.addLayout(row)
        dialog.refresh_files = reload; self.project_dialog = dialog; reload(); dialog.open()

    def chat_menu(self):
        menu = QMenu(self)
        actions = (("Rename", self.rename_chat), ("Pin / unpin", self.pin_chat),
                   ("Archive / restore", self.archive_chat), ("Move to project", self.move_project),
                   ("Export Markdown", lambda: self.export_chat("markdown")),
                   ("Export JSON", lambda: self.export_chat("json")), ("Delete chat", self.delete_chat))
        for name, fn in actions:
            action = menu.addAction(name); action.triggered.connect(fn); action.setEnabled(not self.busy and not self.io_busy)
        menu.exec(self.chat_title.mapToGlobal(self.chat_title.rect().bottomLeft()))

    def rename_chat(self):
        chat = self.session_store.chat(self.chat_id)
        title, ok = QInputDialog.getText(self, "Rename chat", "Title:", text=chat["title"])
        if ok and title.strip():
            self.session_store.update_chat(self.chat_id, title=title); self.load_chat(self.chat_id, self.session_store)

    def pin_chat(self):
        chat = self.session_store.chat(self.chat_id)
        self.session_store.update_chat(self.chat_id, pinned=int(not chat["pinned"])); self.refresh_chats()

    def archive_chat(self):
        chat = self.session_store.chat(self.chat_id)
        self.session_store.update_chat(self.chat_id, archived=int(not chat["archived"])); self.refresh_chats()

    def move_project(self):
        if self.session_store.temporary:
            return
        projects = self.store.projects(); labels = ["No project"] + [p["title"] for p in projects]
        value, ok = QInputDialog.getItem(self, "Move chat", "Project:", labels, 0, False)
        if ok:
            index = labels.index(value)
            self.store.update_chat(self.chat_id, project_id=projects[index - 1]["id"] if index else None)
            self.refresh_chats()

    def delete_chat(self):
        if QMessageBox.question(self, "Delete chat", "Delete this chat and its attachment snapshots?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            old_store = self.session_store
            old_store.delete_chat(self.chat_id)
            self._loading = True
            self.chat_id = self.store.new_chat()
            self.session_store = self.store
            self._has_loaded = False
            self._loading = False
            self.load_chat(self.chat_id)

    def export_chat(self, format):
        name, _ = QFileDialog.getSaveFileName(self, "Export conversation", "Apollo_Chat." + ("json" if format == "json" else "md"))
        if name:
            Path(name).write_text(self.session_store.export(self.chat_id, format), encoding="utf-8")
            self.status.setText("Exported " + Path(name).name)

    def preferences(self):
        text, ok = QInputDialog.getMultiLineText(self, "Custom instructions", "Response preferences for saved chats:",
                                               self.store.preference("custom_instructions"))
        if ok:
            self.store.set_preference("custom_instructions", text[:3000])

    def _background(self, fn, callback):
        task = BackgroundTask(fn); self.background_tasks.append(task)
        task.signals.finished.connect(callback, Qt.QueuedConnection)
        task.signals.failed.connect(self._background_failed, Qt.QueuedConnection)
        task.signals.completed.connect(self._background_done, Qt.QueuedConnection)
        self.owner.thread_pool.start(task)

    @Slot(str)
    def _background_failed(self, error):
        self.status.setText(error)

    @Slot()
    def _background_done(self):
        self.io_busy = False
        self._set_busy(self.busy)
        self.model_refresh.setEnabled(not self.busy)
        # Keep references until their queued signals have been delivered.

    def refresh_models(self):
        if self.busy or self.io_busy:
            return
        self.io_busy = True; self.model_refresh.setEnabled(False)
        self.status.setText("Checking installed Ollama models…")
        self._background(lambda: self.owner.client.models(), self._models_ready)

    @Slot(object)
    def _models_ready(self, models):
        selected = self.models.currentText()
        self.models.blockSignals(True); self.models.clear(); self.models.addItems(models)
        self.models.setCurrentText(selected); self.models.blockSignals(False)
        self.status.setText(f"{len(models)} installed model(s). No downloads started.")

    def attach_files(self, checked=False, project_id=None):
        paths, _ = QFileDialog.getOpenFileNames(self, "Attach files", "", "Documents and images (*.txt *.md *.csv *.tsv *.pdf *.docx *.xlsx *.png *.jpg *.jpeg *.webp *.json *.py *.js *.ts);;All files (*)")
        if paths:
            self.attach_paths(paths, project_id=project_id)

    def attach_paths(self, paths, project_id=None):
        if self.busy or self.io_busy:
            return
        if len(paths) + len(self.pending_attachments) > 8:
            self.status.setText("Attach up to eight files per message."); return
        self.io_busy = True; self._attachment_target = project_id
        self._set_busy(False); self.status.setText("Reading attachment snapshots…")
        self._background(lambda: [extract_attachment(path) for path in paths], self._attachments_ready)

    @Slot(object)
    def _attachments_ready(self, attachments):
        for data in attachments:
            if self._attachment_target:
                if data["kind"] == "image":
                    self.status.setText("Attach project images to a specific message when you want vision analysis.")
                    continue
                self.store.add_attachment(data, project_id=self._attachment_target)
            else:
                self.pending_attachments.append(self.session_store.add_attachment(data, chat_id=self.chat_id))
        self.refresh_attachments(); self.refresh_sources()
        if self.project_dialog is not None and self.project_dialog.isVisible():
            self.project_dialog.refresh_files()
        self.status.setText("Files ready. Review the message, then Send.")

    def refresh_attachments(self):
        self.session_store.set_preference("pending:" + self.chat_id, json.dumps(self.pending_attachments))
        self.attachments_list.clear()
        for ident in self.pending_attachments:
            data = self.session_store.attachment(ident)
            item = QListWidgetItem(data["name"]); item.setData(Qt.UserRole, ident); self.attachments_list.addItem(item)
        self.attachments_list.setVisible(bool(self.pending_attachments))

    def unstage_file(self):
        if self.busy or self.io_busy:
            return
        item = self.attachments_list.currentItem()
        if item:
            ident = item.data(Qt.UserRole); self.pending_attachments.remove(ident)
            self.session_store.remove_attachment(ident); self.refresh_attachments(); self.refresh_sources()

    def refresh_sources(self):
        self.sources.clear()
        chat = self.session_store.chat(self.chat_id)
        sources = self.session_store.attachments(chat_id=self.chat_id)
        if chat["project_id"]:
            sources += self.session_store.attachments(project_id=chat["project_id"])
        for data in sources:
            item = QListWidgetItem(data["name"] + " · " + data["kind"])
            item.setData(Qt.UserRole, data); self.sources.addItem(item)
        remembered_sources = self.packet.get("sources", [])
        if not remembered_sources:
            for message in reversed(self.session_store.messages(self.chat_id)):
                if message["role"] == "assistant":
                    remembered_sources = message["metadata"].get("sources", [])
                    break
        for data in remembered_sources:
            if not any(s["id"] == data["id"] for s in sources):
                item = QListWidgetItem(data["name"]); item.setData(Qt.UserRole, data); self.sources.addItem(item)

    def source_selected(self, item, previous=None):
        if item:
            data = item.data(Qt.UserRole)
            self.source_text.setPlainText(data["name"] + "\n" + data.get("notice", "") + "\n\n" + data.get("content", data.get("excerpt", "Image attachment")))

    def quick_stats(self):
        item = self.sources.currentItem()
        if not item:
            return
        try:
            data = self.session_store.attachment(item.data(Qt.UserRole)["id"])
            self.source_text.setPlainText(json.dumps(table_summary(data), indent=2, ensure_ascii=False))
        except (ValueError, KeyError) as exc:
            self.status.setText(str(exc))

    def toggle_inspector(self):
        if self.inspector.isVisible():
            self.inspector.hide()
            if self.inspector_dialog is not None:
                self.inspector_dialog.hide()
        else:
            self.show_inspector()

    def show_inspector(self, index=None):
        if self.width() < 1050:
            if self.inspector_dialog is None:
                self.inspector_dialog = QDialog(self)
                self.inspector_dialog.setWindowTitle("Apollo · Canvas, sources and activity")
                self.inspector_dialog.resize(650, 650)
                QVBoxLayout(self.inspector_dialog)
            self.inspector_dialog.layout().addWidget(self.inspector)
            self.inspector_dialog.show(); self.inspector.show()
        else:
            if self.inspector.parent() is not self.splitter:
                if self.inspector_dialog is not None:
                    self.inspector_dialog.hide()
                self.splitter.addWidget(self.inspector)
            self.inspector.show()
        if index is not None:
            self.inspector.setCurrentIndex(index)

    def toggle_navigation(self):
        self._nav_choice = not self.navigation.isVisible()
        self.navigation.setVisible(self._nav_choice)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "navigation"):
            self.navigation.setVisible(self._nav_choice if self._nav_choice is not None else self.width() >= 1000)
            self.tagline.setVisible(self.width() >= 1000)

    def save_canvas(self):
        name, _ = QFileDialog.getSaveFileName(self, "Save canvas", "Apollo_Canvas.md", "Markdown (*.md);;Text (*.txt);;Word (*.docx);;PDF (*.pdf);;CSV table to Excel (*.xlsx);;All files (*)")
        if name:
            try:
                export_canvas(name, self.canvas.toPlainText())
                self.status.setText("Saved " + Path(name).name)
            except (ValueError, OSError, ImportError) as exc:
                self.status.setText("Export failed: " + str(exc))

    def apps_menu(self):
        menu = QMenu(self)
        for title, key in (("Knowledge & memory", "memory_bank"), ("Voice", "voice_center"),
                           ("Foundry", "project_studio"), ("Missions", "mission_control"),
                           ("Vision", "visual_learning"), ("Files", "file_manager"), ("Updates", "update_manager")):
            action = menu.addAction(title)
            record = self.owner.module_manager.get_module(key)
            action.setEnabled(bool(record and record.get("enabled")))
            action.triggered.connect(lambda checked=False, module=key: self.owner.open_module_app(module))
        menu.exec(self.connection_label.mapToGlobal(self.connection_label.rect().bottomRight()))

    def prompt_menu(self):
        menu = QMenu(self)
        for name, prompt in (("Explain", "Explain this clearly with an example:\n"),
                ("Research brief", "Research this question and cite the sources you actually use:\n"),
                ("Review code", "Review the attached code for bugs and explain the evidence:\n"),
                ("Analyse data", "Analyse the attached data. State the calculations and limitations.\n"),
                ("Experiment plan", "Plan a reproducible simulation with assumptions and measurable success criteria:\n")):
            menu.addAction(name).triggered.connect(lambda checked=False, text=prompt: self.composer.setText(text))
        menu.exec(self.composer.mapToGlobal(self.composer.rect().topLeft()))

    def _set_busy(self, busy):
        self.busy = bool(busy)
        enabled = not self.busy and not self.io_busy
        for widget in (self.chats, self.new_button, self.temporary_button, self.attach_button,
                       self.remove_file_button, self.models, self.mode, self.style, self.send_button):
            widget.setEnabled(enabled)
        self.composer.setReadOnly(not enabled)
        self.stop_button.setEnabled(self.busy and not self._cancel_requested)
        self.owner.chat_busy = self.busy

    def send(self):
        if self.busy or self.io_busy:
            return
        question = self.composer.text().strip()
        if not question and self.pending_attachments:
            question = "Describe and help me understand the attached files."
        if not question:
            return
        if self.mode.currentText() == "Web research" and not self.tools_check.isChecked():
            self.status.setText("Enable Tools for web research, or choose Chat for a model-only answer.")
            return
        if sum(self.session_store.attachment(i)["kind"] == "image" for i in self.pending_attachments) > 4:
            self.status.setText("Send up to four image attachments per message.")
            return
        self.save_options(); self.draft_timer.stop()
        chat = self.session_store.chat(self.chat_id)
        metadata = {"attachments": list(self.pending_attachments)}
        self.session_store.add_message(self.chat_id, "user", question, metadata=metadata)
        self.pending_attachments = []; self.refresh_attachments()
        memory = None
        if chat["memory"] and not self.session_store.temporary:
            record = self.owner.module_manager.get_module("memory_bank")
            if record and record.get("enabled"):
                try:
                    memory = self.owner.module_manager.execute("memory_bank", "knowledge_context", {"query": question, "limit": 4, "max_chars": 3000})
                except Exception as exc:
                    self.status.setText("Saved memory unavailable: " + str(exc)[:140])
            if chat["tools"] and hasattr(self.owner, "_apply_integrated_chat_learning"):
                self.owner._apply_integrated_chat_learning(question)
        config = self.owner.config
        self.packet = build_chat_context(self.session_store, self.chat_id, question,
            personality_instruction(config.get("sarcasm_level", 2)), memory,
            max_chars=max(6000, int(config.get("num_ctx", 8192)) * 3),
            canvas=self.canvas.toPlainText(), canvas_enabled=self.include_canvas.isChecked())
        mode = self.mode.currentText()
        if mode == "Web research":
            self.packet["messages"][-1]["content"] = "Search the web and cite real sources for this request: " + self.packet["messages"][-1]["content"]
        elif mode == "Coding":
            self.packet["messages"][-1]["content"] = "Coding workspace request: " + self.packet["messages"][-1]["content"]
        elif mode == "Analyse files":
            self.packet["messages"][0]["content"] += "\nExplain data calculations. Do not claim to execute Python unless an actual sandbox/tool result supports it."
        client = OllamaClient(config["ollama_url"], self.models.currentText().strip() or config["model"],
            config.get("temperature", 0.65), config.get("num_ctx", 8192), config.get("num_batch", 256), config.get("keep_alive", "5m"))
        client.strict_model = True
        self.turn_client = client
        self.current_text = ""; self.rendered_stream = ""; self.activities = []
        self._cancel_requested = False; self._started = time.monotonic(); self._last_checkpoint = self._started
        self.answer_id = self.session_store.add_message(self.chat_id, "assistant", "", "streaming", {"model": client.model})
        self._loading = True; self.composer.clear(); self._loading = False
        self.session_store.update_chat(self.chat_id, draft="")
        self._set_busy(True); self.render(); self.refresh_sources(); self.refresh_chats()
        self.activity.setPlainText("Started model: " + client.model)
        self.status.setText("Working · " + str(self.packet["history_messages"]) + " earlier messages · " + str(len(self.packet["sources"])) + " sources" +
            (" · " + " ".join(self.packet["warnings"]) if self.packet["warnings"] else ""))
        manager = ScopedChatManager(self.owner.module_manager) if chat["tools"] and not self.session_store.temporary else None
        self.task = ChatTask(client, self.packet["messages"], manager)
        self.owner.chat_task = self.task
        self.task.signals.chunk.connect(self.on_chunk, Qt.QueuedConnection)
        self.task.signals.finished.connect(self.on_finished, Qt.QueuedConnection)
        self.task.signals.failed.connect(self.on_failed, Qt.QueuedConnection)
        self.task.signals.tool_used.connect(self.on_tool, Qt.QueuedConnection)
        self.task.signals.tool_started.connect(self.on_tool_started, Qt.QueuedConnection)
        self.task.signals.completed.connect(self.on_completed, Qt.QueuedConnection)
        self.stream_timer.start(); self.owner.thread_pool.start(self.task)

    @Slot(str)
    def on_chunk(self, chunk):
        if not self._cancel_requested:
            self.current_text += chunk

    def _flush_stream(self):
        if not self.answer_id or not self.busy:
            return
        delta = self.current_text[len(self.rendered_stream):]
        if delta:
            bar = self.transcript.verticalScrollBar(); follow = bar.value() >= bar.maximum() - 40
            cursor = QTextCursor(self.transcript.document()); cursor.movePosition(QTextCursor.End); cursor.insertText(delta)
            self.rendered_stream = self.current_text
            if follow:
                bar.setValue(bar.maximum())
        if time.monotonic() - self._last_checkpoint >= 0.6:
            self.session_store.update_message(self.answer_id, self.current_text, "streaming", self._turn_metadata())
            self._last_checkpoint = time.monotonic()

    def _turn_metadata(self):
        return {"model": self.turn_client.model, "elapsed_seconds": round(time.monotonic() - self._started, 2),
                "metrics": self.turn_client.last_metrics, "tools": self.activities,
                "sources": self.packet.get("sources", []), "warnings": self.packet.get("warnings", [])}

    @Slot(str)
    def on_finished(self, answer):
        self.current_text = str(answer or self.current_text).strip() or "The model returned no response."
        self.session_store.update_message(self.answer_id, self.current_text, "complete", self._turn_metadata())
        if not self.session_store.temporary:
            if hasattr(self.owner, "hub_recent_chat"):
                self.owner.hub_recent_chat.setText("Apollo: " + self.current_text[:220])
            self.owner.speak_apollo_reply(self.current_text)

    @Slot(str)
    def on_failed(self, error):
        self.current_text = self.current_text or ("Request failed: " + str(error))
        self.session_store.update_message(self.answer_id, self.current_text, "failed", self._turn_metadata())
        self.status.setText(str(error))

    @Slot(str)
    def on_tool_started(self, name):
        self.status.setText("Running " + name.replace("__", ".") + " · Stop waits for an active tool to reach its next boundary")

    @Slot(str, str)
    def on_tool(self, name, result):
        try:
            payload = json.loads(result)
        except ValueError:
            payload = result
        self.activities.append({"tool": name, "result": str(result)[:10000]})
        self.activities = self.activities[-40:]
        self.activity.setPlainText("\n\n".join(a["tool"] + "\n" + a["result"] for a in self.activities))
        chat = self.session_store.chat(self.chat_id)
        if chat["memory"] and not self.session_store.temporary and hasattr(self.owner, "_auto_bank_tool_result"):
            self.owner._auto_bank_tool_result(name, result)

    def stop(self):
        if self.task is not None and self.busy and not self._cancel_requested:
            self._cancel_requested = True; self.task.cancel(); self.stop_button.setEnabled(False)
            self.status.setText("Stopping generation; any active tool must finish its current operation.")

    @Slot()
    def on_completed(self):
        self.stream_timer.stop()
        if self._cancel_requested:
            self.session_store.update_message(self.answer_id, self.current_text, "stopped", self._turn_metadata())
        self.task = None; self.owner.chat_task = None
        self._set_busy(False); self.render(); self.refresh_chats()
        if self._cancel_requested:
            self.status.setText("Stopped · partial answer saved" if not self.session_store.temporary else "Stopped · temporary answer retained for this session")
        else:
            metrics = self.turn_client.last_metrics
            message = next((m for m in self.session_store.messages(self.chat_id) if m["id"] == self.answer_id), None)
            if message and message["status"] == "complete":
                self.status.setText(f"{self.turn_client.model} · {time.monotonic() - self._started:.1f}s" +
                    (f" · {metrics['eval_count']} output tokens" if "eval_count" in metrics else "") +
                    (" · Temporary" if self.session_store.temporary else " · Saved"))
        self.composer.setFocus()

    def _action(self, name, message_id, label):
        return f'<a style="color:#87cfbf;text-decoration:none" href="apollo://{name}/{message_id}?token={self._action_token}">{label}</a>'

    def render(self):
        messages = self.session_store.messages(self.chat_id)
        self._action_token = secrets.token_hex(16)
        chunks = []
        for message in messages:
            role = "You" if message["role"] == "user" else "Apollo"
            metadata = message["metadata"]
            badges = [metadata.get("model", ""), "" if message["status"] == "complete" else message["status"]]
            content = message["content"]
            # References become internal links only through this trusted renderer.
            body = markdown_html(content)
            body = re.sub(r"\[source:([a-f0-9]{32})\]", lambda m: self._action("source", m[1], "[source]"), body)
            body = re.sub(r"\[memory:(\d+)\]", lambda m: self._action("memory", m[1], "[memory:" + m[1] + "]"), body)
            actions = []
            if message["status"] != "streaming":
                actions += [self._action("copy", message["id"], "Copy")]
                if message["role"] == "user":
                    actions += [self._action("edit", message["id"], "Edit & branch")]
                else:
                    actions += [self._action("retry", message["id"], "Regenerate"),
                                self._action("canvas", message["id"], "Open in canvas")]
                    if not self.session_store.temporary:
                        actions += [self._action("speak", message["id"], "Read aloud")]
                    if re.search(r"```[^\n]*\n(.*?)```", content, re.S):
                        actions += [self._action("code", message["id"], "Copy code")]
            names = []
            for ident in metadata.get("attachments", []):
                try:
                    names.append(html.escape(self.session_store.attachment(ident)["name"]))
                except KeyError:
                    names.append("Removed attachment")
            chunks += [f'<div style="margin:14px 0;padding:12px;border-bottom:1px solid #214844;">'
                f'<p style="color:{"#b9d6ce" if role == "You" else "#70e2c4"};font-weight:bold">{role}'
                f' <span style="font-size:10px;color:#7e9e94;">{html.escape(" · ".join(b for b in badges if b))}</span></p>'
                + ("<p>📎 " + " · ".join(names) + "</p>" if names else "") + body +
                ("<p style='font-size:10px;color:#a9b7a0;'>" + html.escape(" ".join(metadata.get("warnings", []))) + "</p>"
                 if metadata.get("warnings") and message["status"] != "streaming" else "") +
                ("<p style='font-size:11px'>" + " &nbsp; · &nbsp; ".join(actions) + "</p>" if actions else "") + "</div>"]
        if not messages:
            chunks = ["<h2>What shall we work on?</h2><p>Ask a question, attach a file, start research, or build something in Foundry.</p><p>Your projects, conversations and editable work stay together here.</p>"]
        bar = self.transcript.verticalScrollBar(); old = bar.value(); follow = old >= bar.maximum() - 40
        self.transcript.setHtml("<html><body style='color:#e5f4ee;font-family:Segoe UI;font-size:14px;'>" + "".join(chunks) + "</body></html>")
        if follow or self.busy:
            bar.setValue(bar.maximum())
        else:
            bar.setValue(old)
        self.rendered_stream = "" if self.busy else self.current_text
        self.chat_title.setText(("Temporary · " if self.session_store.temporary else "") + self.session_store.chat(self.chat_id)["title"])

    def anchor_clicked(self, url):
        if url.scheme() in ("https", "http"):
            QDesktopServices.openUrl(url); return
        if url.scheme() != "apollo" or url.query() != "token=" + self._action_token or self.busy:
            return
        action, ident = url.host(), url.path().strip("/")
        if action in ("source", "memory"):
            source_id = "memory:" + ident if action == "memory" else ident
            for i in range(self.sources.count()):
                if self.sources.item(i).data(Qt.UserRole)["id"] == source_id:
                    self.show_inspector(1); self.sources.setCurrentRow(i); return
            return
        message = next((m for m in self.session_store.messages(self.chat_id) if m["id"] == ident), None)
        if message is None:
            return
        if action == "copy":
            QApplication.clipboard().setText(message["content"])
        elif action == "speak":
            self.owner.speak_apollo_reply(message["content"])
        elif action in ("canvas", "code"):
            blocks = re.findall(r"```[^\n]*\n(.*?)```", message["content"], re.S)
            text = blocks[0].rstrip() if blocks else message["content"]
            if action == "code":
                QApplication.clipboard().setText(text)
            else:
                if self.canvas.toPlainText().strip() and QMessageBox.question(self, "Replace canvas", "Replace the current canvas with this response?",
                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                    return
                self.canvas.setPlainText(text); self.show_inspector(0)
        elif action in ("edit", "retry"):
            self.branch_message(message, edit=action == "edit")

    def branch_message(self, message, edit=False):
        if self.busy or self.io_busy:
            return
        messages = self.session_store.messages(self.chat_id)
        if edit:
            question, ok = QInputDialog.getMultiLineText(self, "Edit & branch", "The original chat will be preserved:", message["content"])
            if not ok or not question.strip():
                return
            before = message["id"]
            source_message = message
        else:
            index = next(i for i, m in enumerate(messages) if m["id"] == message["id"])
            user = next((m for m in reversed(messages[:index]) if m["role"] == "user"), None)
            if not user:
                return
            question, before = user["content"], user["id"]
            source_message = user
        original_ids = source_message["metadata"].get("attachments", [])
        new_id, mapping = self.session_store.branch(self.chat_id, before, return_mapping=True)
        self.load_chat(new_id, self.session_store)
        self.pending_attachments = [mapping[ident] for ident in original_ids if ident in mapping]
        self.refresh_attachments()
        self.composer.setText(question); self.send()

    def copy_last(self):
        answers = [m for m in self.session_store.messages(self.chat_id) if m["role"] == "assistant"]
        if answers:
            QApplication.clipboard().setText(answers[-1]["content"])

    def prepare_close(self):
        if self.busy:
            self.stop(); return False
        if self.io_busy:
            self.status.setText("Finish reading the current files before closing."); return False
        self.draft_timer.stop(); self.save_draft()
        return True

    def close_store(self):
        self.draft_timer.stop(); self.stream_timer.stop()
        if self.project_dialog is not None:
            self.project_dialog.close()
        if self.inspector_dialog is not None:
            self.inspector_dialog.close()
        self.store.close()
        if self.temp_store is not None:
            self.temp_store.close()
