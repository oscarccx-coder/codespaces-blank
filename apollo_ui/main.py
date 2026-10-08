import html
import json
import os
import re
import sys
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None

from PySide6.QtCore import Qt, QThreadPool, QTimer, Slot, QUrl, QMimeData
from PySide6.QtGui import QFont, QIcon, QPainter, QColor, QDesktopServices, QKeySequence, QShortcut, QDrag
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QStackedWidget, QFrame, QLineEdit, QTextEdit, QGridLayout,
    QProgressBar, QListWidget, QListWidgetItem, QScrollArea, QMessageBox,
    QComboBox, QTextBrowser, QTabWidget, QInputDialog, QCheckBox, QDialog,
    QPlainTextEdit, QAbstractSpinBox, QSizePolicy, QAbstractItemView
)

from memory import MemoryStore
from ollama_client import OllamaClient
from workers import ChatTask, ModuleRepairTask, ModuleActionTask
from module_manager import ModuleManager
from module_repair_engine import ModuleRepairEngine
from apollo_runtime import ApolloRuntime
from apollo_shell import ApolloShell, VALID_TILE_SIZES, TILE_SPANS, HUB_COLUMNS, pack_tiles
from apollo_sidebar import SidebarLayoutStore
from apollo_docs import PatchDocs
from apollo_storage import StorageLayout


BASE_DIR = Path(__file__).resolve().parent
STORAGE = StorageLayout(BASE_DIR)
STORAGE.ensure_layout()
PATCH_DOCS = PatchDocs(BASE_DIR)
PATCH_DOCS.ensure_layout()


APP_STYLE = """
QWidget {
    background: #07191a;
    color: #d9f5ef;
    font-family: "Segoe UI";
    font-size: 13px;
}
QMainWindow {
    background: #061617;
}
QFrame#sidebar {
    background: #061416;
    border-right: 1px solid #0d3c39;
}
QFrame#card {
    background: #0a2223;
    border: 1px solid #135a53;
    border-radius: 14px;
}
QFrame#hero {
    background: #0b282a;
    border: 1px solid #147568;
    border-radius: 16px;
}
QFrame#hubTile {
    background: #092526;
    border: 1px solid #17675d;
    border-radius: 14px;
}
QFrame#hubTile:hover {
    border: 1px solid #2edbc2;
    background: #0b2e2e;
}
QFrame#hubEditGrid {
    background: #071d1e;
    border: 1px dashed #1d625b;
    border-radius: 13px;
}
QFrame#hubTileEdit {
    background: #0b292a;
    border: 2px solid #2abca9;
    border-radius: 14px;
}
QFrame#hubTileEdit:hover {
    background: #0d3434;
    border: 2px solid #5af5dc;
}
QFrame#hubResizeHandle {
    background: #52e6cf;
    border: 1px solid #d9fff8;
    border-radius: 4px;
}
QFrame#hubResizePreview {
    background: rgba(46, 219, 194, 32);
    border: 2px dashed #59f2da;
    border-radius: 13px;
}
QLabel#hubEditBadge {
    color: #9ff7e5;
    font-size: 10px;
    font-weight: 700;
}
QLabel#hubEditBanner {
    background: #0c3835;
    border: 1px solid #27cdb4;
    border-radius: 10px;
    color: #cffff6;
    padding: 9px 12px;
    font-weight: 700;
}
QLabel#hubTileTitle {
    color: #e9fffb;
    font-size: 15px;
    font-weight: 700;
}
QLabel#hubTileMeta {
    color: #71b9ad;
    font-size: 10px;
}
QPushButton {
    background: #0b2425;
    border: 1px solid #17675d;
    border-radius: 10px;
    padding: 10px 14px;
    color: #dffbf5;
}
QPushButton:hover {
    background: #0d3432;
    border: 1px solid #2edbc2;
}
QPushButton:pressed {
    background: #0c4941;
}
QPushButton#windowClose {
    background: #2a1418;
    border: 1px solid #74313c;
    color: #ffd9df;
    border-radius: 10px;
    padding: 0px;
    font-size: 17px;
    font-weight: 800;
}
QPushButton#windowClose:hover {
    background: #6b202e;
    border: 1px solid #ff6179;
    color: white;
}
QPushButton#nav {
    text-align: left;
    padding: 12px 14px;
    border: none;
    border-radius: 9px;
    background: transparent;
    font-size: 14px;
}
QPushButton#nav:hover {
    background: #0b2728;
}
QPushButton#nav:checked {
    background: #0c3935;
    border: 1px solid #24caae;
    color: #9ff7e5;
}
QLineEdit, QTextEdit, QPlainTextEdit, QTextBrowser, QComboBox, QAbstractSpinBox {
    background: #081f20;
    border: 1px solid #1b5a55;
    border-radius: 10px;
    padding: 8px 10px;
    color: #e5fffa;
    selection-background-color: #16786c;
    selection-color: #ffffff;
}
QLineEdit, QComboBox, QAbstractSpinBox {
    min-height: 24px;
}
QTextEdit, QPlainTextEdit {
    min-height: 72px;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QAbstractSpinBox:focus {
    border: 1px solid #35e1c6;
}
QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled, QAbstractSpinBox:disabled {
    color: #86aaa4;
    background: #07191a;
}
QLineEdit[readOnly="true"], QTextEdit[readOnly="true"], QPlainTextEdit[readOnly="true"] {
    color: #c7e8e2;
}
QProgressBar {
    background: #061617;
    border: 1px solid #1c4f4b;
    border-radius: 7px;
    text-align: center;
    height: 13px;
}
QProgressBar::chunk {
    background: #34d6b5;
    border-radius: 6px;
}
QListWidget {
    background: transparent;
    border: none;
}
QListWidget::item {
    background: #0a2021;
    border: 1px solid #104b46;
    border-radius: 8px;
    padding: 10px;
    margin: 4px;
}
QScrollArea {
    border: none;
}
QTabWidget::pane {
    border: 1px solid #135a53;
    border-radius: 10px;
    background: #07191a;
    top: -1px;
}
QTabBar::tab {
    background: #081f20;
    border: 1px solid #135a53;
    border-bottom: none;
    padding: 9px 16px;
    margin-right: 4px;
    color: #9fc8c1;
}
QTabBar::tab:selected {
    background: #0c3935;
    color: #9ff7e5;
    border-color: #24caae;
}
"""


def label(text, size=13, color="#d9f5ef", bold=False):
    w = QLabel(text)
    f = QFont("Segoe UI", size)
    f.setBold(bold)
    w.setFont(f)
    w.setStyleSheet(f"color: {color};")
    w.setWordWrap(True)
    return w


class Card(QFrame):
    def __init__(self, title=None):
        super().__init__()
        self.setObjectName("card")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(16, 14, 16, 14)
        self.layout.setSpacing(10)
        if title:
            self.layout.addWidget(label(title, 14, "#e9fffb", True))


HUB_MIME_TYPE = "application/x-apollo-hub-app"
HUB_CELL_HEIGHT = 118
HUB_GRID_SPACING = 10
MAX_EDIT_ROW_SPAN = 4


class HubDropGrid(QFrame):
    """A section-sized drop target used only while the Hub is in edit mode."""

    def __init__(self, section, move_callback, parent=None):
        super().__init__(parent)
        self.section = str(section or "Main")
        self.move_callback = move_callback
        self.setObjectName("hubEditGrid")
        self.setAcceptDrops(True)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(6, 6, 6, 6)
        self.grid.setHorizontalSpacing(HUB_GRID_SPACING)
        self.grid.setVerticalSpacing(HUB_GRID_SPACING)
        for column in range(HUB_COLUMNS):
            self.grid.setColumnStretch(column, 1)

        self.resize_preview = QFrame(self)
        self.resize_preview.setObjectName("hubResizePreview")
        self.resize_preview.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.preview_label = QLabel("", self.resize_preview)
        self.preview_label.setObjectName("hubEditBadge")
        self.preview_label.move(9, 7)
        self.resize_preview.hide()

    def set_row_count_hint(self, rows):
        rows = max(1, int(rows))
        for row in range(rows + 2):
            self.grid.setRowMinimumHeight(row, HUB_CELL_HEIGHT)
        self.setMinimumHeight(
            rows * HUB_CELL_HEIGHT
            + max(0, rows - 1) * HUB_GRID_SPACING
            + 12
        )

    def _fallback_cell(self, point):
        usable_width = max(1, self.width() - 12)
        cell_width = max(1, (usable_width - (HUB_COLUMNS - 1) * HUB_GRID_SPACING) / HUB_COLUMNS)
        x = max(0.0, float(point.x()) - 6.0)
        y = max(0.0, float(point.y()) - 6.0)
        col = int(x / max(1.0, cell_width + HUB_GRID_SPACING))
        row = int(y / max(1.0, HUB_CELL_HEIGHT + HUB_GRID_SPACING))
        return max(0, row), max(0, min(HUB_COLUMNS - 1, col))

    def cell_from_point(self, point):
        # QGridLayout.cellRect gives the most accurate answer after layout. Fall
        # back to deterministic grid maths below the currently occupied area.
        rows = max(self.grid.rowCount(), 1)
        for row in range(rows + MAX_EDIT_ROW_SPAN + 2):
            for col in range(HUB_COLUMNS):
                rect = self.grid.cellRect(row, col)
                if rect.isValid() and rect.contains(point):
                    return row, col
        return self._fallback_cell(point)

    def _rect_for_cells(self, row, col, row_span, col_span):
        first = self.grid.cellRect(row, col)
        last = self.grid.cellRect(row + row_span - 1, col + col_span - 1)
        if first.isValid() and last.isValid():
            return first.united(last)

        usable_width = max(1, self.width() - 12)
        cell_width = max(1, int((usable_width - (HUB_COLUMNS - 1) * HUB_GRID_SPACING) / HUB_COLUMNS))
        x = 6 + col * (cell_width + HUB_GRID_SPACING)
        y = 6 + row * (HUB_CELL_HEIGHT + HUB_GRID_SPACING)
        width = col_span * cell_width + max(0, col_span - 1) * HUB_GRID_SPACING
        height = row_span * HUB_CELL_HEIGHT + max(0, row_span - 1) * HUB_GRID_SPACING
        from PySide6.QtCore import QRect
        return QRect(x, y, width, height)

    def show_resize_preview(self, row, col, row_span, col_span):
        rect = self._rect_for_cells(row, col, row_span, col_span)
        self.resize_preview.setGeometry(rect)
        self.preview_label.setText(f"{col_span} × {row_span}")
        self.preview_label.adjustSize()
        self.resize_preview.show()
        self.resize_preview.raise_()

    def clear_resize_preview(self):
        self.resize_preview.hide()

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(HUB_MIME_TYPE):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(HUB_MIME_TYPE):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(HUB_MIME_TYPE):
            event.ignore()
            return
        try:
            app_id = bytes(event.mimeData().data(HUB_MIME_TYPE)).decode("utf-8")
        except Exception:
            event.ignore()
            return
        row, col = self.cell_from_point(event.position().toPoint())
        self.move_callback(app_id, self.section, row, col)
        event.acceptProposedAction()


class HubResizeHandle(QFrame):
    def __init__(self, tile, corner):
        super().__init__(tile)
        self.tile = tile
        self.corner = corner
        self.setObjectName("hubResizeHandle")
        self.setFixedSize(14, 14)
        if corner in {"nw", "se"}:
            self.setCursor(Qt.SizeFDiagCursor)
        else:
            self.setCursor(Qt.SizeBDiagCursor)
        self.setToolTip("Drag corner to resize this app tile")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.tile.begin_corner_resize(self.corner)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self.tile.update_corner_resize(event.globalPosition().toPoint())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.tile.finish_corner_resize(event.globalPosition().toPoint())
            event.accept()
            return
        super().mouseReleaseEvent(event)


class HubEditableTile(QFrame):
    """Direct-manipulation Hub tile: drag the body, resize from any corner."""

    def __init__(
        self,
        app_id,
        section,
        grid_host,
        row,
        col,
        row_span,
        col_span,
        resize_callback,
        parent=None,
    ):
        super().__init__(parent)
        self.app_id = str(app_id)
        self.section = str(section or "Main")
        self.grid_host = grid_host
        self.grid_row = int(row)
        self.grid_col = int(col)
        self.row_span = int(row_span)
        self.col_span = int(col_span)
        self.resize_callback = resize_callback
        self._drag_start = None
        self._resize_corner = None
        self._pending_resize = None
        self.setObjectName("hubTileEdit")
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip("Drag to move. Drag any corner handle to resize.")
        self.handles = [HubResizeHandle(self, corner) for corner in ("nw", "ne", "sw", "se")]

    def resizeEvent(self, event):
        super().resizeEvent(event)
        m = 4
        s = 14
        positions = {
            "nw": (m, m),
            "ne": (max(m, self.width() - s - m), m),
            "sw": (m, max(m, self.height() - s - m)),
            "se": (max(m, self.width() - s - m), max(m, self.height() - s - m)),
        }
        for handle in self.handles:
            x, y = positions[handle.corner]
            handle.move(x, y)
            handle.raise_()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._resize_corner is None:
            self._drag_start = event.position().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            self._drag_start is not None
            and event.buttons() & Qt.LeftButton
            and (event.position().toPoint() - self._drag_start).manhattanLength()
                >= QApplication.startDragDistance()
        ):
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData(HUB_MIME_TYPE, self.app_id.encode("utf-8"))
            drag.setMimeData(mime)
            pixmap = self.grab()
            drag.setPixmap(pixmap)
            drag.setHotSpot(self._drag_start)
            self._drag_start = None
            drag.exec(Qt.MoveAction)
            self.setCursor(Qt.OpenHandCursor)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start = None
        self.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def begin_corner_resize(self, corner):
        self._resize_corner = corner
        self._pending_resize = (
            self.grid_row,
            self.grid_col,
            self.row_span,
            self.col_span,
        )
        self.grid_host.show_resize_preview(*self._pending_resize)

    def _resize_rectangle_for_target(self, target_row, target_col):
        top = self.grid_row
        left = self.grid_col
        bottom = self.grid_row + self.row_span - 1
        right = self.grid_col + self.col_span - 1
        corner = self._resize_corner

        if corner == "se":
            bottom = max(top, target_row)
            right = max(left, target_col)
        elif corner == "sw":
            bottom = max(top, target_row)
            left = min(right, target_col)
        elif corner == "ne":
            top = min(bottom, target_row)
            right = max(left, target_col)
        elif corner == "nw":
            top = min(bottom, target_row)
            left = min(right, target_col)

        top = max(0, top)
        left = max(0, min(HUB_COLUMNS - 1, left))
        bottom = max(top, min(top + MAX_EDIT_ROW_SPAN - 1, bottom))
        right = max(left, min(HUB_COLUMNS - 1, right))

        row_span = max(1, min(MAX_EDIT_ROW_SPAN, bottom - top + 1))
        col_span = max(1, min(HUB_COLUMNS, right - left + 1))
        if left + col_span > HUB_COLUMNS:
            left = HUB_COLUMNS - col_span
        return top, left, row_span, col_span

    def update_corner_resize(self, global_point):
        if self._resize_corner is None:
            return
        local = self.grid_host.mapFromGlobal(global_point)
        target_row, target_col = self.grid_host.cell_from_point(local)
        self._pending_resize = self._resize_rectangle_for_target(target_row, target_col)
        self.grid_host.show_resize_preview(*self._pending_resize)

    def finish_corner_resize(self, global_point):
        if self._resize_corner is None:
            return
        self.update_corner_resize(global_point)
        pending = self._pending_resize
        self._resize_corner = None
        self._pending_resize = None
        self.grid_host.clear_resize_preview()
        if pending:
            self.resize_callback(
                self.app_id,
                self.section,
                pending[0],
                pending[1],
                pending[2],
                pending[3],
            )


class ApolloWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.config = json.loads(
            (BASE_DIR / "config.json").read_text(encoding="utf-8")
        )

        self.memory = MemoryStore(STORAGE.database(self.config["database"]))
        self.client = OllamaClient(
            self.config["ollama_url"],
            self.config["model"],
            self.config.get("temperature", 0.65),
            self.config.get("num_ctx", 8192),
        )

        # Apollo 7.5 shared runtime: permission gate, action/event bus, blackboard,
        # task journal, notifications and recovery state.
        self.runtime = ApolloRuntime(BASE_DIR)

        # Plug-in architecture: every subfolder under modules/ can add features.
        self.module_manager = ModuleManager(
            BASE_DIR / "modules",
            STORAGE.state_file("modules_state.json"),
            context={
                "base_dir": str(BASE_DIR),
                "runtime": self.runtime,
                "safe_mode": os.environ.get("APOLLO_SAFE_MODE") == "1",
            },
            pending_dir=BASE_DIR / "pending_modules",
            validator_path=BASE_DIR / "module_validator.py",
        )
        self.module_manager.reload()
        self.runtime.attach_manager(self.module_manager)

        # Apollo 7.5.11 OS shell backbone: core pages and module UIs are now
        # represented by one logical app registry with a persistent custom Hub.
        self.shell = ApolloShell(BASE_DIR, self.module_manager)
        self.sidebar_state = SidebarLayoutStore(BASE_DIR)
        self.hub_manager_dialog = None
        self.hub_edit_mode = False

        self.module_repair_engine = ModuleRepairEngine(
            self.client,
            self.module_manager,
            BASE_DIR,
        )
        self.module_repair_task = None
        self.web_task = None
        self.web_last_result = None

        self.dynamic_module_pages = {}
        self.dynamic_sidebar_buttons = {}
        self.dynamic_app_buttons = {}
        self.current_app_module_id = None
        self.current_app_open = False
        self.neural_train_task = None

        self.ui_state_path = STORAGE.state_file("ui_state.json")
        self.ui_state = self._load_ui_state()
        self.ui_save_timer = QTimer(self)
        self.ui_save_timer.setSingleShot(True)
        self.ui_save_timer.setInterval(250)
        self.ui_save_timer.timeout.connect(self._save_ui_state)

        self.chat_history = []
        self.chat_display_messages = []
        self._restore_persistent_chat_history()
        self.current_stream_text = ""
        self.pending_user_text = None
        self.pending_learning_events = []
        self.chat_task = None
        self.chat_busy = False

        speech_state = self.ui_state.get("speech", {}) if isinstance(self.ui_state, dict) else {}
        self.speech_muted = bool(speech_state.get("muted", False))
        self.speech_task = None
        self.stt_task = None

        # Use Qt's managed thread pool instead of manually owning QThread objects.
        # This removes the QThread destruction/lifecycle failure mode entirely.
        self.thread_pool = QThreadPool(self)
        self.thread_pool.setMaxThreadCount(2)

        self.setWindowTitle("Apollo")
        self.setMinimumSize(1100, 700)
        saved_window = self.ui_state.get("window", {})
        try:
            self.setGeometry(
                int(saved_window.get("x", 80)),
                int(saved_window.get("y", 80)),
                max(1100, int(saved_window.get("width", 1500))),
                max(700, int(saved_window.get("height", 900))),
            )
        except Exception:
            self.resize(1500, 900)

        self.setStyleSheet(APP_STYLE)

        self._build_ui()
        self.rebuild_module_ui()
        self._restore_ui_state()

        self.command_palette_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        self.command_palette_shortcut.activated.connect(self.open_command_palette)

        self.neural_progress_timer = QTimer(self)
        self.neural_progress_timer.setInterval(250)
        self.neural_progress_timer.timeout.connect(self.refresh_neural_status)

        self.gpu_timer = QTimer(self)
        self.gpu_timer.setInterval(2000)
        self.gpu_timer.timeout.connect(self.refresh_gpu_status)
        self.gpu_timer.start()
        self._setup_timer()
        self.automation_timer = QTimer(self)
        self.automation_timer.setInterval(30000)
        self.automation_timer.timeout.connect(self.run_due_automations)
        self.automation_timer.start()

        self.background_intelligence_timer = QTimer(self)
        self.background_intelligence_timer.setInterval(300000)
        self.background_intelligence_timer.timeout.connect(self.run_background_maintenance)
        self.background_intelligence_timer.start()
        QTimer.singleShot(4000, self.run_background_maintenance)

        self.refresh_status()
        self.refresh_memory()
        self.refresh_stats()

    def _restore_persistent_chat_history(self):
        """Restore a compact recent conversation window after Apollo restarts."""
        try:
            record = self.module_manager.get_module("chat_memory_module")
            if not (
                record
                and record.get("enabled")
                and record.get("instance") is not None
            ):
                return

            result = self.module_manager.execute(
                "chat_memory_module",
                "conversation_context",
                {
                    "query": "",
                    "recent_limit": 6,
                    "related_limit": 0,
                    "max_chars": 7000,
                },
            )
            restored = []
            for item in result.get("recent", []) if isinstance(result, dict) else []:
                user_text = str(item.get("user_text", "")).strip()
                assistant_text = str(item.get("assistant_text", "")).strip()
                if user_text:
                    restored.append({"role": "user", "content": user_text[:1400]})
                if assistant_text:
                    restored.append({"role": "assistant", "content": assistant_text[:1400]})
            self.chat_history = restored[-12:]
        except Exception:
            self.chat_history = []

    def _load_ui_state(self):
        if not self.ui_state_path.exists():
            return {}
        try:
            data = json.loads(self.ui_state_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _queue_ui_state_save(self):
        if hasattr(self, "ui_save_timer"):
            self.ui_save_timer.start()

    def _current_page_key(self):
        if not hasattr(self, "stack"):
            return "Hub"
        current = self.stack.currentWidget()
        for key, widget in self.pages.items():
            if widget is current:
                return key
        return "Hub"

    def _save_ui_state(self):
        if not hasattr(self, "pages"):
            return
        selected_module = self._selected_module_id() if hasattr(self, "modules_list") else None
        selected_pending = self._selected_pending_id() if hasattr(self, "pending_modules_list") else None
        state = {
            "version": 1,
            "current_page": self._current_page_key(),
            "settings_tab": (
                self.settings_tabs.currentIndex()
                if hasattr(self, "settings_tabs")
                else 0
            ),
            "current_app_module": self.current_app_module_id,
            "current_app_open": bool(self.current_app_open),
            "selected_module": selected_module,
            "selected_pending_module": selected_pending,
            "speech": {
                "muted": bool(getattr(self, "speech_muted", False)),
            },
            "window": {
                "x": self.x(),
                "y": self.y(),
                "width": self.width(),
                "height": self.height(),
            },
        }
        self.ui_state = state
        self.ui_state_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.ui_state_path.with_suffix(self.ui_state_path.suffix + ".tmp")
        temp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        temp.replace(self.ui_state_path)

    def _restore_ui_state(self):
        state = self.ui_state or {}
        app_id = state.get("current_app_module")
        app_open = bool(state.get("current_app_open", False))
        self.current_app_open = False

        if app_id and app_open and hasattr(self, "apps_list"):
            for i in range(self.apps_list.count()):
                item = self.apps_list.item(i)
                if item.data(Qt.UserRole) == app_id:
                    item.setSelected(True)
                    self.open_selected_app_module(item)
                    break
        elif hasattr(self, "apps_host"):
            self.close_current_app(save_state=False)

        module_id = state.get("selected_module")
        if module_id and hasattr(self, "modules_list"):
            for i in range(self.modules_list.count()):
                item = self.modules_list.item(i)
                if item.data(Qt.UserRole) == module_id:
                    item.setSelected(True)
                    break

        pending_id = state.get("selected_pending_module")
        if pending_id and hasattr(self, "pending_modules_list"):
            for i in range(self.pending_modules_list.count()):
                item = self.pending_modules_list.item(i)
                if item.data(Qt.UserRole) == pending_id:
                    item.setSelected(True)
                    break

        page = state.get("current_page", "Hub")
        legacy_apps_page = (
            page == "Apps"
        )

        if legacy_apps_page:
            page = "Settings"

        if page not in self.pages:
            page = "Hub"

        self.switch_page(page)

        if hasattr(self, "settings_tabs"):
            if legacy_apps_page:
                self.settings_tabs.setCurrentWidget(
                    self.settings_apps_tab
                )
            elif page == "Settings":
                try:
                    tab_index = int(
                        state.get(
                            "settings_tab",
                            0,
                        )
                    )
                except Exception:
                    tab_index = 0

                tab_index = max(
                    0,
                    min(
                        self.settings_tabs.count() - 1,
                        tab_index,
                    ),
                )
                self.settings_tabs.setCurrentIndex(
                    tab_index
                )

    def moveEvent(self, event):
        super().moveEvent(event)
        self._queue_ui_state_save()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._queue_ui_state_save()

    def open_command_palette(self):
        text, ok = QInputDialog.getText(
            self,
            "Apollo Command Palette",
            "Command (chat, workshop, modules, system, memory, settings, control, snapshot):",
        )
        if not ok:
            return
        command = text.strip().lower()
        mapping = {
            "chat": "Chat",
            "workshop": "Coding",
            "coding": "Coding",
            "modules": "Modules",
            "system": "System",
            "memory": "Memory",
            "settings": "Settings",
            "hub": "Hub",
        }
        if command in mapping:
            self.switch_page(mapping[command])
            return
        if command in {"edit hub", "edit layout", "customise hub", "customize hub"}:
            self.switch_page("Hub")
            self.toggle_hub_edit_mode(True)
            return
        if command in {"manage hub", "hub manager", "apps manager"}:
            self.open_hub_manager()
            return
        if command in {"control", "control center", "permissions"}:
            self.open_module_app("core_services")
            return
        if command in {"notifications", "notification center"}:
            self.open_module_app("notification_center")
            return
        if command in {"workspace", "projects"}:
            self.open_module_app("workspace_manager")
            return
        if command in {"files", "file manager", "explorer"}:
            record = self.module_manager.get_module("file_manager")
            if record and self.module_manager.get_ui_placement("file_manager") == "sidebar":
                page = self.dynamic_module_pages.get("file_manager")
                if page is not None:
                    self.stack.setCurrentWidget(page)
                    self._queue_ui_state_save()
                    return
            self.open_module_app("file_manager")
            return
        if command in {"tasks", "plans"}:
            self.open_module_app("task_engine")
            return
        if command in {"activity", "trace"}:
            self.open_module_app("activity_trace")
            return
        if command in {"knowledge graph", "graph"}:
            self.open_module_app("knowledge_graph")
            return
        if command in {"benchmark", "benchmarks"}:
            self.open_module_app("benchmark_suite")
            return
        if command in {"models", "model runtime"}:
            self.open_module_app("model_runtime")
            return
        if command == "snapshot":
            try:
                file_path = self.runtime.create_snapshot("command_palette")
                QMessageBox.information(self, "Apollo Recovery", file_path)
            except Exception as exc:
                QMessageBox.warning(self, "Apollo Recovery", str(exc))
            return
        QMessageBox.information(
            self,
            "Apollo Command Palette",
            "Unknown command. Try: chat, workshop, modules, system, memory, settings, manage hub, control, notifications, files, workspace, tasks, activity, graph, benchmarks, models, snapshot.",
        )

    def run_due_automations(self):
        try:
            record = self.module_manager.get_module("automation_engine")
            if record and record.get("enabled") and record.get("instance") is not None:
                self.module_manager.execute("automation_engine", "run_due", {})
        except Exception:
            # Background automation failures are already recorded on the event/task bus.
            pass

    def run_background_maintenance(self):
        try:
            record = self.module_manager.get_module("background_intelligence")
            if record and record.get("enabled") and record.get("instance") is not None:
                self.module_manager.execute("background_intelligence", "maintenance_pulse", {})
        except Exception:
            pass

    def _client_for_chat_text(self, text):
        """Return a client using Apollo 7.5 deterministic role/profile routing."""
        if not bool(self.config.get("auto_model_routing", False)):
            return self.client

        try:
            record = self.module_manager.get_module("model_runtime")
            if not record or not record.get("enabled") or record.get("instance") is None:
                return self.client
            routed = self.module_manager.execute("model_runtime", "route_task", {"text": text})
            model = str(routed.get("model") or "").strip()
            if not model:
                return self.client
            temperature = float(routed.get("temperature", self.config.get("temperature", 0.65)))
            num_ctx = int(routed.get("num_ctx", self.config.get("num_ctx", 8192)))
            if (
                model == self.config.get("model")
                and temperature == float(self.config.get("temperature", 0.65))
                and num_ctx == int(self.config.get("num_ctx", 8192))
            ):
                return self.client
            return OllamaClient(self.config["ollama_url"], model, temperature, num_ctx)
        except Exception:
            return self.client

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(18, 14, 18, 14)
        right_layout.setSpacing(12)

        right_layout.addWidget(self._build_topbar())

        self.stack = QStackedWidget()
        self.pages = {}

        self.pages["Hub"] = self._build_hub()
        self.pages["Chat"] = self._build_chat()
        self.pages["Medical"] = self._build_medical()
        self.pages["Train"] = self._build_train()
        self.pages["Web"] = self._build_web()
        self.pages["Coding"] = self._build_coding()
        self.pages["Modules"] = self._build_modules()
        self.pages["System"] = self._build_system()
        self.pages["Memory"] = self._build_memory()
        self.pages["Settings"] = self._build_settings()

        for name in [
            "Hub", "Chat", "Medical", "Train", "Web",
            "Coding", "Modules", "System", "Memory", "Settings"
        ]:
            self.stack.addWidget(self.pages[name])

        right_layout.addWidget(self.stack, 1)
        root.addWidget(right, 1)

    def _build_sidebar(self):
        side = QFrame()
        side.setObjectName("sidebar")
        self.sidebar_frame = side

        v = QVBoxLayout(side)
        self.sidebar_layout = v
        v.setContentsMargins(10, 16, 10, 12)
        v.setSpacing(7)

        self.sidebar_logo = label("△  A P O L L O", 20, "#dffbf5", True)
        v.addWidget(self.sidebar_logo)
        self.sidebar_tagline = label(
            "Adaptive Personal Orchestrated\nLearning & Logic Overseer",
            9, "#8bbab3"
        )
        v.addWidget(self.sidebar_tagline)
        v.addSpacing(12)

        self.sidebar_default_labels = {
            "Hub": "Home", "Chat": "Chat", "Medical": "Medical",
            "Train": "Train", "Web": "Web", "Coding": "Workshop",
            "Modules": "Modules", "System": "System", "Memory": "Memory",
            "Settings": "Settings",
        }
        self.sidebar_icons = {
            "Hub": "⌂", "Chat": "▣", "Medical": "✚", "Train": "◈",
            "Web": "◎", "Coding": "</>", "Modules": "◇", "System": "▤",
            "Memory": "◉", "Settings": "⚙",
        }
        self.nav_buttons = {}
        for name in ("Hub", "Chat", "Medical", "Train", "Web",
                     "Coding", "Modules", "System", "Memory", "Settings"):
            b = QPushButton()
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setMinimumHeight(34)
            b.clicked.connect(lambda checked=False, n=name: self.switch_page(n))
            self.nav_buttons[name] = b

        # Permanent Home: it cannot be hidden, renamed or moved.
        v.addWidget(self.nav_buttons["Hub"])

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: 0px; }")
        self.sidebar_nav_host = QWidget()
        self.sidebar_nav_host.setStyleSheet("background: transparent;")
        self.sidebar_nav_layout = QVBoxLayout(self.sidebar_nav_host)
        self.sidebar_nav_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_nav_layout.setSpacing(5)
        self.sidebar_nav_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(self.sidebar_nav_host)
        v.addWidget(scroll, 1)

        # Preserve the established dynamic module UI hooks, but use the same
        # reorderable host as the built-in pages.
        self.dynamic_nav_host = self.sidebar_nav_host
        self.dynamic_nav_layout = self.sidebar_nav_layout

        self.sidebar_customize_btn = QPushButton("⚙  Customise Sidebar")
        self.sidebar_customize_btn.setToolTip("Reorder, rename or hide navigation items")
        self.sidebar_customize_btn.clicked.connect(self.open_sidebar_manager)
        v.addWidget(self.sidebar_customize_btn)

        # Permanent Settings: it cannot be hidden, renamed or moved.
        v.addWidget(self.nav_buttons["Settings"])
        self.sidebar_privacy_label = label("Local. Private. Yours.", 10, "#8cc7be")
        v.addWidget(self.sidebar_privacy_label)
        self.nav_buttons["Hub"].setChecked(True)
        self._refresh_sidebar()
        return side

    def _refresh_sidebar(self):
        if not hasattr(self, "sidebar_nav_layout"):
            return

        ordered = self.sidebar_state.ordered(self.nav_buttons.keys())
        # Remove layout references, not the widgets or their signal connections.
        while self.sidebar_nav_layout.count():
            self.sidebar_nav_layout.takeAt(0)

        collapsed = bool(self.sidebar_state.state()["collapsed"])
        width = 76 if collapsed else self.sidebar_state.state()["width"]
        self.sidebar_frame.setFixedWidth(width)
        self.sidebar_logo.setText("△" if collapsed else "△  A P O L L O")
        self.sidebar_tagline.setVisible(not collapsed)
        self.sidebar_privacy_label.setVisible(not collapsed)
        self.sidebar_customize_btn.setText("⚙" if collapsed else "⚙  Customise Sidebar")

        for key in ("Hub", *ordered, "Settings"):
            button = self.nav_buttons.get(key)
            if button is None:
                continue
            icon = self.sidebar_icons.get(key, "◈")
            default = self.sidebar_default_labels.get(key, key)
            title = self.sidebar_state.display_label(key, default)
            button.setText(icon if collapsed else f"{icon}    {title}")
            button.setToolTip(title)
            if key not in ("Hub", "Settings"):
                self.sidebar_nav_layout.addWidget(button)
                button.setVisible(self.sidebar_state.is_visible(key))
            else:
                button.setVisible(True)

    def open_sidebar_manager(self):
        """Edit the navigation without modifying, uninstalling or disabling modules."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Apollo Sidebar Manager")
        dialog.resize(470, 590)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label(
            "Drag to reorder. Untick to hide. Home and Settings are locked.",
            11, "#a5d1c8"
        ))

        listing = QListWidget()
        listing.setAlternatingRowColors(True)
        listing.setDragDropMode(QAbstractItemView.InternalMove)
        listing.setDefaultDropAction(Qt.MoveAction)
        for key in self.sidebar_state.ordered(self.nav_buttons.keys()):
            item = QListWidgetItem(
                self.sidebar_state.display_label(
                    key, self.sidebar_default_labels.get(key, key)
                )
            )
            item.setData(Qt.UserRole, key)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(
                Qt.Checked if self.sidebar_state.is_visible(key) else Qt.Unchecked
            )
            listing.addItem(item)
        layout.addWidget(listing, 1)

        rename = QPushButton("Rename selected")
        def rename_selected():
            item = listing.currentItem()
            if item is None:
                return
            text, accepted = QInputDialog.getText(
                dialog, "Rename Shortcut", "Sidebar label:", text=item.text()
            )
            if accepted and text.strip():
                item.setText(" ".join(text.split())[:36])
        rename.clicked.connect(rename_selected)
        layout.addWidget(rename)

        width_selector = QComboBox()
        widths = (180, 220, 260, 300, 360)
        for width in widths:
            width_selector.addItem(f"{width} px", width)
        current_width = self.sidebar_state.state()["width"]
        if current_width not in widths:
            width_selector.addItem(f"{current_width} px", current_width)
        width_selector.setCurrentIndex(width_selector.findData(current_width))
        layout.addWidget(label("Expanded sidebar width", 10, "#a5d1c8"))
        layout.addWidget(width_selector)

        collapsed_checkbox = QCheckBox("Collapse sidebar to icons")
        collapsed_checkbox.setChecked(self.sidebar_state.state()["collapsed"])
        layout.addWidget(collapsed_checkbox)

        actions = QHBoxLayout()
        reset_button = QPushButton("Reset to defaults")
        cancel_button = QPushButton("Cancel")
        apply_button = QPushButton("Save layout")
        def reset_layout():
            self.sidebar_state.reset()
            self._refresh_sidebar()
            dialog.accept()
        def save_layout():
            order, hidden, labels = [], [], {}
            for index in range(listing.count()):
                item = listing.item(index)
                key = item.data(Qt.UserRole)
                order.append(key)
                if item.checkState() != Qt.Checked:
                    hidden.append(key)
                labels[key] = item.text()
            self.sidebar_state.apply(
                order, hidden, labels,
                width_selector.currentData(), collapsed_checkbox.isChecked()
            )
            self._refresh_sidebar()
            dialog.accept()
        reset_button.clicked.connect(reset_layout)
        cancel_button.clicked.connect(dialog.reject)
        apply_button.clicked.connect(save_layout)
        actions.addWidget(reset_button)
        actions.addStretch()
        actions.addWidget(cancel_button)
        actions.addWidget(apply_button)
        layout.addLayout(actions)
        dialog.exec()

    def _build_topbar(self):
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Ask Apollo anything...")
        self.search.returnPressed.connect(self.top_search_send)
        h.addWidget(self.search, 1)

        self.online_dot = QLabel("●")
        self.online_text = QLabel("Apollo status...")
        self.online_text.setStyleSheet("color: #8be6d4;")
        h.addSpacing(14)
        h.addWidget(self.online_dot)
        h.addWidget(self.online_text)

        badge = QLabel(self.config.get("user_name", "OS")[:2].upper())
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedSize(42, 42)
        badge.setStyleSheet(
            "background:#103536;border:1px solid #1b6d66;border-radius:21px;"
            "color:#dffff9;font-weight:bold;"
        )
        h.addSpacing(12)
        h.addWidget(badge)

        self.window_close_button = QPushButton("✕")
        self.window_close_button.setObjectName("windowClose")
        self.window_close_button.setToolTip(
            "Close Apollo cleanly"
        )
        self.window_close_button.setFixedSize(42, 42)
        self.window_close_button.clicked.connect(
            self.close
        )
        h.addSpacing(8)
        h.addWidget(self.window_close_button)

        return bar

    def switch_page(self, name):
        widget = self.pages.get(name)
        if widget is None:
            return
        self.stack.setCurrentWidget(widget)
        for n, b in self.nav_buttons.items():
            b.setChecked(n == name)
        self._queue_ui_state_save()

    def top_search_send(self):
        text = self.search.text().strip()
        if not text:
            return
        self.search.clear()
        self.switch_page("Chat")
        self.chat_input.setText(text)
        self.send_chat()

    def _build_hub_module_widget(
        self,
        module_id,
        fallback_title,
        fallback_text,
    ):
        record = self.module_manager.get_module(module_id)

        if (
            record
            and record.get("enabled")
            and record.get("instance") is not None
            and hasattr(record.get("instance"), "build_hub_widget")
        ):
            instance = record["instance"]

            try:
                return instance.build_hub_widget(
                    parent=None,
                    ui_context={
                        "apollo_window": self,
                        "module_manager": self.module_manager,
                        "base_dir": str(BASE_DIR),
                    },
                )
            except Exception as exc:
                fallback_text = (
                    f"{fallback_text}\n\n"
                    f"Hub widget error: {type(exc).__name__}: {exc}"
                )

        card = Card(fallback_title)
        card.layout.addWidget(
            label(
                fallback_text,
                10,
                "#b8d9d3",
            )
        )
        return card

    def _build_hub(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        scroll.setWidget(body)

        main = QVBoxLayout(body)
        main.setSpacing(14)

        hero = QFrame()
        hero.setObjectName("hero")
        hv = QVBoxLayout(hero)
        hv.setContentsMargins(28, 22, 28, 22)

        hero_top = QHBoxLayout()
        hero_text = QVBoxLayout()
        hero_text.addWidget(label(
            f"Good morning, {self.config.get('user_name', 'Oscar')}",
            26, "#e9fffb", True
        ))
        hero_text.addWidget(label(
            "Apollo OS shell is active. Pin, size and organise the tools you actually use.",
            12, "#b9dcd6"
        ))
        hero_top.addLayout(hero_text, 1)

        manage_btn = QPushButton("⚙  Manage Hub")
        manage_btn.setToolTip("Pin, unpin, resize, reorder and group Apollo apps")
        manage_btn.clicked.connect(self.open_hub_manager)
        hero_top.addWidget(manage_btn)
        hv.addLayout(hero_top)
        hv.addSpacing(8)
        hv.addWidget(label(
            "“Understand. Learn. Assist. Protect. Evolve.”",
            11, "#62ddc8"
        ))
        hero.setMinimumHeight(145)
        main.addWidget(hero)

        apps_heading = QHBoxLayout()
        apps_heading.addWidget(label("Pinned Apps", 17, "#e9fffb", True))
        apps_heading.addWidget(label(
            "Logical grid layout — safe across window sizes and restarts.",
            10, "#78afa6"
        ))
        apps_heading.addStretch()
        self.hub_edit_btn = QPushButton("Edit Layout")
        self.hub_edit_btn.setCheckable(True)
        self.hub_edit_btn.setChecked(bool(self.hub_edit_mode))
        self.hub_edit_btn.setToolTip("Direct edit: drag tiles to move them and drag any corner to resize")
        self.hub_edit_btn.clicked.connect(self.toggle_hub_edit_mode)
        apps_heading.addWidget(self.hub_edit_btn)
        main.addLayout(apps_heading)

        self.hub_edit_banner = QLabel(
            "EDIT MODE  •  Drag an app tile to move it  •  Drag any glowing corner to resize  •  Layout snaps to the Apollo grid"
        )
        self.hub_edit_banner.setObjectName("hubEditBanner")
        self.hub_edit_banner.setWordWrap(True)
        self.hub_edit_banner.hide()
        main.addWidget(self.hub_edit_banner)

        self.hub_apps_host = QWidget()
        self.hub_apps_layout = QVBoxLayout(self.hub_apps_host)
        self.hub_apps_layout.setContentsMargins(0, 0, 0, 0)
        self.hub_apps_layout.setSpacing(10)
        main.addWidget(self.hub_apps_host)
        self._refresh_hub_tiles()

        # Live overview keeps the useful status information from the old Hub,
        # but app launching itself is now handled by the configurable shell.
        main.addWidget(label("Live Overview", 16, "#e9fffb", True))
        overview = QGridLayout()
        overview.setHorizontalSpacing(12)
        overview.setVerticalSpacing(12)

        recent = Card("Recent Chat")
        self.hub_recent_chat = label(
            "Ask Apollo something to begin.", 10, "#d4eee9"
        )
        recent.layout.addWidget(self.hub_recent_chat)
        open_chat = QPushButton("Open Chat")
        open_chat.clicked.connect(lambda: self._launch_shell_app("core.chat"))
        recent.layout.addWidget(open_chat)
        overview.addWidget(recent, 0, 0)

        train = Card("Learning")
        self.hub_learning = label("0 learned items", 18, "#7cf0d7", True)
        train.layout.addWidget(self.hub_learning)
        train.layout.addWidget(label(
            "Persistent facts, corrections and preferred answers.",
            10, "#aacfc8"
        ))
        overview.addWidget(train, 0, 1)

        memory = Card("Memory")
        self.hub_memory = label("No memories stored yet.", 10, "#c1ded9")
        memory.layout.addWidget(self.hub_memory)
        btn_mem = QPushButton("View Memory")
        btn_mem.clicked.connect(lambda: self._launch_shell_app("core.memory"))
        memory.layout.addWidget(btn_mem)
        overview.addWidget(memory, 0, 2)

        system = Card("System")
        self.hub_cpu = QProgressBar()
        self.hub_ram = QProgressBar()
        system.layout.addWidget(label("CPU", 10, "#9fc8c1"))
        system.layout.addWidget(self.hub_cpu)
        system.layout.addWidget(label("RAM", 10, "#9fc8c1"))
        system.layout.addWidget(self.hub_ram)
        self.hub_model = label("Model: checking...", 10, "#79dfcc")
        system.layout.addWidget(self.hub_model)
        overview.addWidget(system, 0, 3)

        main.addLayout(overview)

        live_row = QHBoxLayout()
        live_row.setSpacing(12)

        self.hub_neural_widget = self._build_hub_module_widget(
            "neural_visualizer",
            "Live Neural Activity",
            "Neural Visualizer is unavailable. Enable the neural_visualizer module.",
        )
        self.hub_to_do_widget = self._build_hub_module_widget(
            "todo_list",
            "To-Do List",
            "To-Do List is unavailable. Enable the todo_list module.",
        )

        live_row.addWidget(self.hub_neural_widget, 2)
        live_row.addWidget(self.hub_to_do_widget, 1)
        main.addLayout(live_row)

        bottom = QHBoxLayout()

        status = Card("System Status")
        self.hub_status_list = QVBoxLayout()
        status.layout.addLayout(self.hub_status_list)
        bottom.addWidget(status, 1)

        quick = Card("Quick Actions")
        for text, app_id in [
            ("Open Chat", "core.chat"),
            ("Open Workshop", "core.workshop"),
            ("Manage Modules", "core.modules"),
            ("Review Memory", "core.memory"),
        ]:
            b = QPushButton(text)
            b.clicked.connect(lambda checked=False, a=app_id: self._launch_shell_app(a))
            quick.layout.addWidget(b)
        hub_manage = QPushButton("Manage Hub")
        hub_manage.clicked.connect(self.open_hub_manager)
        quick.layout.addWidget(hub_manage)
        bottom.addWidget(quick, 1)

        self.hub_memory_bank_widget = self._build_hub_module_widget(
            "memory_bank",
            "Memory Bank",
            "Memory Bank is unavailable. Enable the memory_bank module.",
        )
        bottom.addWidget(self.hub_memory_bank_widget, 1)

        main.addLayout(bottom)
        main.addStretch()
        return scroll

    def _clear_layout(self, layout):
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            child_layout = item.layout()
            widget = item.widget()
            if child_layout is not None:
                self._clear_layout(child_layout)
            if widget is not None:
                widget.deleteLater()

    def toggle_hub_edit_mode(self, force=None):
        if force is None:
            self.hub_edit_mode = not bool(self.hub_edit_mode)
        else:
            self.hub_edit_mode = bool(force)
        if hasattr(self, "hub_edit_btn"):
            self.hub_edit_btn.setChecked(bool(self.hub_edit_mode))
            self.hub_edit_btn.setText("Done Editing" if self.hub_edit_mode else "Edit Layout")
        if hasattr(self, "hub_edit_banner"):
            self.hub_edit_banner.setVisible(self.hub_edit_mode)
        self._refresh_hub_tiles()

    def _hub_drop_tile(self, app_id, section, row, col):
        current = self.shell.store.get(app_id)
        if not current:
            return
        try:
            self.shell.place_resize(
                app_id,
                row,
                col,
                row_span=current.get("row_span", 1),
                col_span=current.get("col_span", 1),
                section=section,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Apollo Hub", f"Could not move tile: {exc}")
        self._refresh_hub_tiles()

    def _hub_resize_tile(self, app_id, section, row, col, row_span, col_span):
        try:
            self.shell.place_resize(
                app_id,
                row,
                col,
                row_span=row_span,
                col_span=col_span,
                section=section,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Apollo Hub", f"Could not resize tile: {exc}")
        self._refresh_hub_tiles()

    def _make_hub_app_tile(self, app, edit_context=None):
        edit_mode = edit_context is not None
        if edit_mode:
            grid_host, row, column, row_span, column_span = edit_context
            tile = HubEditableTile(
                app.get("app_id"),
                app.get("section", "Main"),
                grid_host,
                row,
                column,
                row_span,
                column_span,
                self._hub_resize_tile,
            )
        else:
            tile = QFrame()
            tile.setObjectName("hubTile")
            row_span = int(app.get("row_span", TILE_SPANS.get(app.get("size", "medium"), (1, 2))[0]))
            column_span = int(app.get("col_span", TILE_SPANS.get(app.get("size", "medium"), (1, 2))[1]))

        layout = QVBoxLayout(tile)
        layout.setContentsMargins(18 if edit_mode else 15, 16 if edit_mode else 13, 18 if edit_mode else 15, 16 if edit_mode else 13)
        layout.setSpacing(7)

        title = QLabel(f"{app.get('glyph', '◫')}   {app.get('title', app.get('app_id'))}")
        title.setObjectName("hubTileTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        if edit_mode:
            badge = QLabel(f"⠿  DRAG   •   {column_span} × {row_span}")
            badge.setObjectName("hubEditBadge")
            layout.addWidget(badge)
            for widget in (title, badge):
                widget.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        if column_span > 1 or row_span > 1:
            description = label(
                str(app.get("description", "")) or "Apollo application",
                9,
                "#9bc9c1",
            )
            description.setMaximumHeight(80 if row_span > 1 else 46)
            if edit_mode:
                description.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            layout.addWidget(description)

        status_text = "Core app"
        if app.get("kind") == "module":
            status_text = (
                f"Module • v{app.get('version', '?')} • "
                + ("Ready" if app.get("available") else "Disabled / unavailable")
            )
        meta = QLabel(status_text)
        meta.setObjectName("hubTileMeta")
        meta.setWordWrap(True)
        if edit_mode:
            meta.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(meta)

        if row_span > 1 and column_span > 1:
            detail = label(
                f"ID: {app.get('app_id')}\nSection: {app.get('section', 'Main')}",
                9,
                "#659b93",
            )
            if edit_mode:
                detail.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            layout.addWidget(detail)

        layout.addStretch()
        if edit_mode:
            hint = QLabel("Move: drag tile   Resize: drag a corner")
            hint.setObjectName("hubTileMeta")
            hint.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            layout.addWidget(hint)
        else:
            open_btn = QPushButton("Open" if app.get("available", True) else "Unavailable")
            open_btn.setEnabled(bool(app.get("available", True)))
            open_btn.clicked.connect(
                lambda checked=False, app_id=app.get("app_id"): self._launch_shell_app(app_id)
            )
            layout.addWidget(open_btn)

        tile.setMinimumHeight(HUB_CELL_HEIGHT if row_span == 1 else HUB_CELL_HEIGHT * row_span)
        return tile

    def _refresh_hub_tiles(self):
        if not hasattr(self, "hub_apps_layout"):
            return
        self._clear_layout(self.hub_apps_layout)
        items = self.shell.hub_items()
        if not items:
            empty = Card("No pinned apps")
            empty.layout.addWidget(label(
                "Your Hub is empty. Use Manage Hub to pin Apollo apps and modules.",
                10,
                "#91bdb6",
            ))
            button = QPushButton("Manage Hub")
            button.clicked.connect(self.open_hub_manager)
            empty.layout.addWidget(button)
            self.hub_apps_layout.addWidget(empty)
            return

        sections = []
        grouped = {}
        for item in items:
            section = str(item.get("section") or "Main")
            if section not in grouped:
                grouped[section] = []
                sections.append(section)
            grouped[section].append(item)

        for section in sections:
            section_heading = QHBoxLayout()
            section_heading.addWidget(label(section, 11, "#73d9c6", True))
            if self.hub_edit_mode:
                section_heading.addWidget(label("Drop apps anywhere in this section", 9, "#619c93"))
            section_heading.addStretch()
            self.hub_apps_layout.addLayout(section_heading)

            if self.hub_edit_mode:
                grid_host = HubDropGrid(section, self._hub_drop_tile)
                grid = grid_host.grid
            else:
                grid_host = QWidget()
                grid = QGridLayout(grid_host)
                grid.setContentsMargins(0, 0, 0, 0)
                grid.setHorizontalSpacing(HUB_GRID_SPACING)
                grid.setVerticalSpacing(HUB_GRID_SPACING)
                for column in range(HUB_COLUMNS):
                    grid.setColumnStretch(column, 1)

            packed = pack_tiles(grouped[section], HUB_COLUMNS)
            max_rows = 1
            for item, row, column, row_span, column_span in packed:
                max_rows = max(max_rows, row + row_span)
                if self.hub_edit_mode:
                    tile = self._make_hub_app_tile(
                        item,
                        edit_context=(grid_host, row, column, row_span, column_span),
                    )
                else:
                    tile = self._make_hub_app_tile(item)
                grid.addWidget(tile, row, column, row_span, column_span)

            for row in range(max_rows):
                grid.setRowMinimumHeight(row, HUB_CELL_HEIGHT)
            if self.hub_edit_mode:
                grid_host.set_row_count_hint(max_rows)
            self.hub_apps_layout.addWidget(grid_host)

    def _launch_shell_app(self, app_id):
        app = self.shell.app(app_id)
        if not app:
            QMessageBox.warning(
                self,
                "Apollo Hub",
                "That app is no longer installed or registered. Open Manage Hub to clean the shortcut."
            )
            return

        if app.get("kind") == "core":
            self.switch_page(str(app.get("target")))
            return

        module_id = str(app.get("module_id") or app.get("target") or "").strip()
        if not app.get("available"):
            QMessageBox.information(
                self,
                "Apollo Hub",
                f"{app.get('title', module_id)} is installed but currently disabled or unavailable. "
                "Open Modules to inspect or enable it."
            )
            self.switch_page("Modules")
            return

        placement = self.module_manager.get_ui_placement(module_id)
        if placement == "sidebar":
            page_key = f"module::{module_id}"
            if page_key in self.pages:
                self.switch_page(page_key)
                return

        # Apps placement already has a normal route. Hidden/tool-only module UIs
        # can still be opened from a pinned Hub tile without changing placement.
        if placement == "apps":
            self.open_module_app(module_id)
            return

        record = self.module_manager.get_module(module_id)
        if not record:
            return
        manifest = record.get("manifest", {})
        ui = manifest.get("ui", {}) if isinstance(manifest, dict) else {}
        module_info = {
            "id": module_id,
            "title": ui.get("title", manifest.get("name", module_id)),
            "description": manifest.get("description", ""),
            "instance": record.get("instance"),
            "manifest": manifest,
        }
        page = self.dynamic_module_pages.get(module_id)
        if page is None:
            page = self._build_module_page_widget(module_info)
            if page is None:
                QMessageBox.warning(self, "Apollo Hub", "The module UI could not be created.")
                return
            self.dynamic_module_pages[module_id] = page
            self.apps_host.addWidget(page)

        self.switch_page("Settings")
        if hasattr(self, "settings_tabs") and hasattr(self, "settings_apps_tab"):
            self.settings_tabs.setCurrentWidget(self.settings_apps_tab)
        self.apps_host.setCurrentWidget(page)
        self.current_app_module_id = module_id
        self.current_app_open = True
        if hasattr(self, "apps_current_label"):
            self.apps_current_label.setText(f"Open app: {module_info['title']}")
        if hasattr(self, "apps_close_btn"):
            self.apps_close_btn.setEnabled(True)
        if hasattr(self, "apps_inline_close_btn"):
            self.apps_inline_close_btn.setEnabled(True)
        self._queue_ui_state_save()

    def open_hub_manager(self):
        """Open the first Apollo OS app-management surface."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Apollo Hub Manager")
        dialog.setMinimumSize(760, 560)
        self.hub_manager_dialog = dialog

        root = QVBoxLayout(dialog)
        root.addWidget(label("Manage Hub", 20, "#e9fffb", True))
        root.addWidget(label(
            "Pin/unpin apps and organise sections here. For normal layout editing, close this window "
            "and use Edit Layout on the Hub: drag tiles to move them and drag any glowing corner to resize. "
            "Removing a tile from the Hub does not uninstall its module.",
            10,
            "#91bdb6",
        ))

        body = QHBoxLayout()
        app_list = QListWidget()
        body.addWidget(app_list, 2)

        controls_card = Card("Selected App")
        details = label("Select an app.", 10, "#b9dcd6")
        controls_card.layout.addWidget(details)

        size_combo = QComboBox()
        size_combo.addItem("Small — 1×1", "small")
        size_combo.addItem("Medium — 2×1", "medium")
        size_combo.addItem("Wide — 3×1", "wide")
        size_combo.addItem("Large — 2×2", "large")
        controls_card.layout.addWidget(label("Preset size (optional)", 9, "#7eb8ae", True))
        controls_card.layout.addWidget(size_combo)

        pin_btn = QPushButton("Pin to Hub")
        size_btn = QPushButton("Apply Preset Size")
        up_btn = QPushButton("Move Up (fallback)")
        down_btn = QPushButton("Move Down (fallback)")
        section_btn = QPushButton("Change Section")
        controls_card.layout.addWidget(pin_btn)
        controls_card.layout.addWidget(size_btn)
        controls_card.layout.addWidget(up_btn)
        controls_card.layout.addWidget(down_btn)
        controls_card.layout.addWidget(section_btn)
        controls_card.layout.addStretch()
        body.addWidget(controls_card, 1)
        root.addLayout(body, 1)

        bottom = QHBoxLayout()
        reset_btn = QPushButton("Reset Default Layout")
        refresh_btn = QPushButton("Refresh Apps")
        edit_direct_btn = QPushButton("Edit Hub Directly")
        close_btn = QPushButton("Close")
        bottom.addWidget(reset_btn)
        bottom.addWidget(refresh_btn)
        bottom.addWidget(edit_direct_btn)
        bottom.addStretch()
        bottom.addWidget(close_btn)
        root.addLayout(bottom)

        rows_by_id = {}

        def selected_id():
            selected = app_list.selectedItems()
            return selected[0].data(Qt.UserRole) if selected else None

        def refresh_list(preferred=None):
            current = preferred or selected_id()
            app_list.clear()
            rows_by_id.clear()
            for row in self.shell.manager_rows():
                rows_by_id[row["app_id"]] = row
                marker = "✓" if row.get("pinned") else "+"
                availability = "" if row.get("available") else "  [disabled/missing]"
                size = f" [{row.get('size')}]" if row.get("pinned") else ""
                item = QListWidgetItem(
                    f"{marker}  {row.get('title')}  {size}{availability}\n"
                    f"{row.get('app_id')}"
                )
                item.setData(Qt.UserRole, row["app_id"])
                app_list.addItem(item)
                if row["app_id"] == current:
                    app_list.setCurrentItem(item)
            if app_list.count() and not app_list.selectedItems():
                app_list.setCurrentRow(0)

        def update_controls():
            app_id = selected_id()
            row = rows_by_id.get(app_id)
            if not row:
                details.setText("Select an app.")
                for button in (pin_btn, size_btn, up_btn, down_btn, section_btn):
                    button.setEnabled(False)
                return
            pinned = bool(row.get("pinned"))
            details.setText(
                f"{row.get('title')}\n\n{row.get('description', '')}\n\n"
                f"Type: {row.get('kind')}\n"
                f"Status: {'ready' if row.get('available') else 'disabled / unavailable'}\n"
                f"Section: {row.get('section')}\n"
                f"App ID: {row.get('app_id')}"
            )
            pin_btn.setEnabled(True)
            pin_btn.setText("Remove from Hub" if pinned else "Pin to Hub")
            size_btn.setEnabled(pinned)
            up_btn.setEnabled(pinned)
            down_btn.setEnabled(pinned)
            section_btn.setEnabled(pinned)
            index = size_combo.findData(row.get("size", "medium"))
            if index >= 0:
                size_combo.setCurrentIndex(index)

        def mutate(action):
            app_id = selected_id()
            if not app_id:
                return
            row = rows_by_id.get(app_id, {})
            try:
                action(app_id, row)
            except Exception as exc:
                QMessageBox.warning(dialog, "Apollo Hub Manager", str(exc))
            self._refresh_hub_tiles()
            refresh_list(app_id)
            update_controls()

        def toggle_pin():
            def action(app_id, row):
                if row.get("pinned"):
                    self.shell.unpin(app_id)
                else:
                    self.shell.pin(app_id, size=size_combo.currentData() or "medium", section="Main")
            mutate(action)

        def apply_size():
            mutate(lambda app_id, row: self.shell.set_size(app_id, size_combo.currentData()))

        def move_up():
            mutate(lambda app_id, row: self.shell.move(app_id, -1))

        def move_down():
            mutate(lambda app_id, row: self.shell.move(app_id, 1))

        def change_section():
            app_id = selected_id()
            if not app_id:
                return
            row = rows_by_id.get(app_id, {})
            value, ok = QInputDialog.getText(
                dialog,
                "Apollo Hub Section",
                "Section name:",
                text=str(row.get("section") or "Main"),
            )
            if ok and value.strip():
                mutate(lambda target, ignored: self.shell.set_section(target, value))

        def reset_layout():
            answer = QMessageBox.question(
                dialog,
                "Reset Apollo Hub",
                "Restore Apollo's default pinned-app layout? This does not uninstall any apps."
            )
            if answer == QMessageBox.Yes:
                self.shell.reset_layout()
                self._refresh_hub_tiles()
                refresh_list()
                update_controls()

        app_list.itemSelectionChanged.connect(update_controls)
        pin_btn.clicked.connect(toggle_pin)
        size_btn.clicked.connect(apply_size)
        up_btn.clicked.connect(move_up)
        down_btn.clicked.connect(move_down)
        section_btn.clicked.connect(change_section)
        def open_direct_editor():
            dialog.accept()
            self.switch_page("Hub")
            self.toggle_hub_edit_mode(True)

        reset_btn.clicked.connect(reset_layout)
        refresh_btn.clicked.connect(lambda: (refresh_list(selected_id()), update_controls()))
        edit_direct_btn.clicked.connect(open_direct_editor)
        close_btn.clicked.connect(dialog.accept)

        refresh_list()
        update_controls()
        dialog.exec()
        self.hub_manager_dialog = None

    def _build_chat(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)

        title_row = QHBoxLayout()
        title_row.addWidget(label("Chat", 22, "#e6fffa", True))
        title_row.addStretch()
        self.chat_model = label("Model: checking...", 10, "#74d9c6")
        title_row.addWidget(self.chat_model)
        v.addLayout(title_row)

        # A single document-based transcript is deliberately used here instead of
        # a QListWidget full of resizable child widgets. QTextBrowser handles long
        # wrapped text, selection, scrolling and resizing without clipped bubbles.
        self.chat_view = QTextBrowser()
        self.chat_view.setOpenExternalLinks(False)
        self.chat_view.setReadOnly(True)
        self.chat_view.setStyleSheet(
            "QTextBrowser {"
            " background:#071d1e;"
            " border:1px solid #135a53;"
            " border-radius:12px;"
            " padding:10px;"
            " color:#e7fffb;"
            " selection-background-color:#17675d;"
            "}"
        )
        self.chat_view.setHtml(
            "<div style='color:#78bdb1;font-size:13px;padding:14px;'>"
            "Apollo is ready. Ask me anything."
            "</div>"
        )
        v.addWidget(self.chat_view, 1)

        row = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Message Apollo...")
        self.chat_input.returnPressed.connect(self.send_chat)

        self.chat_mic_button = QPushButton("🎙 Dictate")
        self.chat_mic_button.setToolTip(
            "Use Windows offline speech recognition and place the result in the message box."
        )
        self.chat_mic_button.clicked.connect(self.start_speech_to_text)

        self.chat_voice_button = QPushButton()
        self.chat_voice_button.setToolTip(
            "Apollo reads its own completed replies aloud. Click to mute/unmute."
        )
        self.chat_voice_button.clicked.connect(self.toggle_speech_mute)

        self.chat_voice_settings_button = QPushButton("🎚 Voice")
        self.chat_voice_settings_button.setToolTip(
            "Open Voice Studio to change voice, gender, emotion, depth, pitch, speed and volume."
        )
        self.chat_voice_settings_button.clicked.connect(
            lambda: self.open_module_app("text_to_speech")
        )

        self._update_speech_buttons()

        self.chat_send_button = QPushButton("Send")
        self.chat_send_button.clicked.connect(self.send_chat)

        row.addWidget(self.chat_input, 1)
        row.addWidget(self.chat_mic_button)
        row.addWidget(self.chat_voice_button)
        row.addWidget(self.chat_voice_settings_button)
        row.addWidget(self.chat_send_button)
        v.addLayout(row)

        hint = label(
            (
                "Tip: teach Apollo directly in Chat. Named Memory Bank entries, "
                "compiled knowledge and relevant memories are retrieved automatically."
            ),
            9,
            "#6da59d"
        )
        v.addWidget(hint)

        return page

    def _speech_module_ready(self):
        try:
            record = self.module_manager.get_module("text_to_speech")
            return bool(
                record
                and record.get("enabled")
                and record.get("instance") is not None
            )
        except Exception:
            return False

    def _update_speech_buttons(self):
        if hasattr(self, "chat_voice_button"):
            if self.speech_muted:
                self.chat_voice_button.setText("🔇 Muted")
            else:
                self.chat_voice_button.setText("🔊 Voice On")

        module_ready = self._speech_module_ready()

        if hasattr(self, "chat_mic_button"):
            self.chat_mic_button.setEnabled(
                self.stt_task is None
                and module_ready
            )

        if hasattr(self, "chat_voice_settings_button"):
            self.chat_voice_settings_button.setEnabled(
                module_ready
            )

    @Slot()
    def toggle_speech_mute(self):
        self.speech_muted = not self.speech_muted
        self._update_speech_buttons()
        self._queue_ui_state_save()

        if self.speech_muted:
            self.stop_apollo_speech()

    def stop_apollo_speech(self):
        if not self._speech_module_ready():
            return

        task = ModuleActionTask(
            self.module_manager,
            "text_to_speech",
            "stop_speaking",
            {},
        )
        self.thread_pool.start(task)

    def speak_apollo_reply(self, text):
        """Speak ONLY Apollo's completed reply, never the user's input."""
        text = str(text or "").strip()

        if (
            not text
            or self.speech_muted
            or not self._speech_module_ready()
        ):
            return

        # Pass Apollo's real response to Speech I/O. Voice Studio now owns the
        # speech-friendly renderer so displayed text stays precise while spoken text
        # can be more fluid, skip code and use natural pauses/contractions.
        task = ModuleActionTask(
            self.module_manager,
            "text_to_speech",
            "speak_text",
            {"text": text[:12000]},
        )
        self.speech_task = task
        task.signals.failed.connect(self._on_speech_failed, Qt.QueuedConnection)
        task.signals.completed.connect(self._on_speech_completed, Qt.QueuedConnection)
        self.thread_pool.start(task)

    @Slot(str)
    def _on_speech_failed(self, error):
        # Speech is optional. A voice failure must never break Chat.
        if hasattr(self, "online_text"):
            self.online_text.setText(
                "Voice unavailable: " + str(error)[:140]
            )

    @Slot()
    def _on_speech_completed(self):
        self.speech_task = None

    @Slot()
    def start_speech_to_text(self):
        if self.stt_task is not None:
            return

        if not self._speech_module_ready():
            if hasattr(self, "online_text"):
                self.online_text.setText(
                    "Speech I/O module is unavailable."
                )
            return

        self.chat_mic_button.setEnabled(False)
        self.chat_mic_button.setText("🎙 Listening...")

        task = ModuleActionTask(
            self.module_manager,
            "text_to_speech",
            "record_dictation",
            {
                "timeout_seconds": 12,
            },
        )
        self.stt_task = task
        task.signals.finished.connect(self._on_stt_finished, Qt.QueuedConnection)
        task.signals.failed.connect(self._on_stt_failed, Qt.QueuedConnection)
        task.signals.completed.connect(self._on_stt_completed, Qt.QueuedConnection)
        self.thread_pool.start(task)

    @Slot(dict)
    def _on_stt_finished(self, result):
        transcript = str(
            (result or {}).get("text", "")
            or ""
        ).strip()

        if transcript:
            self.chat_input.setText(transcript)
            self.chat_input.setFocus()
            if hasattr(self, "online_text"):
                self.online_text.setText("Speech converted to text and voice sample saved when enabled — review it, then Send.")
        elif hasattr(self, "online_text"):
            self.online_text.setText("No speech was recognized.")

    @Slot(str)
    def _on_stt_failed(self, error):
        if hasattr(self, "online_text"):
            self.online_text.setText(
                "Speech-to-text unavailable: " + str(error)[:160]
            )

    @Slot()
    def _on_stt_completed(self):
        self.stt_task = None
        if hasattr(self, "chat_mic_button"):
            self.chat_mic_button.setText("🎙 Dictate")
        self._update_speech_buttons()

    def _message_needs_tool_catalog(self, text):
        """Keep tool-mode instructions out of ordinary conversation."""
        lower = str(text or "").lower()

        if "coding workspace request:" in lower:
            return True

        action_phrases = (
            "the pile",
            "learn from pile",
            "memory bank",
            "to-do",
            "todo",
            "search the web",
            "search web",
            "look online",
            "web search",
            "gpu",
            "your source",
            "your code",
            "your architecture",
            "train neural",
            "neural status",
            "speak aloud",
            "read aloud",
            "text to speech",
            "speech to text",
            "dictate",
            "microphone",
            "calculator",
            "calculate",
            "create a module",
            "create module",
            "add a module",
            "add module",
        )

        return any(phrase in lower for phrase in action_phrases)

    def _render_chat_transcript(self):
        """Render all chat text inside one QTextDocument on the GUI thread."""
        blocks = []

        for msg in self.chat_display_messages:
            role = msg.get("role", "assistant")
            content = html.escape(msg.get("content", "")).replace("\n", "<br>")

            if role == "user":
                speaker = "You"
                border = "#1b7168"
                bg = "#0b2929"
                speaker_color = "#86e6d4"
            else:
                speaker = "Apollo"
                border = "#14645c"
                bg = "#082324"
                speaker_color = "#45efd1"

            blocks.append(
                f"""
                <div style="margin:8px 2px 12px 2px; padding:12px 14px;
                            background-color:{bg}; border:1px solid {border};">
                    <div style="color:{speaker_color}; font-weight:600;
                                font-size:12px; margin-bottom:7px;">{speaker}</div>
                    <div style="color:#e7fffb; font-size:14px; line-height:1.45;">
                        {content}
                    </div>
                </div>
                """
            )

        document = """
        <html>
        <body style="background-color:#071d1e; color:#e7fffb;
                     font-family:'Segoe UI'; margin:4px;">
        """ + "".join(blocks) + "</body></html>"

        self.chat_view.setHtml(document)
        bar = self.chat_view.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _set_chat_busy(self, busy):
        self.chat_busy = bool(busy)
        self.chat_input.setEnabled(not busy)
        self.chat_send_button.setEnabled(not busy)
        self.chat_send_button.setText("Thinking..." if busy else "Send")
        if not busy:
            self.chat_input.setFocus()

    def _learning_topic(self, content):
        content = " ".join(str(content or "").split()).strip()
        if not content:
            return "Chat learned fact"

        cleaned = re.sub(
            r"^(?:that\s+|my\s+|the\s+)",
            "",
            content,
            flags=re.IGNORECASE,
        ).strip()

        return (cleaned or content)[:120]

    def _apply_integrated_chat_learning(self, text):
        """
        Deterministic learning layer for explicit teaching commands.

        This runs before Ollama, so persistent learning does not depend on the
        language model successfully deciding to call a tool.
        """
        text = str(text or "").strip()
        lower = text.lower()
        events = []

        if not text:
            return events

        # ----------------------------------------------------
        # Preferred-response learning:
        # "when I ask X, answer Y"
        # ----------------------------------------------------
        lesson_patterns = [
            (
                r"(?is)\bwhen\s+i\s+(?:ask|say)\s+['\"]?(.+?)['\"]?"
                r"\s*,?\s*(?:answer|reply|respond|say)\s+(?:with\s+)?"
                r"['\"]?(.+?)['\"]?\s*$"
            ),
            (
                r"(?is)\bif\s+i\s+(?:ask|say)\s+['\"]?(.+?)['\"]?"
                r"\s*,?\s*(?:answer|reply|respond|say)\s+(?:with\s+)?"
                r"['\"]?(.+?)['\"]?\s*$"
            ),
        ]

        for pattern in lesson_patterns:
            match = re.search(pattern, text)
            if match:
                question = match.group(1).strip(" \"'")
                answer = match.group(2).strip(" \"'")

                if question and answer:
                    ident = self.memory.teach(
                        question,
                        answer,
                    )

                    self._store_memory_bank(
                        name=(
                            "Preferred Answer: "
                            + question
                        ),
                        memory_type=(
                            "preferred_answer"
                        ),
                        summary=(
                            "A preferred response "
                            "explicitly taught in Chat."
                        ),
                        content=(
                            f"When asked: {question}\n"
                            f"Preferred answer: {answer}"
                        ),
                        source="Chat Instruction",
                        source_ref=(
                            f"lesson:{ident}"
                        ),
                        tags=[
                            "preferred answer",
                            "chat learning",
                        ],
                        importance=2.0,
                    )

                    events.append(
                        {
                            "kind": "preferred_answer",
                            "id": ident,
                            "summary": (
                                f"Preferred answer learned: when asked "
                                f"'{question}', answer '{answer}'."
                            ),
                        }
                    )
                break

        # ----------------------------------------------------
        # Explicit neural examples:
        # "learn this as coding: debug this program"
        # ----------------------------------------------------
        neural_match = re.search(
            r"(?is)\b(?:learn|label|classify)\s+(?:this\s+)?as\s+"
            r"([a-z0-9][a-z0-9 _-]{0,39})\s*:\s*(.+)$",
            text,
        )

        if neural_match and self._neural_module_available():
            label_name = neural_match.group(1).strip().lower()
            example = neural_match.group(2).strip()

            if label_name and example:
                try:
                    result = self.module_manager.execute(
                        "neural_learning",
                        "add_training_example",
                        {
                            "text": example,
                            "label": label_name,
                        },
                    )

                    if result.get("duplicate"):
                        summary = (
                            f"Neural example already existed for label "
                            f"'{label_name}'."
                        )
                    else:
                        summary = (
                            f"Neural example stored under label '{label_name}'. "
                            f"Total examples: {result.get('example_count')}."
                        )

                    events.append(
                        {
                            "kind": "neural_example",
                            "summary": summary,
                        }
                    )

                    self.refresh_neural_status()

                except Exception as exc:
                    events.append(
                        {
                            "kind": "neural_error",
                            "summary": (
                                "Apollo could not store the neural example: "
                                f"{exc}"
                            ),
                        }
                    )

        # ----------------------------------------------------
        # Explicit fact/preference memory.
        # Avoid treating questions such as "do you remember..." as writes.
        # ----------------------------------------------------
        fact = None

        if not lower.startswith(
            (
                "do you remember",
                "what do you remember",
                "can you tell me if you remember",
            )
        ):
            fact_patterns = [
                r"(?is)\bplease\s+remember\s+(?:that\s+)?(.+)$",
                r"(?is)^\s*remember\s+(?:that\s+|this\s*:\s*)?(.+)$",
                r"(?is)^\s*learn\s+that\s+(.+)$",
                r"(?is)^\s*don't\s+forget\s+(?:that\s+)?(.+)$",
                r"(?is)^\s*do\s+not\s+forget\s+(?:that\s+)?(.+)$",
                r"(?is)^\s*from\s+now\s+on\s*[,:]?\s*(.+)$",
            ]

            for pattern in fact_patterns:
                match = re.search(pattern, text)
                if match:
                    fact = match.group(1).strip()
                    break

        # Don't save a neural command again as a generic fact.
        if fact and not neural_match:
            topic = self._learning_topic(fact)
            ident = self.memory.remember(
                topic,
                fact,
            )

            self._store_memory_bank(
                name=topic,
                memory_type="fact",
                summary=(
                    "A fact explicitly taught "
                    "to Apollo in Chat."
                ),
                content=fact,
                source="Chat Instruction",
                source_ref=(
                    f"fact:{ident}"
                ),
                tags=[
                    "fact",
                    "chat learning",
                ],
                importance=2.0,
            )

            events.append(
                {
                    "kind": "fact",
                    "id": ident,
                    "summary": f"Persistent memory stored: {fact}",
                }
            )

        return events

    @staticmethod
    def _memory_display_name(topic):
        value = " ".join(str(topic or "").split()).strip()
        if not value:
            return "Learned Knowledge"

        wrappers = [
            r"(?i)^\s*(?:says?\s+this|sent\s+this|request)\s*[:,-]?\s*",
            r"(?i)^\s*(?:please\s+)?(?:learn|study|research|remember|absorb)\s+(?:about\s+)?(?:from\s+)?(?:the\s+)?pile(?:\s+(?:about|on|for))?\s*[:,-]?\s*",
            r"(?i)^\s*(?:please\s+)?(?:search|query|access|use)\s+(?:the\s+)?pile(?:\s+(?:about|on|for))?\s*[:,-]?\s*",
        ]
        changed = True
        while changed:
            changed = False
            for pattern in wrappers:
                new_value = re.sub(pattern, "", value, count=1).strip(" :,-")
                if new_value != value:
                    value = new_value
                    changed = True

        value = value.title()

        replacements = {
            "Ai": "AI",
            "Api": "API",
            "Apis": "APIs",
            "Llm": "LLM",
            "Llms": "LLMs",
            "Gpu": "GPU",
            "Cpu": "CPU",
            "Pcb": "PCB",
            "Pcbs": "PCBs",
            "Sql": "SQL",
            "Json": "JSON",
            "Html": "HTML",
            "Css": "CSS",
            "Usb": "USB",
            "Obd": "OBD",
        }

        for old, new in replacements.items():
            value = re.sub(
                r"\b" + re.escape(old) + r"\b",
                new,
                value,
            )

        return value[:120]

    def _store_memory_bank(
        self,
        name,
        content,
        memory_type="knowledge",
        summary="",
        source="",
        source_ref="",
        tags=None,
        importance=1.0,
    ):
        try:
            record = self.module_manager.get_module(
                "memory_bank"
            )

            if (
                not record
                or not record.get("enabled")
                or record.get("instance") is None
            ):
                return None

            return self.module_manager.execute(
                "memory_bank",
                "store_memory",
                {
                    "name": self._memory_display_name(
                        name
                    ),
                    "memory_type": memory_type,
                    "summary": summary,
                    "content": content,
                    "source": source,
                    "source_ref": source_ref,
                    "tags": tags or [],
                    "importance": importance,
                },
            )

        except Exception:
            return None

    def _auto_bank_tool_result(
        self,
        tool_name,
        raw_result,
    ):
        try:
            payload = json.loads(raw_result)

            if not isinstance(payload, dict):
                return

            if not payload.get("ok"):
                return

            result = payload.get("result", {})

            if not isinstance(result, dict):
                return

            if (
                tool_name
                == "pile_knowledge__learn_from_pile"
            ):
                chunks = int(
                    result.get("chunks_added", 0)
                    or 0
                )

                if chunks <= 0:
                    return

                query = str(
                    result.get(
                        "query",
                        "Pile learning",
                    )
                ).strip()

                passages = result.get(
                    "learned_passages",
                    [],
                )

                subsets = sorted({
                    str(item.get("subset", ""))
                    for item in passages
                    if isinstance(item, dict) and item.get("subset")
                })

                distilled = None
                try:
                    record = self.module_manager.get_module("memory_distillation")
                    if record and record.get("enabled") and record.get("instance") is not None:
                        distilled = self.module_manager.execute(
                            "memory_distillation",
                            "distill_pile_result",
                            {"query": query, "passages": passages},
                        )
                except Exception:
                    distilled = None

                if isinstance(distilled, dict):
                    memory_name = distilled.get("display_name") or query
                    summary = str(distilled.get("summary", ""))
                    content = str(distilled.get("content", ""))
                    fingerprint = str(distilled.get("fingerprint", ""))
                else:
                    memory_name = query
                    summary = f"Learned {chunks} source-backed knowledge chunk(s) from The Pile."
                    content = (
                        f"Compiled source-backed knowledge for {query}. "
                        "Use storage/databases/compiled_knowledge.db for the full retrieved passages."
                    )
                    fingerprint = ""

                self._store_memory_bank(
                    name=memory_name,
                    memory_type="learned_knowledge",
                    summary=summary[:1200],
                    content=content[:12000],
                    source="The Pile",
                    source_ref=str(result.get("dataset", "")),
                    tags=[
                        "The Pile",
                        "learned",
                        "source-backed",
                        *(["topic:" + fingerprint] if fingerprint else []),
                        *subsets[:8],
                    ],
                    importance=2.5,
                )

                try:
                    graph = self.module_manager.get_module("knowledge_graph")
                    if graph and graph.get("enabled") and graph.get("instance") is not None:
                        topic_name = self._memory_display_name(memory_name)
                        self.module_manager.execute(
                            "knowledge_graph",
                            "add_relation",
                            {
                                "subject": topic_name,
                                "relation": "learned_from",
                                "object": "The Pile",
                                "source": str(result.get("dataset", "")),
                                "confidence": 1.0,
                            },
                        )
                        for subset in subsets[:8]:
                            self.module_manager.execute(
                                "knowledge_graph",
                                "add_relation",
                                {
                                    "subject": topic_name,
                                    "relation": "source_subset",
                                    "object": subset,
                                    "source": "The Pile",
                                    "confidence": 1.0,
                                },
                            )
                except Exception:
                    pass

            elif (
                tool_name
                == (
                    "training_module__"
                    "explore_web_and_save"
                )
            ):
                query = str(
                    result.get(
                        "query",
                        "Web Research",
                    )
                ).strip()

                sources = result.get(
                    "sources",
                    [],
                )

                sections = []

                for source in sources[:8]:
                    url = str(
                        source.get(
                            "url",
                            "",
                        )
                    ).strip()

                    text = str(
                        source.get("text", "")
                        or source.get(
                            "snippet",
                            "",
                        )
                    ).strip()

                    if not text:
                        continue

                    sections.append(
                        (
                            "Title: "
                            f"{source.get('title', 'Source')}\n"
                            f"URL: {url}\n\n"
                            f"{text[:7000]}"
                        )
                    )

                if not sections:
                    return

                saved = result.get(
                    "saved",
                    {},
                )

                self._store_memory_bank(
                    name=query,
                    memory_type="web_research",
                    summary=(
                        "Source-backed web research "
                        f"from {result.get('source_pages_fetched', 0)} "
                        "fetched page(s)."
                    ),
                    content=(
                        "\n\n---\n\n".join(
                            sections
                        )
                    )[:50000],
                    source="Web Research",
                    source_ref=str(
                        saved.get(
                            "filename",
                            "",
                        )
                    ),
                    tags=[
                        "web research",
                        "source-backed",
                    ],
                    importance=2.0,
                )

        except Exception:
            return

    def open_module_app(self, module_id):
        """Open any installed UI-capable module from any Apollo shell surface."""
        module_id = str(module_id or "").strip()
        if not module_id:
            return

        record = self.module_manager.get_module(module_id)
        if not record or not record.get("enabled") or record.get("instance") is None:
            QMessageBox.information(
                self,
                "Apollo Module Apps",
                f"'{module_id}' is installed but disabled or unavailable. Open Modules to inspect it."
            )
            self.switch_page("Modules")
            return
        if not self.module_manager.module_has_ui(module_id):
            QMessageBox.information(
                self,
                "Apollo Module Apps",
                f"'{module_id}' does not currently expose a usable UI page."
            )
            return

        placement = self.module_manager.get_ui_placement(module_id)
        if placement == "sidebar":
            page_key = f"module::{module_id}"
            if page_key in self.pages:
                self.switch_page(page_key)
                return

        self.switch_page("Settings")
        if hasattr(self, "settings_tabs") and hasattr(self, "settings_apps_tab"):
            self.settings_tabs.setCurrentWidget(self.settings_apps_tab)

        # Rebuild normal module UI first. If legacy placement is Hidden/Tool Only,
        # build an ephemeral Apps view rather than forcing the placement to change.
        self.rebuild_module_ui()
        page = self.dynamic_module_pages.get(module_id)
        if page is None:
            manifest = record.get("manifest", {})
            ui = manifest.get("ui", {}) if isinstance(manifest, dict) else {}
            module_info = {
                "id": module_id,
                "title": ui.get("title", manifest.get("name", module_id)),
                "description": manifest.get("description", ""),
                "instance": record.get("instance"),
                "manifest": manifest,
            }
            page = self._build_module_page_widget(module_info)
            if page is None:
                QMessageBox.warning(self, "Apollo Module Apps", "The module UI could not be built.")
                return
            self.dynamic_module_pages[module_id] = page
            self.apps_host.addWidget(page)

        # Select its list item when one exists; hidden apps can still be launched.
        if hasattr(self, "apps_list"):
            for index in range(self.apps_list.count()):
                item = self.apps_list.item(index)
                if item.data(Qt.UserRole) == module_id:
                    self.apps_list.setCurrentItem(item)
                    break

        self.apps_host.setCurrentWidget(page)
        self.current_app_module_id = module_id
        self.current_app_open = True
        manifest = record.get("manifest", {})
        ui = manifest.get("ui", {}) if isinstance(manifest, dict) else {}
        title = ui.get("title", manifest.get("name", module_id))
        if hasattr(self, "apps_current_label"):
            self.apps_current_label.setText(f"Open app: {title}")
        if hasattr(self, "apps_close_btn"):
            self.apps_close_btn.setEnabled(True)
        if hasattr(self, "apps_inline_close_btn"):
            self.apps_inline_close_btn.setEnabled(True)
        self._queue_ui_state_save()

    @Slot()
    def send_chat(self):
        # This method only runs on the GUI thread.
        text = self.chat_input.text().strip()
        if not text or self.chat_busy:
            return

        self.chat_input.clear()
        self.pending_user_text = text
        self.pending_learning_events = self._apply_integrated_chat_learning(text)

        # Keep the Neural Visualizer active on the Hub for every normal Chat message.
        try:
            neural_visualizer_record = self.module_manager.get_module(
                "neural_visualizer"
            )
            if (
                neural_visualizer_record
                and neural_visualizer_record.get("enabled")
                and neural_visualizer_record.get("instance") is not None
            ):
                self.module_manager.execute(
                    "neural_visualizer",
                    "observe_text",
                    {"text": text},
                )
        except Exception:
            pass

        self.current_stream_text = ""

        self.chat_display_messages.append({"role": "user", "content": text})
        self.chat_display_messages.append({"role": "assistant", "content": "Working..."})
        self._render_chat_transcript()
        self._set_chat_busy(True)

        context = self.memory.context(text)

        # Persistent conversation recall combines a chronological recent window
        # with semantic matches from older exchanges. It survives restarts and
        # lets vague follow-ups resolve what "that", "before" or "try again" means.
        module_memory_context = ""
        try:
            memory_record = self.module_manager.get_module("chat_memory_module")
            if (
                memory_record
                and memory_record.get("enabled")
                and memory_record.get("instance") is not None
            ):
                recalled = self.module_manager.execute(
                    "chat_memory_module",
                    "conversation_context",
                    {
                        "query": text,
                        "recent_limit": 6,
                        "related_limit": 4,
                        "max_chars": 9000,
                    },
                )
                pieces = []
                recent = recalled.get("recent", []) if isinstance(recalled, dict) else []
                related = recalled.get("related", []) if isinstance(recalled, dict) else []
                if recent:
                    pieces.append("RECENT CONVERSATION TIMELINE (oldest to newest):")
                    for item in recent:
                        pieces.append(
                            f"[Conversation #{item.get('memory_id')}]\n"
                            f"User: {item.get('user_text', '')}\n"
                            f"Apollo: {item.get('assistant_text', '')}"
                        )
                if related:
                    pieces.append("OLDER RELEVANT EXCHANGES:")
                    for item in related:
                        pieces.append(
                            f"[Conversation #{item.get('memory_id')}; relevance={item.get('relevance', 0)}]\n"
                            f"User: {item.get('user_text', '')}\n"
                            f"Apollo: {item.get('assistant_text', '')}"
                        )
                module_memory_context = "\n\n".join(pieces)[:12000]
        except Exception:
            module_memory_context = ""

        # Local research files are also a form of Apollo learning. Research & Training
        # now fetches real source-page text, and relevant saved research is injected
        # automatically into later chats.
        research_context = ""
        try:
            research_record = self.module_manager.get_module("training_module")
            if (
                research_record
                and research_record.get("enabled")
                and research_record.get("instance") is not None
            ):
                research = self.module_manager.execute(
                    "training_module",
                    "search_local_research",
                    {"query": text, "limit": 2, "max_chars": 4500},
                )
                matches = research.get("matches", []) if isinstance(research, dict) else []
                if matches:
                    research_context = "\n\n".join(
                        f"Saved research file: {item.get('filename')}\n{item.get('content', '')}"
                        for item in matches
                    )
        except Exception:
            research_context = ""

        # Apollo's compiled knowledge base unifies selected Pile material and
        # locally saved Research & Training files.
        compiled_knowledge_context = ""
        try:
            knowledge_record = self.module_manager.get_module("pile_knowledge")
            if (
                knowledge_record
                and knowledge_record.get("enabled")
                and knowledge_record.get("instance") is not None
            ):
                knowledge = self.module_manager.execute(
                    "pile_knowledge",
                    "search_knowledge",
                    {"query": text, "limit": 4},
                )
                matches = (
                    knowledge.get("matches", [])
                    if isinstance(knowledge, dict)
                    else []
                )

                if matches:
                    compiled_knowledge_context = "\n\n".join(
                        (
                            f"Knowledge source: {item.get('source')} "
                            f"({item.get('source_ref')})\n"
                            f"Title: {item.get('title')}\n"
                            f"{item.get('text', '')}"
                        )
                        for item in matches
                    )
        except Exception:
            compiled_knowledge_context = ""

        # Named Memory Bank retrieval. This is separate from raw conversation
        # history and represents information Apollo deliberately decided to keep.
        memory_bank_context = ""
        try:
            memory_bank_record = self.module_manager.get_module(
                "memory_bank"
            )
            if (
                memory_bank_record
                and memory_bank_record.get("enabled")
                and memory_bank_record.get("instance") is not None
            ):
                bank_matches = self.module_manager.execute(
                    "memory_bank",
                    "search_memory_bank",
                    {"query": text, "limit": 4},
                )

                if bank_matches:
                    memory_bank_context = "\n\n".join(
                        (
                            f"Memory: {item.get('name')}\n"
                            f"Type: {item.get('memory_type')}\n"
                            f"Learned: {item.get('learned_at')}\n"
                            f"Source: {item.get('source')} "
                            f"({item.get('source_ref')})\n"
                            f"Summary: {item.get('summary')}\n"
                            f"{item.get('content', '')[:1800]}"
                        )
                        for item in bank_matches
                    )
        except Exception:
            memory_bank_context = ""

        # Knowledge Graph relationships are compact and source-linked.
        knowledge_graph_context = ""
        try:
            graph_record = self.module_manager.get_module("knowledge_graph")
            if (
                graph_record
                and graph_record.get("enabled")
                and graph_record.get("instance") is not None
            ):
                graph_result = self.module_manager.execute(
                    "knowledge_graph",
                    "search_graph",
                    {"query": text, "limit": 12},
                )
                edges = graph_result.get("edges", []) if isinstance(graph_result, dict) else []
                if edges:
                    knowledge_graph_context = "\n".join(
                        f"{item.get('subject')} --{item.get('relation')}--> {item.get('object')} "
                        f"[source={item.get('source')}; confidence={item.get('confidence')}]"
                        for item in edges[:12]
                    )
        except Exception:
            knowledge_graph_context = ""

        # Only use neural predictions in normal chat after held-out validation passes.
        neural_context = ""
        try:
            neural_record = self.module_manager.get_module("neural_learning")
            if (
                neural_record
                and neural_record.get("enabled")
                and neural_record.get("instance") is not None
            ):
                neural_status = self.module_manager.execute(
                    "neural_learning",
                    "neural_status",
                    {},
                )
                if neural_status.get("ready_for_use"):
                    prediction = self.module_manager.execute(
                        "neural_learning",
                        "predict_label",
                        {"text": text, "top_k": 3},
                    )
                    predictions = prediction.get("predictions", [])
                    if predictions:
                        best = predictions[0]
                        if float(best.get("confidence", 0)) >= 0.55:
                            neural_context = (
                                "Apollo auxiliary neural learner prediction: "
                                f"{best.get('label')} "
                                f"(confidence {best.get('confidence')})."
                            )
        except Exception:
            neural_context = ""

        conversation_flow_context = ""
        try:
            flow_record = self.module_manager.get_module("conversation_flow")
            if (
                flow_record
                and flow_record.get("enabled")
                and flow_record.get("instance") is not None
            ):
                flow_packet = self.module_manager.execute(
                    "conversation_flow",
                    "analyse_turn",
                    {
                        "current_text": text,
                        "recent_messages": self.chat_history[-10:],
                    },
                )
                conversation_flow_context = json.dumps(
                    flow_packet,
                    ensure_ascii=False,
                    default=str,
                )[:5000]
        except Exception:
            conversation_flow_context = ""

        coordination_context = ""
        try:
            context_record = self.module_manager.get_module("context_manager")
            if (
                context_record
                and context_record.get("enabled")
                and context_record.get("instance") is not None
            ):
                packet = self.module_manager.execute(
                    "context_manager",
                    "build_context",
                    {"task": text, "max_chars": 6000},
                )
                coordination_context = json.dumps(packet, ensure_ascii=False, default=str)[:6000]
        except Exception:
            coordination_context = ""

        system = (
            "You are Apollo, a local personal AI assistant. "
            "Apollo 7.5 uses a shared action bus, permission gate, event bus, blackboard, Conversation Flow, Context Manager, Task Engine, Verification Engine and Orchestrator. "
            "Conversation Flow may inject a visible-history continuity packet. Persistent conversation recall may also contain recent exchanges from before Apollo was restarted. "
            "When the user refers to earlier conversation with phrases such as 'try again', 'before', 'previous', 'that one', 'do that', or 'what we were doing', resolve the reference from supplied recent/relevant conversation context before treating it as a new request. "
            "When a turn is a retry/follow-up, preserve the previous meaningful user intent instead of restarting the task or replying with a generic acknowledgement. "
            "For substantial work use a planner -> executor -> verifier pattern: plan persistent steps when useful, execute REAL capabilities, then verify evidence before claiming success. "
            "A plan is not execution. Never narrate imaginary tool calls, file writes, module builds or tests. "
            "Use File Manager for cross-root OS file moves/renames and Workspace/File Builder for authored projects. "
            "When a task spans subsystems, preserve intent in orchestrator goals/shared state and use real capabilities rather than pretending work happened. "
            "High-risk capabilities may be denied until the user enables them in Control Center; report that clearly instead of trying to bypass the gate. "
            "Be useful, technically capable, concise when appropriate, and honest. "
            "In ordinary conversation Apollo has a dry, intelligent, mildly sarcastic personality: use quick wit, understated teasing, and occasional deadpan observations. Never let sarcasm obscure the answer, become cruel, target vulnerable traits, or interfere with medical or safety guidance, coding accuracy, tool execution, structured data, or other precision-critical work. When the situation is serious, drop the jokes and be direct. "
            "For ordinary conversation, answer the user normally. Never ask the user "
            "to provide a function name, tool name, or JSON arguments unless the user "
            "is explicitly discussing Apollo's tool API. "
            "Use learned memory when relevant. "
            "Normal Chat is Apollo's primary learning interface. When the user explicitly "
            "asks you to remember, learn, or adopt a preferred response, do not tell them "
            "to open the Train page. Treat it as persistent learning and acknowledge it "
            "naturally in this same chat. "
            "Apollo has a compiled Knowledge Base. Always use relevant compiled knowledge "
            "that is injected into context. "
            "Explicit requests to access/search/learn from 'The Pile' are handled "
            "deterministically by Apollo before the language model answers. Never claim "
            "Pile-derived facts unless that source operation actually succeeded. "
            "Do not call self_awareness, file tools, or unrelated modules as a fallback "
            "for a Pile request. "
            "Do NOT attempt to download the whole Pile; compile only relevant passages. "
            "If the user asks you to research a topic from the general web AND keep/learn it, "
            "use training_module__explore_web_and_save when available so real source material "
            "is stored locally; the Knowledge Base will sync those research files for later "
            "retrieval. "
            "If the user explicitly gives a labelled neural example, use neural_learning "
            "only if the integrated learning layer has not already stored it. "
            "If the user asks to train the neural network, use "
            "neural_learning__train_network from this chat. "
            "Do not claim actions were performed unless they really were. "
            "Apollo has a persistent named Memory Bank. Source-backed knowledge learned "
            "from The Pile and saved web research are automatically banked with a name, "
            "source and learned date. Use memory_bank tools when the user explicitly asks "
            "to store, inspect, search or remove named memories. "
            "Apollo also has a persistent To-Do List. When the user asks to add, edit, "
            "remove, list, complete, tick off or reopen an item, use todo_list tools. "
            "When the user asks to 'achieve the to-do list', call "
            "todo_list__achieve_to_do_list, work through actionable items with real tools, "
            "and call todo_list__complete_to_do_item only after each corresponding task "
            "actually succeeds. Never mark failed, unsupported or manual work complete. "
            "You have a read-only self_awareness module for inspecting your own source code. "
            "Use it when the user asks about your implementation, architecture, bugs, or code. "
            "When the user asks you to BUILD, CREATE, SAVE, or MAKE a coding project/file, "
            "prefer the file_builder module so real files are created inside Apollo/workspace "
            "instead of only pasting code into chat. "
            "For current or public internet information, use web_explorer tools when available "
            "instead of pretending your training data is live. "
            "When asked to create or repair an Apollo feature/module, use module_factory. "
            "FIRST call module_factory__get_contract so you know Apollo's real API. "
            "New modules must live under pending_modules. After every create/update, Apollo "
            "automatically validates the candidate. If validation fails, inspect the exact "
            "error and keep modifying the pending files until validation/tests pass. "
            "A passing module is STILL NOT INSTALLED: explicit user acceptance from the "
            "Modules page is always required."
        )
        if self.pending_learning_events:
            system += (
                "\n\nApollo's integrated learning layer already completed these "
                "persistent actions for THIS user message:\n"
                + "\n".join(
                    "- " + event.get("summary", "")
                    for event in self.pending_learning_events
                )
                + "\nAcknowledge these completed actions naturally. Do not call another "
                "tool to repeat the same learning action and do not send the user to a "
                "separate learning chat."
            )

        if context:
            system += "\n\nRelevant learned memory:\n" + context

        if module_memory_context:
            system += (
                "\n\nPersistent previous-conversation context (recent timeline + relevant older exchanges):\n"
                + module_memory_context
            )

        if research_context:
            system += (
                "\n\nRelevant locally saved research (source-backed):\n"
                + research_context
            )

        if compiled_knowledge_context:
            system += (
                "\n\nRelevant compiled Apollo knowledge:\n"
                + compiled_knowledge_context
            )

        if memory_bank_context:
            system += (
                "\n\nRelevant named Memory Bank entries:\n"
                + memory_bank_context
            )

        if knowledge_graph_context:
            system += (
                "\n\nRelevant Knowledge Graph relationships:\n"
                + knowledge_graph_context
            )

        if neural_context:
            system += "\n\n" + neural_context

        if conversation_flow_context:
            system += (
                "\n\nConversation continuity packet derived from visible recent chat (not private reasoning):\n"
                + conversation_flow_context
            )

        if coordination_context:
            system += (
                "\n\nApollo internal coordination state (goals/shared state/relevant capabilities):\n"
                + coordination_context
            )

        module_catalog = (
            self.module_manager.tool_catalog_text()
            if self._message_needs_tool_catalog(text)
            else ""
        )
        if module_catalog:
            system += (
                "\n\nThis request appears to require an Apollo action. Installed module tools "
                "are available. Prefer native Ollama tool calls. If native tool calls are "
                "unavailable, output one exact JSON tool object only when you genuinely need "
                "Apollo to execute an action. Never use tool JSON for greetings, questions, "
                "explanations, or ordinary conversation. Do not pretend an action ran unless "
                "a real tool result is returned. For Apollo extension modules use "
                "module_factory, never file_builder.\n" + module_catalog
            )

        messages = [{"role": "system", "content": system}]
        messages.extend(self.chat_history[-12:])
        messages.append({"role": "user", "content": text})

        task = ChatTask(self._client_for_chat_text(text), messages, self.module_manager)
        self.chat_task = task

        # Force GUI-affecting slots onto the receiver/main thread. No lambdas,
        # no widget access from a worker thread.
        task.signals.chunk.connect(self.on_chat_chunk, Qt.QueuedConnection)
        task.signals.finished.connect(self.on_chat_finished, Qt.QueuedConnection)
        task.signals.failed.connect(self.on_chat_failed, Qt.QueuedConnection)
        task.signals.tool_used.connect(self.on_module_tool_used, Qt.QueuedConnection)
        task.signals.completed.connect(self._on_chat_task_completed, Qt.QueuedConnection)

        self.thread_pool.start(task)

    @Slot(str)
    def on_chat_chunk(self, chunk):
        # Stable-response mode. Rebuilding the complete QTextDocument for each
        # model chunk caused the visible transcript to flash during generation and
        # file writes. Accumulate output in memory and render once when finished.
        self.current_stream_text += chunk

    @Slot(str)
    def on_chat_finished(self, answer):
        user_text = self.pending_user_text or ""
        final_answer = answer.strip() if answer else self.current_stream_text.strip()
        if not final_answer:
            final_answer = "No response was returned by Ollama."

        if self.chat_display_messages and self.chat_display_messages[-1]["role"] == "assistant":
            self.chat_display_messages[-1]["content"] = final_answer
        self._render_chat_transcript()

        # Voice output belongs to Apollo's completed reply. User messages are never
        # automatically sent to TTS. The Chat mute button controls this path directly.
        self.speak_apollo_reply(final_answer)

        if user_text:
            self.chat_history.append({"role": "user", "content": user_text})
            self.chat_history.append({"role": "assistant", "content": final_answer})
            self.chat_history = self.chat_history[-16:]

            self.memory.add_conversation(user_text, final_answer)

            # Also save completed exchanges into the modular long-term memory.
            try:
                memory_record = self.module_manager.get_module(
                    "chat_memory_module"
                )
                if (
                    memory_record
                    and memory_record.get("enabled")
                    and memory_record.get("instance") is not None
                ):
                    self.module_manager.execute(
                        "chat_memory_module",
                        "save_chat_memory",
                        {
                            "user_text": user_text,
                            "assistant_text": final_answer,
                            "tags": "automatic_chat",
                            "importance": 1.0,
                        },
                    )
            except Exception:
                # Never break the conversation UI because optional memory failed.
                pass

            self.hub_recent_chat.setText(
                f"You: {user_text}\n\nApollo: {final_answer[:220]}"
            )
            self.refresh_stats()

    @Slot(str, str)
    def on_module_tool_used(self, tool_name, result):
        # Keep the transcript clean while still showing that a real feature ran.
        self.online_text.setText(f"Module ran: {tool_name.replace('__', '.')}")

        # Promote deliberate source-backed learning into the named Memory Bank.
        self._auto_bank_tool_result(
            tool_name,
            result,
        )

    @Slot(str)
    def on_chat_failed(self, error):
        message = (
            "I couldn't talk to Ollama.\n\n"
            + error
            + "\n\nMake sure Ollama is running and a model is installed."
        )
        if self.chat_display_messages and self.chat_display_messages[-1]["role"] == "assistant":
            self.chat_display_messages[-1]["content"] = message
        self._render_chat_transcript()

    @Slot()
    def _on_chat_task_completed(self):
        self.chat_task = None
        self.pending_user_text = None
        self.pending_learning_events = []
        self._set_chat_busy(False)

    def _build_medical(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.addWidget(label("Medical", 22, "#e7fffb", True))
        card = Card("Medical-safe mode")
        card.layout.addWidget(label(
            "This UI section is a placeholder for monitoring and summaries only. "
            "No autonomous diagnosis, dosing, or treatment changes are performed.",
            12, "#b9dcd6"
        ))
        card.layout.addWidget(label(
            "Future modules can import approved local health data and display trends.",
            11, "#70c9bb"
        ))
        v.addWidget(card)
        v.addStretch()
        return page

    def _build_train(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)

        outer.addWidget(label("Train / Learn", 22, "#e7fffb", True))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        content = QWidget()
        v = QVBoxLayout(content)
        v.setContentsMargins(8, 8, 14, 18)
        v.setSpacing(14)

        integrated = Card("Chat-integrated learning")
        integrated.layout.addWidget(label(
            "Normal Chat is now Apollo's main learning interface. You do not need "
            "a separate learning conversation. Explicit teaching instructions are "
            "stored before Apollo answers you.",
            11,
            "#b9dcd6"
        ))
        integrated.layout.addWidget(label(
            "Examples:\n"
            "• remember that my project uses a 12V supply\n"
            "• when I ask what model I use, answer Qwen 2.5 Coder\n"
            "• learn this as coding: debug this Python script\n"
            "• research and learn about multilayer circuit boards\n"
            "• train your neural network",
            10,
            "#75d8c5"
        ))
        v.addWidget(integrated)

        teach = Card("Teach a preferred answer — manual fallback")
        teach.layout.addWidget(label(
            "You can still enter a preferred answer here, but the same thing can "
            "now be taught naturally from Chat.",
            10,
            "#91bdb6"
        ))

        self.teach_q = QLineEdit()
        self.teach_q.setPlaceholderText("Question / trigger")
        self.teach_q.setMinimumHeight(42)

        self.teach_a = QTextEdit()
        self.teach_a.setPlaceholderText("Answer Apollo should remember")
        self.teach_a.setMinimumHeight(110)
        self.teach_a.setMaximumHeight(160)

        b = QPushButton("Teach Apollo")
        b.setMinimumHeight(40)
        b.clicked.connect(self.do_teach)

        teach.layout.addWidget(self.teach_q)
        teach.layout.addWidget(self.teach_a)
        teach.layout.addWidget(b)
        v.addWidget(teach)

        fact = Card("Remember a fact — manual fallback")
        fact.layout.addWidget(label(
            "Facts entered here use the same persistent memory that normal Chat "
            "can now write to with phrases such as 'remember that...'.",
            10,
            "#91bdb6"
        ))

        self.fact_topic = QLineEdit()
        self.fact_topic.setPlaceholderText("Topic")
        self.fact_topic.setMinimumHeight(42)

        self.fact_content = QTextEdit()
        self.fact_content.setPlaceholderText("Information to remember")
        self.fact_content.setMinimumHeight(100)
        self.fact_content.setMaximumHeight(150)

        fb = QPushButton("Store memory")
        fb.setMinimumHeight(40)
        fb.clicked.connect(self.do_remember)

        fact.layout.addWidget(self.fact_topic)
        fact.layout.addWidget(self.fact_content)
        fact.layout.addWidget(fb)
        v.addWidget(fact)

        neural = Card("Neural Learning")
        neural.layout.addWidget(label(
            "The neural learner is managed as an Apollo app, so this page no longer "
            "duplicates its cramped training fields. You can still train it here or "
            "open the full Neural Learning / Neural Visualizer apps.",
            10,
            "#9fc8c1"
        ))

        neural_buttons = QHBoxLayout()

        open_neural = QPushButton("Open Neural Learning App")
        open_neural.setMinimumHeight(40)
        open_neural.clicked.connect(
            lambda: self.open_module_app("neural_learning")
        )

        open_visual = QPushButton("Open Neural Visualizer")
        open_visual.setMinimumHeight(40)
        open_visual.clicked.connect(
            lambda: self.open_module_app("neural_visualizer")
        )

        self.neural_train_button = QPushButton("Train + Validate Neural Net")
        self.neural_train_button.setMinimumHeight(40)
        self.neural_train_button.clicked.connect(
            self.train_neural_network
        )

        neural_status = QPushButton("Neural Status")
        neural_status.setMinimumHeight(40)
        neural_status.clicked.connect(
            self.show_neural_status
        )

        neural_buttons.addWidget(open_neural)
        neural_buttons.addWidget(open_visual)
        neural_buttons.addWidget(self.neural_train_button)
        neural_buttons.addWidget(neural_status)
        neural_buttons.addStretch()

        self.neural_status_label = label(
            "Neural learner: checking...",
            10,
            "#75d8c5"
        )

        self.neural_progress_bar = QProgressBar()
        self.neural_progress_bar.setRange(0, 100)
        self.neural_progress_bar.setValue(0)
        self.neural_progress_bar.setMinimumHeight(22)

        self.neural_training_detail = label(
            "Training idle. Use at least 3 examples for every label.",
            9,
            "#91bdb6"
        )

        neural.layout.addLayout(neural_buttons)
        neural.layout.addWidget(self.neural_status_label)
        neural.layout.addWidget(self.neural_progress_bar)
        neural.layout.addWidget(self.neural_training_detail)

        v.addWidget(neural)
        v.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        self.refresh_neural_status()
        return page


    def do_teach(self):
        q = self.teach_q.text().strip()
        a = self.teach_a.toPlainText().strip()
        if not q or not a:
            QMessageBox.warning(self, "Apollo", "Enter both a question and answer.")
            return
        ident = self.memory.teach(q, a)
        self.teach_q.clear()
        self.teach_a.clear()
        QMessageBox.information(self, "Apollo", f"Learned lesson #{ident}.")
        self.refresh_memory()
        self.refresh_stats()

    def do_remember(self):
        topic = self.fact_topic.text().strip()
        content = self.fact_content.toPlainText().strip()
        if not topic or not content:
            QMessageBox.warning(self, "Apollo", "Enter both a topic and information.")
            return
        ident = self.memory.remember(topic, content)
        self.fact_topic.clear()
        self.fact_content.clear()
        QMessageBox.information(self, "Apollo", f"Stored memory #{ident}.")
        self.refresh_memory()
        self.refresh_stats()

    def _neural_module_available(self):
        record = self.module_manager.get_module("neural_learning")
        return bool(
            record
            and record.get("enabled")
            and record.get("instance") is not None
        )

    def refresh_neural_status(self):
        if not hasattr(self, "neural_status_label"):
            return
        if not self._neural_module_available():
            self.neural_status_label.setText("Neural learner: module unavailable or disabled.")
            return
        try:
            status = self.module_manager.execute("neural_learning", "neural_status", {})
            counts = status.get("class_counts", {})
            self.neural_status_label.setText(
                "Neural learner: "
                f"{status.get('example_count', 0)} examples | "
                f"{len(status.get('known_labels', []))} labels | "
                f"{'READY' if status.get('ready_for_use') else ('trained/not validated' if status.get('trained') else 'needs training')} | "
                f"{status.get('backend', 'unknown')}"
            )
            training = status.get("training", {})
            if hasattr(self, "neural_progress_bar"):
                self.neural_progress_bar.setValue(int(training.get("percent", 0)))
            if hasattr(self, "neural_training_detail"):
                last = status.get("last_training", {})
                self.neural_training_detail.setText(
                    f"Per-label examples: {counts} | "
                    f"phase={training.get('phase', 'idle')} {training.get('percent', 0)}% | "
                    f"validation={last.get('validation_accuracy', 'n/a')} | "
                    f"duration={last.get('duration_seconds', 'n/a')} s"
                )
        except Exception as exc:
            self.neural_status_label.setText(f"Neural learner error: {exc}")

    def add_neural_example(self):
        text = self.neural_example_text.text().strip()
        label_name = self.neural_example_label.text().strip()
        if not text or not label_name:
            QMessageBox.warning(self, "Apollo Neural Learning", "Enter both an example and a label.")
            return
        if not self._neural_module_available():
            QMessageBox.warning(self, "Apollo Neural Learning", "The neural_learning module is unavailable or disabled.")
            return
        try:
            result = self.module_manager.execute(
                "neural_learning", "add_training_example", {"text": text, "label": label_name}
            )
        except Exception as exc:
            QMessageBox.critical(self, "Apollo Neural Learning", str(exc))
            return
        self.neural_example_text.clear()
        self.neural_example_label.clear()
        self.refresh_neural_status()
        if result.get("duplicate"):
            QMessageBox.information(self, "Apollo Neural Learning", "That exact labelled example already exists, so Apollo did not duplicate it.")
        else:
            QMessageBox.information(
                self,
                "Apollo Neural Learning",
                f"Example added to '{result.get('label')}'.\n"
                f"Stored examples: {result.get('example_count')}\n"
                f"Per-label counts: {result.get('class_counts')}\n\n"
                "Apollo requires at least 3 different examples for every label before training."
            )

    def train_neural_network(self):
        if not self._neural_module_available():
            QMessageBox.warning(self, "Apollo Neural Learning", "The neural_learning module is unavailable or disabled.")
            return
        if self.neural_train_task is not None:
            QMessageBox.information(self, "Apollo Neural Learning", "Neural training is already running.")
            return

        self.neural_train_button.setEnabled(False)
        self.neural_train_button.setText("Training + validating...")
        self.neural_progress_bar.setValue(0)

        task = ModuleActionTask(
            self.module_manager,
            "neural_learning",
            "train_network",
            {
                "epochs": 1000,
                "learning_rate": 0.07,
                "hidden_size": 32,
                "restarts": 4,
            },
        )
        self.neural_train_task = task
        self.neural_progress_timer.start()
        task.signals.finished.connect(self.on_neural_training_finished, Qt.QueuedConnection)
        task.signals.failed.connect(self.on_neural_training_failed, Qt.QueuedConnection)
        task.signals.completed.connect(self.on_neural_training_completed, Qt.QueuedConnection)
        self.thread_pool.start(task)

    @Slot(dict)
    def on_neural_training_finished(self, result):
        self.refresh_neural_status()
        ready = bool(result.get("ready_for_use"))
        QMessageBox.information(
            self,
            "Neural Training Complete",
            "Apollo actually trained and evaluated the network.\n\n"
            f"Examples: {result.get('example_count')}\n"
            f"Labels: {', '.join(result.get('labels', []))}\n"
            f"Training accuracy: {round(float(result.get('training_accuracy', 0)) * 100, 1)}%\n"
            f"Validation accuracy: {round(float(result.get('validation_accuracy', 0)) * 100, 1)}%\n"
            f"Best epoch: {result.get('best_epoch')} across {result.get('restarts')} restarts\n"
            f"Duration: {result.get('duration_seconds')} seconds\n\n"
            + ("Quality gate PASSED — Apollo may use this classifier in chat." if ready else "Quality gate FAILED — model was saved, but Apollo will NOT use its predictions in normal chat yet. Add more varied examples and train again.")
        )

    @Slot(str)
    def on_neural_training_failed(self, error):
        self.refresh_neural_status()
        QMessageBox.warning(self, "Apollo Neural Learning", error)

    @Slot()
    def on_neural_training_completed(self):
        self.neural_train_task = None
        if hasattr(self, "neural_progress_timer"):
            self.neural_progress_timer.stop()
        if hasattr(self, "neural_train_button"):
            self.neural_train_button.setEnabled(True)
            self.neural_train_button.setText("Train + Validate Neural Net")
        self.refresh_neural_status()

    def show_neural_status(self):
        if not self._neural_module_available():
            QMessageBox.warning(
                self,
                "Apollo Neural Learning",
                "The neural_learning module is unavailable or disabled."
            )
            return

        try:
            status = self.module_manager.execute(
                "neural_learning",
                "neural_status",
                {},
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Apollo Neural Learning",
                str(exc)
            )
            return

        labels = status.get("known_labels", [])
        last = status.get("last_training", {})

        QMessageBox.information(
            self,
            "Apollo Neural Status",
            f"Backend: {status.get('backend')}\\n"
            f"Examples: {status.get('example_count')}\\n"
            f"Labels: {', '.join(labels) if labels else 'none'}\\n"
            f"Trained: {status.get('trained')}\\n"
            f"Vocabulary: {status.get('vocab_size')}\\n"
            f"Last training accuracy: "
            f"{last.get('training_accuracy', 'n/a')}\\n\\n"
            "The neural learner is a small auxiliary network. "
            "Ollama/Qwen remains Apollo's main language model."
        )

    def _placeholder_page(self, title, body):
        page = QWidget()
        v = QVBoxLayout(page)
        v.addWidget(label(title, 22, "#e7fffb", True))
        c = Card(title)
        c.layout.addWidget(label(body, 12, "#b9dcd6"))
        v.addWidget(c)
        v.addStretch()
        return page

    def _build_apps(self):
        page = QWidget()
        v = QVBoxLayout(page)

        v.addWidget(label("Module Apps", 18, "#e7fffb", True))
        v.addWidget(label(
            "Module mini-apps now live inside Settings. Closing an app only closes "
            "its view — the module stays installed and can be reopened at any time.",
            10,
            "#91bdb6"
        ))

        self.apps_list = QListWidget()
        self.apps_list.setMinimumHeight(76)
        self.apps_list.setMaximumHeight(130)
        self.apps_list.itemDoubleClicked.connect(self.open_selected_app_module)
        v.addWidget(self.apps_list, 0)

        buttons = QHBoxLayout()

        self.apps_open_btn = QPushButton("Open Selected App")
        self.apps_open_btn.clicked.connect(self.open_selected_app_module)

        self.apps_close_btn = QPushButton("Close App")
        self.apps_close_btn.clicked.connect(self.close_current_app)
        self.apps_close_btn.setEnabled(False)

        refresh_btn = QPushButton("Refresh Apps")
        refresh_btn.clicked.connect(self.rebuild_module_ui)

        buttons.addWidget(self.apps_open_btn)
        buttons.addWidget(self.apps_close_btn)
        buttons.addWidget(refresh_btn)
        buttons.addStretch()

        v.addLayout(buttons)

        self.apps_current_bar = QFrame()
        self.apps_current_bar.setObjectName("card")
        current_bar_layout = QHBoxLayout(self.apps_current_bar)
        current_bar_layout.setContentsMargins(12, 8, 12, 8)

        self.apps_current_label = label(
            "No app open",
            11,
            "#91bdb6",
            True,
        )
        current_bar_layout.addWidget(self.apps_current_label)
        current_bar_layout.addStretch()

        self.apps_inline_close_btn = QPushButton("✕ Close")
        self.apps_inline_close_btn.clicked.connect(self.close_current_app)
        self.apps_inline_close_btn.setEnabled(False)
        current_bar_layout.addWidget(self.apps_inline_close_btn)

        v.addWidget(self.apps_current_bar)

        self.apps_host = QStackedWidget()
        self.apps_host.setMinimumHeight(460)
        self.apps_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        v.addWidget(self.apps_host, 1)

        placeholder = QLabel(
            "No app is open.\n\n"
            "Select an app above and press Open Selected App, "
            "or double-click it."
        )
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet("color:#719c95;")
        self.apps_host.addWidget(placeholder)
        self.apps_placeholder = placeholder

        return page


    def _remove_dynamic_sidebar_buttons(self):
        for module_id, button in list(self.dynamic_sidebar_buttons.items()):
            page_key = f"module::{module_id}"
            self.nav_buttons.pop(page_key, None)
            self.sidebar_default_labels.pop(page_key, None)
            try:
                self.dynamic_nav_layout.removeWidget(button)
                button.deleteLater()
            except Exception:
                pass
        self.dynamic_sidebar_buttons = {}

    def _remove_dynamic_module_pages(self):
        for module_id, page in list(self.dynamic_module_pages.items()):
            page_key = f"module::{module_id}"
            if self.pages.get(page_key) is page:
                self.pages.pop(page_key, None)
            try:
                index = self.stack.indexOf(page)
                if index >= 0:
                    self.stack.removeWidget(page)
            except Exception:
                pass
            try:
                if hasattr(self, "apps_host"):
                    index = self.apps_host.indexOf(page)
                    if index >= 0:
                        self.apps_host.removeWidget(page)
            except Exception:
                pass
            try:
                page.deleteLater()
            except Exception:
                pass
        self.dynamic_module_pages = {}
        self.dynamic_app_buttons = {}

        if hasattr(self, "apps_host") and hasattr(self, "apps_placeholder"):
            self.apps_host.setCurrentWidget(self.apps_placeholder)

    def _stabilize_module_ui_controls(self, widget):
        """Give third-party/generated module UIs sane minimum control sizes.

        Qt layouts are allowed to compress child widgets below their useful
        size hints when an embedded app has more content than the host area.
        That made QLineEdit/QTextEdit controls collapse into unreadable strips.
        """
        if widget is None:
            return None

        try:
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        except Exception:
            pass

        try:
            for field in widget.findChildren(QLineEdit):
                field.setMinimumHeight(max(field.minimumHeight(), 38))
                field.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        except Exception:
            pass

        try:
            for combo in widget.findChildren(QComboBox):
                combo.setMinimumHeight(max(combo.minimumHeight(), 38))
                combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        except Exception:
            pass

        try:
            for spin in widget.findChildren(QAbstractSpinBox):
                spin.setMinimumHeight(max(spin.minimumHeight(), 38))
                spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        except Exception:
            pass

        try:
            text_widgets = []
            text_widgets.extend(widget.findChildren(QTextEdit))
            text_widgets.extend(widget.findChildren(QPlainTextEdit))
            for text_widget in text_widgets:
                text_widget.setMinimumHeight(max(text_widget.minimumHeight(), 96))
                text_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        except Exception:
            pass

        try:
            min_hint = widget.minimumSizeHint()
            target_height = max(460, int(min_hint.height()))
            widget.setMinimumHeight(min(target_height, 1600))
        except Exception:
            try:
                widget.setMinimumHeight(max(widget.minimumHeight(), 460))
            except Exception:
                pass

        return widget

    def _wrap_module_ui_for_host(self, widget):
        """Host module pages in a scroll area instead of crushing their fields."""
        if widget is None:
            return None

        self._stabilize_module_ui_controls(widget)

        host = QScrollArea()
        host.setObjectName("moduleAppScrollHost")
        host.setWidgetResizable(True)
        host.setFrameShape(QFrame.NoFrame)
        host.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        host.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        host.setWidget(widget)
        return host

    def _build_module_page_widget(self, module_info):
        instance = module_info.get("instance")
        if instance is None or not hasattr(instance, "build_ui"):
            return None
        try:
            page = instance.build_ui(
                parent=None,
                ui_context={
                    "apollo_window": self,
                    "module_manager": self.module_manager,
                    "base_dir": str(BASE_DIR),
                },
            )
            return self._wrap_module_ui_for_host(page)
        except TypeError:
            page = instance.build_ui()
            return self._wrap_module_ui_for_host(page)
        except Exception as exc:
            error = QWidget()
            layout = QVBoxLayout(error)
            layout.addWidget(label(
                f"{module_info.get('title')} failed to build its UI.",
                18, "#e4a0a0", True
            ))
            details = QTextBrowser()
            details.setPlainText(f"{type(exc).__name__}: {exc}")
            layout.addWidget(details)
            return error

    def close_current_app(self, save_state=True):
        """
        Close the currently displayed Apps-page module without unloading,
        disabling or removing the module itself.
        """
        if hasattr(self, "apps_host") and hasattr(self, "apps_placeholder"):
            self.apps_host.setCurrentWidget(self.apps_placeholder)

        self.current_app_open = False

        if hasattr(self, "apps_close_btn"):
            self.apps_close_btn.setEnabled(False)

        if hasattr(self, "apps_inline_close_btn"):
            self.apps_inline_close_btn.setEnabled(False)

        if hasattr(self, "apps_current_label"):
            self.apps_current_label.setText("No app open")

        if save_state:
            self._queue_ui_state_save()

    def rebuild_module_ui(self):
        if not hasattr(self, "stack"):
            return

        previous_page = self._current_page_key() if hasattr(self, "pages") else "Hub"
        previous_app = self.current_app_module_id
        previous_app_open = bool(self.current_app_open)
        self._remove_dynamic_sidebar_buttons()
        self._remove_dynamic_module_pages()

        if hasattr(self, "apps_list"):
            self.apps_list.clear()

        for module_info in self.module_manager.ui_modules():
            module_id = module_info["id"]
            placement = module_info["placement"]
            if placement == "none":
                continue

            page = self._build_module_page_widget(module_info)
            if page is None:
                continue
            self.dynamic_module_pages[module_id] = page

            if placement == "sidebar":
                page_key = f"module::{module_id}"
                self.pages[page_key] = page
                self.stack.addWidget(page)
                button = QPushButton(str(module_info.get("title", module_id)))
                button.setObjectName("nav")
                button.setCheckable(True)
                button.clicked.connect(
                    lambda checked=False, key=page_key: self.switch_page(key)
                )
                self.dynamic_nav_layout.addWidget(button)
                self.dynamic_sidebar_buttons[module_id] = button
                self.nav_buttons[page_key] = button
                self.sidebar_default_labels[page_key] = str(module_info.get("title", module_id))

            elif placement == "apps":
                self.apps_host.addWidget(page)
                item = QListWidgetItem(
                    f"{module_info.get('title', module_id)}\n"
                    f"{module_info.get('description', '')}"
                )
                item.setData(Qt.UserRole, module_id)
                self.apps_list.addItem(item)

        if hasattr(self, "apps_list") and self.apps_list.count() == 0:
            item = QListWidgetItem(
                "No module apps are assigned to Settings → Apps.\n"
                "Open Modules and set a UI-capable module to Settings → Apps."
            )
            item.setFlags(Qt.NoItemFlags)
            self.apps_list.addItem(item)

        # Restore the user's view when possible after a rebuild.
        if previous_page in self.pages:
            self.switch_page(previous_page)
        elif previous_page.startswith("module::"):
            self.switch_page("Modules")

        restored_app = False

        if previous_app and hasattr(self, "apps_list"):
            for i in range(self.apps_list.count()):
                item = self.apps_list.item(i)
                if item.data(Qt.UserRole) == previous_app:
                    item.setSelected(True)

                    if previous_app_open:
                        self.open_selected_app_module(item)
                        restored_app = True
                    break

        if not restored_app:
            self.current_app_open = False
            if hasattr(self, "apps_close_btn"):
                self.apps_close_btn.setEnabled(False)
            if hasattr(self, "apps_inline_close_btn"):
                self.apps_inline_close_btn.setEnabled(False)
            if hasattr(self, "apps_current_label"):
                self.apps_current_label.setText("No app open")
            if hasattr(self, "apps_host") and hasattr(self, "apps_placeholder"):
                self.apps_host.setCurrentWidget(self.apps_placeholder)

        if hasattr(self, "hub_apps_layout"):
            self._refresh_hub_tiles()
        self._refresh_sidebar()
        self._queue_ui_state_save()

    def open_selected_app_module(self, item=None):
        if not hasattr(self, "apps_list"):
            return

        selected = self.apps_list.selectedItems()

        if item is not None and isinstance(item, QListWidgetItem):
            module_id = item.data(Qt.UserRole)
        elif selected:
            module_id = selected[0].data(Qt.UserRole)
        else:
            return

        if not module_id:
            return

        page = self.dynamic_module_pages.get(module_id)

        if page is None:
            QMessageBox.warning(
                self,
                "Apollo Apps",
                "That module app is not currently available. "
                "Try Refresh Apps or reload the module."
            )
            return

        self.apps_host.setCurrentWidget(page)
        self.current_app_module_id = module_id
        self.current_app_open = True

        title = module_id
        record = self.module_manager.get_module(module_id)
        if record:
            manifest = record.get("manifest", {})
            ui = manifest.get("ui", {}) if isinstance(manifest, dict) else {}
            title = ui.get(
                "title",
                manifest.get("name", module_id),
            )

        if hasattr(self, "apps_current_label"):
            self.apps_current_label.setText(
                f"Open app: {title}"
            )

        if hasattr(self, "apps_close_btn"):
            self.apps_close_btn.setEnabled(True)

        if hasattr(self, "apps_inline_close_btn"):
            self.apps_inline_close_btn.setEnabled(True)

        self._queue_ui_state_save()


    def _build_web(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)

        title_row = QHBoxLayout()
        title_row.addWidget(label("Web", 22, "#e7fffb", True))
        title_row.addStretch()
        self.web_status_label = label(
            "Web Explorer: checking...",
            10,
            "#75d8c5"
        )
        title_row.addWidget(self.web_status_label)
        v.addLayout(title_row)

        search_card = Card("Search / Open")
        self.web_input = QLineEdit()
        self.web_input.setPlaceholderText(
            "Search the web or enter https://example.com"
        )
        self.web_input.returnPressed.connect(self.web_search_or_fetch)

        controls = QHBoxLayout()

        self.web_search_btn = QPushButton("Search Web")
        self.web_search_btn.clicked.connect(self.web_search)

        self.web_fetch_btn = QPushButton("Fetch URL")
        self.web_fetch_btn.clicked.connect(self.web_fetch)

        self.web_open_btn = QPushButton("Open in Browser")
        self.web_open_btn.clicked.connect(self.web_open_external)

        self.web_ask_btn = QPushButton("Ask Apollo About This")
        self.web_ask_btn.clicked.connect(self.web_ask_apollo)
        self.web_ask_btn.setEnabled(False)

        controls.addWidget(self.web_search_btn)
        controls.addWidget(self.web_fetch_btn)
        controls.addWidget(self.web_open_btn)
        controls.addWidget(self.web_ask_btn)
        controls.addStretch()

        search_card.layout.addWidget(self.web_input)
        search_card.layout.addLayout(controls)
        v.addWidget(search_card)

        results_card = Card("Web Results")
        self.web_output = QTextBrowser()
        self.web_output.setOpenExternalLinks(True)
        self.web_output.setPlaceholderText(
            "Search results and fetched webpage text will appear here."
        )
        results_card.layout.addWidget(self.web_output)
        v.addWidget(results_card, 1)

        self.refresh_web_status()
        return page

    def refresh_web_status(self):
        if not hasattr(self, "web_status_label"):
            return

        record = self.module_manager.get_module("web_explorer")
        if (
            record
            and record.get("enabled")
            and record.get("instance") is not None
        ):
            self.web_status_label.setText("Web Explorer: ready")
            self.web_status_label.setStyleSheet("color:#75d8c5;")
        else:
            self.web_status_label.setText(
                "Web Explorer: module unavailable/disabled"
            )
            self.web_status_label.setStyleSheet("color:#e5a2a2;")

    def _web_available(self):
        record = self.module_manager.get_module("web_explorer")
        return bool(
            record
            and record.get("enabled")
            and record.get("instance") is not None
        )

    def _set_web_busy(self, busy, message=None):
        for widget_name in (
            "web_search_btn",
            "web_fetch_btn",
            "web_open_btn",
        ):
            widget = getattr(self, widget_name, None)
            if widget is not None:
                widget.setEnabled(not busy)

        if busy:
            self.web_ask_btn.setEnabled(False)

        if message and hasattr(self, "web_status_label"):
            self.web_status_label.setText(message)

    def web_search_or_fetch(self):
        text = self.web_input.text().strip()
        if not text:
            return

        lower = text.lower()
        if lower.startswith("http://") or lower.startswith("https://"):
            self.web_fetch()
        else:
            self.web_search()

    def web_search(self):
        query = self.web_input.text().strip()
        if not query:
            return

        if not self._web_available():
            QMessageBox.warning(
                self,
                "Apollo Web",
                "The web_explorer module is unavailable or disabled. "
                "Open Modules and reload/re-enable it."
            )
            return

        if self.web_task is not None:
            return

        self.web_output.setPlainText(
            f"Searching the web for: {query}\n\nPlease wait..."
        )
        self._set_web_busy(True, "Web Explorer: searching...")

        task = ModuleActionTask(
            self.module_manager,
            "web_explorer",
            "search_web",
            {"query": query, "limit": 8},
        )
        self.web_task = task

        task.signals.finished.connect(
            self.on_web_search_finished,
            Qt.QueuedConnection
        )
        task.signals.failed.connect(
            self.on_web_failed,
            Qt.QueuedConnection
        )
        task.signals.completed.connect(
            self.on_web_task_completed,
            Qt.QueuedConnection
        )

        self.thread_pool.start(task)

    @Slot(dict)
    def on_web_search_finished(self, result):
        self.web_last_result = result
        query = html.escape(str(result.get("query", "")))
        rows = result.get("results", [])

        pieces = [
            f"<h2 style='color:#dffbf5;'>Search: {query}</h2>"
        ]

        if not rows:
            pieces.append(
                "<p>No search results were returned. "
                "The site may be blocking automated requests.</p>"
            )

        for index, item in enumerate(rows, 1):
            title = html.escape(str(item.get("title", "Untitled")))
            url = html.escape(str(item.get("url", "")), quote=True)
            snippet = html.escape(str(item.get("snippet", "")))

            pieces.append(
                "<div style='margin:12px 0;'>"
                f"<b>{index}. <a href='{url}' style='color:#5ce0c5;'>{title}</a></b><br>"
                f"<span style='color:#7fc1b5;'>{url}</span><br>"
                f"<span>{snippet}</span>"
                "</div>"
            )

        self.web_output.setHtml("\n".join(pieces))
        self.web_ask_btn.setEnabled(bool(rows))

    def web_fetch(self):
        url = self.web_input.text().strip()
        if not url:
            return

        if not self._web_available():
            QMessageBox.warning(
                self,
                "Apollo Web",
                "The web_explorer module is unavailable or disabled."
            )
            return

        if self.web_task is not None:
            return

        self.web_output.setPlainText(
            f"Fetching: {url}\n\nPlease wait..."
        )
        self._set_web_busy(True, "Web Explorer: fetching page...")

        task = ModuleActionTask(
            self.module_manager,
            "web_explorer",
            "fetch_url",
            {"url": url, "max_chars": 60000},
        )
        self.web_task = task

        task.signals.finished.connect(
            self.on_web_fetch_finished,
            Qt.QueuedConnection
        )
        task.signals.failed.connect(
            self.on_web_failed,
            Qt.QueuedConnection
        )
        task.signals.completed.connect(
            self.on_web_task_completed,
            Qt.QueuedConnection
        )

        self.thread_pool.start(task)

    @Slot(dict)
    def on_web_fetch_finished(self, result):
        self.web_last_result = result

        title = html.escape(str(result.get("title", "Web page")))
        url = html.escape(str(result.get("url", "")), quote=True)
        content_type = html.escape(str(result.get("content_type", "")))
        text = html.escape(str(result.get("text", "")))

        self.web_output.setHtml(
            f"<h2 style='color:#dffbf5;'>{title}</h2>"
            f"<p><a href='{url}' style='color:#5ce0c5;'>{url}</a></p>"
            f"<p style='color:#7fc1b5;'>Content type: {content_type}</p>"
            "<hr>"
            f"<pre style='white-space:pre-wrap;font-family:Segoe UI;'>{text}</pre>"
        )

        self.web_ask_btn.setEnabled(bool(result.get("text")))

    @Slot(str)
    def on_web_failed(self, error):
        self.web_last_result = None
        self.web_output.setPlainText(
            "Web Explorer failed.\n\n"
            + error
            + "\n\nSome sites block automated fetching or require JavaScript."
        )
        self.web_ask_btn.setEnabled(False)

    @Slot()
    def on_web_task_completed(self):
        self.web_task = None
        self._set_web_busy(False)
        self.refresh_web_status()

    def web_open_external(self):
        text = self.web_input.text().strip()

        if not text and isinstance(self.web_last_result, dict):
            text = str(self.web_last_result.get("url", "")).strip()

        if not text:
            return

        if "://" not in text:
            text = "https://" + text

        QDesktopServices.openUrl(QUrl(text))

    def web_ask_apollo(self):
        if not isinstance(self.web_last_result, dict):
            return

        if "text" in self.web_last_result:
            title = self.web_last_result.get("title", "")
            url = self.web_last_result.get("url", "")
            page_text = str(self.web_last_result.get("text", ""))[:18000]

            prompt = (
                "I fetched this webpage using Apollo's Web Explorer.\n\n"
                f"TITLE: {title}\n"
                f"URL: {url}\n\n"
                "PAGE TEXT:\n"
                f"{page_text}\n\n"
                "Explain or summarise the useful information from this page. "
                "If I ask a follow-up, use this content as the source."
            )
        else:
            query = self.web_last_result.get("query", "")
            results = self.web_last_result.get("results", [])
            condensed = "\n".join(
                f"- {item.get('title')}: {item.get('url')} — {item.get('snippet')}"
                for item in results[:8]
            )

            prompt = (
                "Apollo Web Explorer returned these live search results.\n\n"
                f"QUERY: {query}\n\n"
                f"RESULTS:\n{condensed}\n\n"
                "Summarise the results and help me decide which source is most useful."
            )

        self.switch_page("Chat")
        self.chat_input.setText(prompt)
        self.send_chat()

    def _build_coding(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.addWidget(label("Apollo Workshop", 22, "#e7fffb", True))
        v.addWidget(label(
            "Build real multi-file projects, use Apollo's installed capabilities, or create controlled self-improvement candidates. "
            "This is the beginning of Apollo's OS-style work surface.",
            10, "#91bdb6"
        ))

        c = Card("Workshop request")
        self.workshop_mode = QComboBox()
        self.workshop_mode.addItem("Build / edit real project files", "build")
        self.workshop_mode.addItem("Full Apollo capability access", "full")
        self.workshop_mode.addItem("Self-improvement — pending / approval gated", "self")
        c.layout.addWidget(label("Mode", 10, "#9fc8c1"))
        c.layout.addWidget(self.workshop_mode)

        self.code_prompt = QTextEdit()
        self.code_prompt.setPlaceholderText(
            "Describe what you want Apollo to build or do. Multi-file projects are written as real files and checked together."
        )
        self.code_prompt.setFixedHeight(130)
        c.layout.addWidget(self.code_prompt)

        controls = QHBoxLayout()
        send = QPushButton("Run Workshop Request")
        send.clicked.connect(self.send_code_request)
        open_workspace = QPushButton("Open Workspace")
        open_workspace.clicked.connect(self.open_workspace_folder)
        refresh_caps = QPushButton("Refresh Capabilities")
        refresh_caps.clicked.connect(self.refresh_workshop_capabilities)
        controls.addWidget(send)
        controls.addWidget(open_workspace)
        controls.addWidget(refresh_caps)
        controls.addStretch()
        c.layout.addLayout(controls)

        self.code_output = QTextEdit()
        self.code_output.setReadOnly(True)
        self.code_output.setPlaceholderText(
            "Workshop status appears here; real project files live under Apollo/workspace."
        )
        c.layout.addWidget(self.code_output)
        v.addWidget(c, 2)

        caps = Card("Apollo capability registry")
        caps.layout.addWidget(label(
            "Every installed/enabled module tool is exported to workspace/APOLLO_CAPABILITIES.json. "
            "Full-capability mode can access this tool surface without exposing it to ordinary Chat.",
            9, "#78bcb0"
        ))
        self.workshop_capabilities = QTextEdit()
        self.workshop_capabilities.setReadOnly(True)
        self.workshop_capabilities.setPlaceholderText("Press Refresh Capabilities to rebuild the registry.")
        self.workshop_capabilities.setFixedHeight(180)
        caps.layout.addWidget(self.workshop_capabilities)
        v.addWidget(caps, 1)

        QTimer.singleShot(0, self.refresh_workshop_capabilities)
        return page

    def refresh_workshop_capabilities(self):
        try:
            tools = self.module_manager.ollama_tools()
        except Exception as exc:
            if hasattr(self, "workshop_capabilities"):
                self.workshop_capabilities.setPlainText(f"Capability scan failed: {exc}")
            return

        registry = []
        lines = []
        for tool in tools:
            fn = (tool.get("function", {}) or {})
            name = str(fn.get("name", "") or "")
            if not name:
                continue
            description = str(fn.get("description", "") or "").strip()
            registry.append({
                "name": name,
                "description": description,
                "parameters": fn.get("parameters", {}),
            })
            lines.append(f"{name}\n  {description}")

        workspace = (BASE_DIR / "workspace").resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        registry_path = workspace / "APOLLO_CAPABILITIES.json"
        registry_path.write_text(
            json.dumps({
                "format": "apollo-capability-registry-v1",
                "tool_count": len(registry),
                "tools": registry,
                "notes": (
                    "Generated by Apollo Workshop. Ordinary Chat intentionally uses a filtered tool set; "
                    "Workshop full-capability mode may access the complete enabled tool surface."
                ),
            }, indent=2),
            encoding="utf-8",
        )

        if hasattr(self, "workshop_capabilities"):
            self.workshop_capabilities.setPlainText(
                f"{len(registry)} enabled tool(s)\nRegistry: workspace/APOLLO_CAPABILITIES.json\n\n"
                + "\n\n".join(lines)
            )

    def send_code_request(self):
        prompt = self.code_prompt.toPlainText().strip()
        if not prompt:
            return

        mode = self.workshop_mode.currentData() if hasattr(self, "workshop_mode") else "build"
        self.switch_page("Chat")

        if mode == "full":
            wrapped = (
                "APOLLO WORKSHOP REQUEST:\n"
                "This request is explicitly running inside Apollo Workshop with access to the enabled Apollo capability registry.\n"
                "Use real tools when an action is requested; never claim a file/module/memory/action happened unless its tool returned success.\n"
                "Prefer existing Apollo capabilities over inventing duplicate code.\n\n"
                "REQUEST:\n" + prompt
            )
            self.code_output.setPlainText("Workshop full-capability request sent to Apollo.")

        elif mode == "self":
            wrapped = (
                "SELF IMPROVEMENT WORKSHOP REQUEST:\n"
                "Apollo may inspect its own source read-only, reason about improvements, and build new workspace prototypes or pending modules.\n"
                "SELF-IMPROVEMENT SAFETY RULE: never overwrite Apollo core or silently install/enable your own changes. "
                "Use module_factory for Apollo extensions, keep them in pending_modules, validate them, and wait for explicit user approval.\n"
                "Use file_builder only for prototypes/patch projects under workspace.\n\n"
                "REQUEST:\n" + prompt
            )
            self.code_output.setPlainText("Self-improvement request sent with approval gate active.")

        else:
            wrapped = (
                "CODING WORKSPACE REQUEST:\n"
                "Create this as REAL FILES, not just code blocks in chat.\n\n"
                "TOOL ROUTING RULES:\n"
                "1. For an ORDINARY project, use ONE file_builder__write_files call for the coherent multi-file project under Apollo/workspace.\n"
                "2. Every code block/source/config/README needed by the project must become a real file; filenames/imports/paths must agree.\n"
                "3. Apollo will statically verify Python syntax and local project links/imports after writing. Repair real failures instead of claiming success.\n"
                "4. For an APOLLO MODULE / PLUGIN / NEW APOLLO FEATURE, DO NOT use file_builder. Read module_factory__get_contract, create a pending candidate, validate it, then STOP for approval.\n"
                "5. Never repeat the same tool call with identical arguments.\n\n"
                "REQUEST:\n" + prompt
            )
            self.code_output.setPlainText(
                "Real-project build request sent. Apollo will write the whole project and check the files together."
            )

        self.chat_input.setText(wrapped)
        self.send_chat()

    def open_workspace_folder(self):
        workspace = (BASE_DIR / "workspace").resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(workspace)))

    def _build_modules(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.addWidget(label("Modules", 22, "#e7fffb", True))
        v.addWidget(label(
            "Accepted modules are validated in a separate Python process before Apollo "
            "loads them. New/generated modules go into pending_modules first and cannot "
            "be accepted unless validation passes. Installed modules can be moved back "
            "to pending for editing/repair or removed from Apollo.",
            10, "#91bdb6"
        ))

        v.addWidget(label("Accepted / Installed", 13, "#8cf0dc", True))
        self.modules_list = QListWidget()
        self.modules_list.itemSelectionChanged.connect(self.show_selected_module)
        v.addWidget(self.modules_list, 1)

        accepted_buttons = QHBoxLayout()
        reload_btn = QPushButton("Reload + Revalidate")
        reload_btn.clicked.connect(self.reload_modules)
        self.module_toggle_btn = QPushButton("Enable / Disable")
        self.module_toggle_btn.clicked.connect(self.toggle_selected_module)

        move_pending_btn = QPushButton("Move Back to Pending")
        move_pending_btn.clicked.connect(
            self.move_selected_module_to_pending
        )

        remove_module_btn = QPushButton("Remove Module")
        remove_module_btn.clicked.connect(
            self.remove_selected_installed_module
        )

        folder_btn = QPushButton("Open Modules Folder")
        folder_btn.clicked.connect(self.open_modules_folder)

        accepted_buttons.addWidget(reload_btn)
        accepted_buttons.addWidget(self.module_toggle_btn)
        accepted_buttons.addWidget(move_pending_btn)
        accepted_buttons.addWidget(remove_module_btn)
        accepted_buttons.addWidget(folder_btn)
        accepted_buttons.addStretch()
        v.addLayout(accepted_buttons)

        v.addWidget(label("Pending / Not Yet Installed", 13, "#e9c879", True))
        self.pending_modules_list = QListWidget()
        self.pending_modules_list.itemSelectionChanged.connect(
            self.show_selected_pending_module
        )
        v.addWidget(self.pending_modules_list, 1)

        pending_buttons = QHBoxLayout()
        validate_btn = QPushButton("Validate Selected")
        validate_btn.clicked.connect(self.validate_selected_pending_module)

        self.auto_repair_btn = QPushButton("Auto Repair + Test")
        self.auto_repair_btn.clicked.connect(
            self.auto_repair_selected_pending_module
        )

        accept_btn = QPushButton("Accept Valid Module")
        accept_btn.clicked.connect(self.accept_selected_pending_module)

        remove_pending_btn = QPushButton("Remove Pending")
        remove_pending_btn.clicked.connect(
            self.remove_selected_pending_module
        )

        pending_folder_btn = QPushButton("Open Pending Folder")
        pending_folder_btn.clicked.connect(self.open_pending_modules_folder)

        pending_buttons.addWidget(validate_btn)
        pending_buttons.addWidget(self.auto_repair_btn)
        pending_buttons.addWidget(accept_btn)
        pending_buttons.addWidget(remove_pending_btn)
        pending_buttons.addWidget(pending_folder_btn)
        pending_buttons.addStretch()
        v.addLayout(pending_buttons)

        ui_row = QHBoxLayout()
        ui_row.addWidget(label("Selected Module UI:", 10, "#91bdb6", True))

        self.module_ui_combo = QComboBox()
        self.module_ui_combo.addItem("Hidden / Tool Only", "none")
        self.module_ui_combo.addItem("Settings → Apps", "apps")
        self.module_ui_combo.addItem("Sidebar Tab", "sidebar")

        self.module_ui_apply_btn = QPushButton("Apply UI Placement")
        self.module_ui_apply_btn.clicked.connect(
            self.apply_selected_module_ui_placement
        )

        ui_row.addWidget(self.module_ui_combo)
        ui_row.addWidget(self.module_ui_apply_btn)
        ui_row.addStretch()

        v.addLayout(ui_row)

        self.module_details = QTextBrowser()
        self.module_details.setMaximumHeight(210)
        self.module_details.setPlaceholderText(
            "Select an installed or pending module to see its validation details."
        )
        v.addWidget(self.module_details)

        self.refresh_modules_ui()
        return page

    def refresh_modules_ui(self):
        if not hasattr(self, "modules_list"):
            return

        self.modules_list.clear()
        for module in self.module_manager.list_modules():
            if module.get("error"):
                state = "ERROR - NOT LOADED"
            elif module.get("enabled") and module.get("loaded"):
                state = "ENABLED ✓ VALIDATED"
            else:
                state = "DISABLED ✓ VALIDATED"

            item = QListWidgetItem(
                f"{module.get('name', module['id'])}  [{state}]\n"
                f"{module.get('description', '')}"
            )
            item.setData(Qt.UserRole, module["id"])
            self.modules_list.addItem(item)

        if hasattr(self, "pending_modules_list"):
            self.pending_modules_list.clear()
            self.module_manager.refresh_pending()

            for module in self.module_manager.list_pending():
                validation = module.get("validation")
                if validation is None:
                    state = "PENDING - NOT VALIDATED"
                elif validation.get("ok"):
                    state = "VALID ✓ - WAITING FOR APPROVAL"
                else:
                    state = "ERROR ✗ - WILL NOT BE ACCEPTED"

                item = QListWidgetItem(
                    f"{module.get('name', module['id'])}  [{state}]\n"
                    f"{module.get('description', '')}"
                )
                item.setData(Qt.UserRole, module["id"])
                self.pending_modules_list.addItem(item)

        self._queue_ui_state_save()

    def reload_modules(self):
        self.module_manager.reload()
        self.refresh_modules_ui()
        self.refresh_status()
        self.refresh_neural_status()
        self.refresh_web_status()
        self.rebuild_module_ui()

        errors = self.module_manager.errors()
        if errors:
            QMessageBox.warning(
                self,
                "Apollo Modules",
                "Module scan completed, but one or more accepted folders FAILED "
                "validation and were NOT loaded. Select them to inspect the error."
            )
        else:
            QMessageBox.information(
                self,
                "Apollo Modules",
                f"Validation complete. "
                f"{len(self.module_manager.list_modules())} accepted module folder(s) scanned."
            )

    def _selected_module_id(self):
        selected = self.modules_list.selectedItems() if hasattr(self, "modules_list") else []
        if not selected:
            return None
        return selected[0].data(Qt.UserRole)

    def _selected_pending_id(self):
        selected = (
            self.pending_modules_list.selectedItems()
            if hasattr(self, "pending_modules_list")
            else []
        )
        if not selected:
            return None
        return selected[0].data(Qt.UserRole)

    def show_selected_module(self):
        module_id = self._selected_module_id()
        if not module_id:
            return
        self._queue_ui_state_save()

        if hasattr(self, "pending_modules_list"):
            self.pending_modules_list.clearSelection()

        record = self.module_manager.get_module(module_id)
        if record is None:
            errors = self.module_manager.errors()
            self.module_details.setPlainText(
                "VALIDATION/LOAD ERROR\n\n"
                + errors.get(module_id, "Module did not load.")
            )
            return

        manifest = record["manifest"]
        tool_lines = [
            f"• {module_id}.{tool.get('name')}: {tool.get('description', '')}"
            for tool in record.get("tools", [])
        ] or ["No tools exposed."]

        validation = record.get("validation", {})
        if hasattr(self, "module_ui_combo"):
            has_ui = self.module_manager.module_has_ui(module_id)
            self.module_ui_combo.setEnabled(has_ui)
            self.module_ui_apply_btn.setEnabled(has_ui)

            if has_ui:
                placement = self.module_manager.get_ui_placement(module_id)
                index = self.module_ui_combo.findData(placement)
                if index >= 0:
                    self.module_ui_combo.setCurrentIndex(index)

        self.module_details.setPlainText(
            f"Name: {manifest.get('name', module_id)}\n"
            f"ID: {module_id}\n"
            f"Version: {manifest.get('version', '?')}\n"
            f"Enabled: {record.get('enabled')}\n"
            f"Validation: {'PASSED' if validation.get('ok') else 'FAILED'}\n"
            f"Has UI: {self.module_manager.module_has_ui(module_id)}\n"
            f"UI placement: {self.module_manager.get_ui_placement(module_id) if self.module_manager.module_has_ui(module_id) else 'n/a'}\n"
            f"UI surfaces: {', '.join(self.module_manager.get_ui_surfaces(module_id)) or 'none'}\n"
            f"Pinned on Hub: {self.shell.is_pinned('module.' + module_id)}\n"
            f"Folder: {record.get('folder')}\n\n"
            "Exposed tools:\n" + "\n".join(tool_lines)
        )

    def show_selected_pending_module(self):
        module_id = self._selected_pending_id()
        if not module_id:
            return
        self._queue_ui_state_save()

        self.modules_list.clearSelection()
        record = self.module_manager.get_pending(module_id)
        if record is None:
            self.module_details.setPlainText("Pending module not found.")
            return

        validation = record.get("validation")
        if validation is None:
            validation_text = "NOT YET VALIDATED"
        elif validation.get("ok"):
            validation_text = (
                "PASSED\n"
                f"Tools: {', '.join(validation.get('tools', [])) or 'none'}\n"
                f"Self-test: {validation.get('self_test')}"
            )
        else:
            validation_text = (
                "FAILED - MODULE CANNOT BE ACCEPTED\n"
                + validation.get("error", "Unknown error")
            )

        self.module_details.setPlainText(
            f"Pending module: {record.get('name', module_id)}\n"
            f"ID: {module_id}\n"
            f"Version: {record.get('version', '?')}\n"
            f"Folder: {record.get('folder')}\n\n"
            f"VALIDATION:\n{validation_text}\n\n"
            "Pending modules are not available to Apollo until validation passes "
            "and you explicitly accept them."
        )

    def apply_selected_module_ui_placement(self):
        module_id = self._selected_module_id()
        if not module_id:
            QMessageBox.information(
                self,
                "Apollo Module UI",
                "Select an installed module first."
            )
            return

        if not self.module_manager.module_has_ui(module_id):
            QMessageBox.warning(
                self,
                "Apollo Module UI",
                "That module does not provide a build_ui() page."
            )
            return

        placement = self.module_ui_combo.currentData()

        try:
            self.module_manager.set_ui_placement(
                module_id,
                placement,
            )
            self.rebuild_module_ui()
            self.show_selected_module()
            self._save_ui_state()
            QMessageBox.information(
                self,
                "Apollo Module UI",
                f"{module_id} UI placement saved as: {placement}."
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Apollo Module UI",
                str(exc)
            )

    def validate_selected_pending_module(self):
        module_id = self._selected_pending_id()
        if not module_id:
            QMessageBox.information(
                self, "Apollo Modules", "Select a pending module first."
            )
            return

        result = self.module_manager.validate_pending(module_id)
        self.refresh_modules_ui()

        # Re-select so details remain visible.
        for i in range(self.pending_modules_list.count()):
            item = self.pending_modules_list.item(i)
            if item.data(Qt.UserRole) == module_id:
                item.setSelected(True)
                break

        if result.get("ok"):
            QMessageBox.information(
                self,
                "Module Validation Passed",
                f"{module_id} passed compile, import, tool-schema and self-test checks. "
                "It is still NOT installed until you press Accept Valid Module."
            )
        else:
            QMessageBox.warning(
                self,
                "Module Validation Failed",
                f"{module_id} was NOT accepted.\n\n"
                + result.get("error", "Unknown validation error")
            )

    def _select_pending_module(self, module_id):
        for i in range(self.pending_modules_list.count()):
            item = self.pending_modules_list.item(i)
            if item.data(Qt.UserRole) == module_id:
                item.setSelected(True)
                self.pending_modules_list.scrollToItem(item)
                return

    @Slot()
    def auto_repair_selected_pending_module(self):
        module_id = self._selected_pending_id()
        if not module_id:
            QMessageBox.information(
                self,
                "Apollo Module Repair",
                "Select a pending module first."
            )
            return

        if self.module_repair_task is not None:
            QMessageBox.information(
                self,
                "Apollo Module Repair",
                "Apollo is already repairing another pending module."
            )
            return

        if not self.client.is_running():
            QMessageBox.warning(
                self,
                "Apollo Module Repair",
                "Ollama is offline. Start Ollama before automatic repair."
            )
            return

        self.auto_repair_btn.setEnabled(False)
        self.auto_repair_btn.setText("Repairing...")

        self.module_details.setPlainText(
            f"AUTO REPAIR: {module_id}\n\n"
            "Apollo will validate the existing pending files, read the exact errors, "
            "rewrite only the pending candidate, and rerun tests. It will repeat up "
            "to 6 repair attempts.\n\n"
            "The module will NOT be installed automatically.\n"
        )

        task = ModuleRepairTask(
            self.module_repair_engine,
            module_id,
            max_attempts=6,
        )
        self.module_repair_task = task

        task.signals.progress.connect(
            self.on_module_repair_progress,
            Qt.QueuedConnection
        )
        task.signals.finished.connect(
            self.on_module_repair_finished,
            Qt.QueuedConnection
        )
        task.signals.failed.connect(
            self.on_module_repair_failed,
            Qt.QueuedConnection
        )
        task.signals.completed.connect(
            self.on_module_repair_completed,
            Qt.QueuedConnection
        )

        self.thread_pool.start(task)

    @Slot(str)
    def on_module_repair_progress(self, message):
        current = self.module_details.toPlainText()
        if len(current) > 16000:
            current = current[-12000:]
        self.module_details.setPlainText(
            current + "\n" + message
        )
        bar = self.module_details.verticalScrollBar()
        bar.setValue(bar.maximum())

    @Slot(dict)
    def on_module_repair_finished(self, result):
        module_id = result.get("module_id", "module")
        self.module_manager.refresh_pending()
        self.refresh_modules_ui()
        self._select_pending_module(module_id)

        if result.get("ok"):
            validation = result.get("validation", {})
            tests = validation.get("external_tests", {})
            test_note = (
                tests.get("output", "tests passed")
                if tests.get("present")
                else "self_test/API validation passed"
            )

            QMessageBox.information(
                self,
                "Apollo Module Repair Passed",
                f"{module_id} now passes validation.\n\n"
                f"Repair attempts: {result.get('attempts', 0)}\n"
                f"Tests: {test_note}\n\n"
                "It is still pending. Review it, then press Accept Valid Module "
                "if you want Apollo to install it."
            )
        else:
            validation = result.get("validation", {})
            QMessageBox.warning(
                self,
                "Apollo Module Repair Stopped",
                f"{module_id} still fails after "
                f"{result.get('attempts', 0)} attempts.\n\n"
                + validation.get("error", "Unknown validation failure")
                + "\n\nThe candidate remains pending and can be repaired again."
            )

    @Slot(str)
    def on_module_repair_failed(self, error):
        QMessageBox.critical(
            self,
            "Apollo Module Repair Error",
            error
        )

    @Slot()
    def on_module_repair_completed(self):
        self.module_repair_task = None
        if hasattr(self, "auto_repair_btn"):
            self.auto_repair_btn.setEnabled(True)
            self.auto_repair_btn.setText("Auto Repair + Test")

    def accept_selected_pending_module(self):
        module_id = self._selected_pending_id()
        if not module_id:
            QMessageBox.information(
                self, "Apollo Modules", "Select a pending module first."
            )
            return

        # Always validate immediately before approval.
        result = self.module_manager.validate_pending(module_id)
        if not result.get("ok"):
            self.refresh_modules_ui()
            QMessageBox.warning(
                self,
                "Cannot Accept Module",
                "Apollo blocked this module because validation failed.\n\n"
                + result.get("error", "Unknown validation error")
            )
            return

        answer = QMessageBox.question(
            self,
            "Approve Module Installation",
            f"'{module_id}' passed validation.\n\n"
            "Accept it into Apollo's live modules folder?\n\n"
            "The module will then run with Apollo's local user permissions.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            activation = self.module_manager.activate_certified_pending(
                module_id,
                approved=True,
                replace_existing=False,
            )
            if not activation.get("ok"):
                raise RuntimeError(
                    activation.get("error")
                    or f"Certified activation failed at stage: {activation.get('stage')}"
                )

            self.refresh_modules_ui()
            self.refresh_status()
            self.rebuild_module_ui()
            try:
                self._refresh_hub_tiles()
            except Exception:
                pass

            QMessageBox.information(
                self,
                "Module Certified + Active",
                f"{module_id} passed validation, was approved, and is now live in Apollo."
            )
        except Exception as exc:
            self.refresh_modules_ui()
            QMessageBox.critical(
                self,
                "Module Acceptance Failed",
                str(exc)
            )

    def move_selected_module_to_pending(self):
        module_id = self._selected_module_id()
        if not module_id:
            QMessageBox.information(
                self,
                "Apollo Modules",
                "Select an installed module first."
            )
            return

        answer = QMessageBox.question(
            self,
            "Move Module Back to Pending",
            f"Move '{module_id}' out of Apollo's live modules and back into "
            "pending_modules?\n\n"
            "Apollo will unload it immediately. It will no longer provide tools "
            "or a UI until you validate and accept it again.\n\n"
            "Its module files are preserved and can be edited/repaired while pending.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            # Delete any live module-created page before unloading/moving its files.
            self.rebuild_module_ui()

            result = self.module_manager.move_to_pending(module_id)

            self.refresh_modules_ui()
            self.refresh_status()
            self.refresh_neural_status()
            self.refresh_web_status()
            self.rebuild_module_ui()
            self._select_pending_module(module_id)

            validation = result.get("validation", {})
            if validation.get("ok"):
                validation_note = (
                    "The moved module already passes validation and is waiting "
                    "for approval."
                )
            else:
                validation_note = (
                    "The moved module is pending and currently fails validation:\n\n"
                    + validation.get("error", "Unknown validation error")
                )

            QMessageBox.information(
                self,
                "Module Moved to Pending",
                f"{module_id} was unloaded and moved to pending_modules.\n\n"
                + validation_note
            )

        except Exception as exc:
            self.refresh_modules_ui()
            self.rebuild_module_ui()
            QMessageBox.critical(
                self,
                "Move to Pending Failed",
                str(exc)
            )

    def remove_selected_installed_module(self):
        module_id = self._selected_module_id()
        if not module_id:
            QMessageBox.information(
                self,
                "Apollo Modules",
                "Select an installed module first."
            )
            return

        answer = QMessageBox.warning(
            self,
            "Remove Installed Module",
            f"PERMANENTLY remove '{module_id}' from Apollo?\n\n"
            "This deletes the module's folder from modules/ and removes its "
            "enabled/UI-placement state.\n\n"
            "Module-specific data stored elsewhere (for example Apollo/storage/) "
            "is NOT deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self.rebuild_module_ui()
            self.module_manager.remove_installed(module_id)

            self.refresh_modules_ui()
            self.refresh_status()
            self.refresh_neural_status()
            self.refresh_web_status()
            self.rebuild_module_ui()

            self.module_details.setPlainText(
                f"{module_id} was removed from Apollo."
            )

            QMessageBox.information(
                self,
                "Module Removed",
                f"{module_id} was removed from the live modules folder."
            )

        except Exception as exc:
            self.refresh_modules_ui()
            self.rebuild_module_ui()
            QMessageBox.critical(
                self,
                "Module Removal Failed",
                str(exc)
            )

    def remove_selected_pending_module(self):
        module_id = self._selected_pending_id()
        if not module_id:
            QMessageBox.information(
                self,
                "Apollo Modules",
                "Select a pending module first."
            )
            return

        answer = QMessageBox.warning(
            self,
            "Remove Pending Module",
            f"PERMANENTLY delete the pending candidate '{module_id}'?\n\n"
            "Its pending module files and repair history will be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self.module_manager.remove_pending(module_id)
            self.refresh_modules_ui()

            self.module_details.setPlainText(
                f"Pending module {module_id} was removed."
            )

            QMessageBox.information(
                self,
                "Pending Module Removed",
                f"{module_id} was deleted from pending_modules."
            )

        except Exception as exc:
            self.refresh_modules_ui()
            QMessageBox.critical(
                self,
                "Pending Module Removal Failed",
                str(exc)
            )

    def toggle_selected_module(self):
        module_id = self._selected_module_id()
        if not module_id:
            QMessageBox.information(
                self, "Apollo Modules", "Select an accepted module first."
            )
            return

        record = self.module_manager.get_module(module_id)
        if record is None:
            QMessageBox.warning(
                self,
                "Apollo Modules",
                "That module failed validation/load and cannot be enabled."
            )
            return

        self.module_manager.set_enabled(
            module_id,
            not record.get("enabled", False)
        )
        self.refresh_modules_ui()
        self.refresh_status()
        self.rebuild_module_ui()

    def open_modules_folder(self):
        QDesktopServices.openUrl(
            QUrl.fromLocalFile(str((BASE_DIR / "modules").resolve()))
        )

    def open_pending_modules_folder(self):
        pending = (BASE_DIR / "pending_modules").resolve()
        pending.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(pending)))

    def _build_system(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.addWidget(label("System", 22, "#e7fffb", True))

        c = Card("Local system")
        self.sys_cpu = QProgressBar()
        self.sys_ram = QProgressBar()
        self.sys_gpu = label("GPU: optional monitoring not configured", 11, "#91bdb6")
        self.sys_model = label("Model: checking...", 11, "#6fe4cf")
        self.sys_ollama = label("Ollama: checking...", 11, "#6fe4cf")

        c.layout.addWidget(label("CPU", 11, "#c1ded9"))
        c.layout.addWidget(self.sys_cpu)
        c.layout.addWidget(label("RAM", 11, "#c1ded9"))
        c.layout.addWidget(self.sys_ram)
        c.layout.addWidget(self.sys_gpu)
        c.layout.addWidget(self.sys_model)
        c.layout.addWidget(self.sys_ollama)

        v.addWidget(c)
        v.addStretch()
        gpu = Card("NVIDIA GPU")
        self.gpu_name_label = label("GPU: checking...", 12, "#dffbf5", True)
        self.gpu_usage_label = label("Usage: —", 10, "#91bdb6")
        self.gpu_usage_bar = QProgressBar()
        self.gpu_usage_bar.setRange(0, 100)

        self.gpu_vram_label = label("VRAM: —", 10, "#91bdb6")
        self.gpu_vram_bar = QProgressBar()
        self.gpu_vram_bar.setRange(0, 100)

        self.gpu_temp_label = label("Temperature: —", 10, "#91bdb6")
        self.gpu_power_label = label("Power: —", 10, "#91bdb6")

        gpu.layout.addWidget(self.gpu_name_label)
        gpu.layout.addWidget(self.gpu_usage_label)
        gpu.layout.addWidget(self.gpu_usage_bar)
        gpu.layout.addWidget(self.gpu_vram_label)
        gpu.layout.addWidget(self.gpu_vram_bar)
        gpu.layout.addWidget(self.gpu_temp_label)
        gpu.layout.addWidget(self.gpu_power_label)

        v.addWidget(gpu)

        self.refresh_gpu_status()

        return page

    def _build_memory(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.addWidget(label("Memory", 22, "#e7fffb", True))

        self.memory_list = QListWidget()
        v.addWidget(self.memory_list, 1)

        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_memory)
        v.addWidget(refresh)

        return page

    def refresh_memory(self):
        self.memory_list.clear()
        memories = self.memory.recent_memories(20)
        if not memories:
            self.memory_list.addItem("No learned memories yet.")
        else:
            for m in memories:
                self.memory_list.addItem(
                    f"{m['kind'].upper()} — {m['title']}\n{m['body']}"
                )

        preview = memories[:3]
        if preview:
            self.hub_memory.setText(
                "\n".join("• " + x["title"] for x in preview)
            )
        else:
            self.hub_memory.setText("No memories stored yet.")

    def refresh_gpu_status(self):
        if not hasattr(self, "gpu_name_label"):
            return

        try:
            record = self.module_manager.get_module("gpu_monitor")
            if (
                not record
                or not record.get("enabled")
                or record.get("instance") is None
            ):
                self.gpu_name_label.setText(
                    "GPU Monitor module unavailable or disabled"
                )
                return

            status = self.module_manager.execute(
                "gpu_monitor",
                "gpu_status",
                {},
            )

            gpus = status.get("gpus", [])
            if not gpus:
                self.gpu_name_label.setText(
                    "No NVIDIA GPU detected"
                )
                return

            gpu = gpus[0]

            usage = int(gpu.get("utilization_percent") or 0)
            used = float(gpu.get("memory_used_mb") or 0)
            total = float(gpu.get("memory_total_mb") or 0)
            percent = int((used / total) * 100) if total else 0

            self.gpu_name_label.setText(
                f"GPU: {gpu.get('name', 'NVIDIA GPU')}"
            )
            self.gpu_usage_label.setText(
                f"Usage: {usage}%"
            )
            self.gpu_usage_bar.setValue(max(0, min(usage, 100)))

            self.gpu_vram_label.setText(
                f"VRAM: {used/1024:.2f} / {total/1024:.2f} GB"
            )
            self.gpu_vram_bar.setValue(max(0, min(percent, 100)))

            temp = gpu.get("temperature_c")
            power = gpu.get("power_draw_w")
            limit = gpu.get("power_limit_w")

            self.gpu_temp_label.setText(
                f"Temperature: {temp:.0f}°C"
                if temp is not None else "Temperature: —"
            )

            if power is not None and limit is not None:
                self.gpu_power_label.setText(
                    f"Power: {power:.1f} / {limit:.1f} W"
                )
            elif power is not None:
                self.gpu_power_label.setText(
                    f"Power: {power:.1f} W"
                )
            else:
                self.gpu_power_label.setText("Power: —")

        except Exception as exc:
            self.gpu_name_label.setText(
                f"GPU Monitor unavailable: {exc}"
            )

    def _build_settings(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.addWidget(
            label(
                "Settings",
                22,
                "#e7fffb",
                True,
            )
        )

        self.settings_tabs = QTabWidget()

        # General settings
        self.settings_general_tab = QWidget()
        general_layout = QVBoxLayout(
            self.settings_general_tab
        )

        c = Card("AI Model / Ollama")
        self.setting_url = QLineEdit(
            self.config["ollama_url"]
        )

        self.setting_model = QComboBox()
        self.setting_model.setEditable(True)
        self.setting_model.setInsertPolicy(
            QComboBox.NoInsert
        )
        self.setting_model.addItem(
            self.config["model"]
        )
        self.setting_model.setCurrentText(
            self.config["model"]
        )
        self.setting_model.setToolTip(
            "Choose any model installed in Ollama. Apollo keeps the same memory, "
            "modules and personality; only the language model is swapped."
        )

        self.setting_model_status = label(
            (
                "Selected model: "
                f"{self.config['model']}\n"
                "Press Refresh Installed Models to scan Ollama."
            ),
            9,
            "#74bfb2",
        )

        model_buttons = QHBoxLayout()

        refresh_models = QPushButton(
            "Refresh Installed Models"
        )
        refresh_models.clicked.connect(
            self.refresh_model_selector
        )

        save = QPushButton(
            "Save & Switch Model"
        )
        save.clicked.connect(
            self.save_settings
        )

        model_buttons.addWidget(
            refresh_models
        )
        model_buttons.addWidget(
            save
        )

        c.layout.addWidget(
            label(
                "Ollama URL",
                10,
                "#9fc8c1",
            )
        )
        c.layout.addWidget(
            self.setting_url
        )
        c.layout.addWidget(
            label(
                "Apollo language model",
                10,
                "#9fc8c1",
            )
        )
        c.layout.addWidget(
            self.setting_model
        )
        c.layout.addWidget(
            self.setting_model_status
        )
        c.layout.addLayout(
            model_buttons
        )

        model_note = label(
            (
                "Switching the model does not reset Apollo. Memory, learned knowledge, "
                "modules, To-Do items, Voice Studio and the rest of Apollo stay loaded. "
                "The selected Ollama model is used for the next AI request."
            ),
            9,
            "#6da59d",
        )
        c.layout.addWidget(
            model_note
        )

        general_layout.addWidget(
            c
        )

        routing_card = Card("Apollo 7.5 Model Routing")
        self.setting_auto_model_routing = QCheckBox(
            "Automatically choose General / Coding / Reasoning / Fast / Vision role per request"
        )
        self.setting_auto_model_routing.setChecked(
            bool(self.config.get("auto_model_routing", False))
        )
        routing_card.layout.addWidget(self.setting_auto_model_routing)
        routing_card.layout.addWidget(
            label(
                "Role-to-model mappings are managed by the Model Runtime capability. Manual model selection above remains the fallback.",
                9,
                "#6da59d",
            )
        )
        general_layout.addWidget(routing_card)
        general_layout.addStretch()

        # Patch Notes are file-backed so future releases only need to update
        # PATCH_NOTES.md. The Settings view reloads that file on demand.
        self.settings_patch_notes_tab = QWidget()
        patch_notes_layout = QVBoxLayout(
            self.settings_patch_notes_tab
        )

        patch_notes_header = QHBoxLayout()
        patch_notes_header.addWidget(
            label(
                "Apollo Patch Notes",
                16,
                "#e7fffb",
                True,
            )
        )
        patch_notes_header.addStretch(1)

        patch_notes_reload = QPushButton(
            "Reload Notes"
        )
        patch_notes_reload.clicked.connect(
            self.refresh_patch_notes
        )

        patch_notes_open = QPushButton(
            "Open Notes File"
        )
        patch_notes_open.clicked.connect(
            self.open_patch_notes_file
        )

        patch_notes_header.addWidget(
            patch_notes_reload
        )
        patch_notes_header.addWidget(
            patch_notes_open
        )
        patch_notes_layout.addLayout(
            patch_notes_header
        )

        self.patch_notes_source_label = label(
            "",
            9,
            "#6da59d",
        )
        patch_notes_layout.addWidget(
            self.patch_notes_source_label
        )

        self.patch_notes_view = QTextBrowser()
        self.patch_notes_view.setOpenExternalLinks(
            True
        )
        self.patch_notes_view.setReadOnly(
            True
        )
        patch_notes_layout.addWidget(
            self.patch_notes_view,
            1,
        )

        # Module Apps are no longer a top-level sidebar destination.
        self.settings_apps_tab = (
            self._build_apps()
        )

        self.settings_tabs.addTab(
            self.settings_general_tab,
            "General",
        )
        self.settings_tabs.addTab(
            self.settings_patch_notes_tab,
            "Patch Notes",
        )
        self.settings_tabs.addTab(
            self.settings_apps_tab,
            "Apps",
        )

        # Same Sidebar Manager as the sidebar shortcut; no duplicate settings.
        self.settings_sidebar_tab = QWidget()
        sidebar_settings = QVBoxLayout(self.settings_sidebar_tab)
        sidebar_settings.addWidget(label(
            "Choose which built-in pages and installed module shortcuts appear, "
            "change their order and labels, or collapse the sidebar to icons.",
            11, "#a5d1c8"
        ))
        sidebar_settings_btn = QPushButton("Open Sidebar Manager")
        sidebar_settings_btn.clicked.connect(self.open_sidebar_manager)
        sidebar_settings.addWidget(sidebar_settings_btn)
        sidebar_settings.addStretch()
        self.settings_tabs.addTab(self.settings_sidebar_tab, "Sidebar")

        self.settings_tabs.currentChanged.connect(
            self._settings_tab_changed
        )

        self.refresh_patch_notes()

        v.addWidget(
            self.settings_tabs,
            1,
        )

        return page

    def _settings_tab_changed(self, index):
        self._queue_ui_state_save()

        if (
            hasattr(
                self,
                "settings_patch_notes_tab",
            )
            and self.settings_tabs.widget(index)
            is self.settings_patch_notes_tab
        ):
            self.refresh_patch_notes()

    def _patch_notes_path(self):
        return PATCH_DOCS.patch_notes_path

    def refresh_patch_notes(self):
        if not hasattr(
            self,
            "patch_notes_view",
        ):
            return

        path = self._patch_notes_path()

        if hasattr(
            self,
            "patch_notes_source_label",
        ):
            self.patch_notes_source_label.setText(
                "Source file: "
                + str(path)
            )

        if not path.exists():
            self.patch_notes_view.setPlainText(
                "PATCH_NOTES.md was not found.\n\n"
                "Apollo expects it under docs/patch_notes/."
            )
            return

        try:
            text = path.read_text(
                encoding="utf-8",
                errors="replace",
            )

            if hasattr(
                self.patch_notes_view,
                "setMarkdown",
            ):
                self.patch_notes_view.setMarkdown(
                    text
                )
            else:
                self.patch_notes_view.setPlainText(
                    text
                )

        except Exception as exc:
            self.patch_notes_view.setPlainText(
                "Could not read patch notes:\n"
                + str(exc)
            )

    def open_patch_notes_file(self):
        path = self._patch_notes_path()

        if not path.exists():
            QMessageBox.warning(
                self,
                "Apollo",
                "PATCH_NOTES.md does not exist yet.",
            )
            return

        opened = QDesktopServices.openUrl(
            QUrl.fromLocalFile(
                str(path)
            )
        )

        if not opened:
            QMessageBox.warning(
                self,
                "Apollo",
                "Windows could not open the patch-notes file.",
            )

    def refresh_model_selector(self):
        """Refresh the Settings model selector from Ollama's installed models."""
        configured = self.setting_model.currentText().strip()

        if not configured:
            configured = str(
                self.config.get(
                    "model",
                    "",
                )
                or ""
            ).strip()

        test_client = OllamaClient(
            self.setting_url.text().strip()
            or self.config["ollama_url"],
            configured
            or self.config["model"],
            self.config.get(
                "temperature",
                0.65,
            ),
            self.config.get(
                "num_ctx",
                8192,
            ),
        )

        try:
            models = test_client.models()
        except Exception as exc:
            self.setting_model_status.setText(
                "Could not read Ollama models: "
                + str(exc)
            )
            return

        current = configured

        self.setting_model.blockSignals(
            True
        )
        self.setting_model.clear()

        for model_name in models:
            self.setting_model.addItem(
                model_name
            )

        if (
            current
            and self.setting_model.findText(
                current
            ) < 0
        ):
            self.setting_model.addItem(
                current
            )

        if current:
            self.setting_model.setCurrentText(
                current
            )
        elif models:
            self.setting_model.setCurrentIndex(
                0
            )

        self.setting_model.blockSignals(
            False
        )

        if models:
            self.setting_model_status.setText(
                f"{len(models)} installed Ollama model(s) found. "
                "Choose one, then press Save & Switch Model."
            )
        else:
            self.setting_model_status.setText(
                "Ollama is running, but no installed models were returned."
            )

    def save_settings(self):
        ollama_url = self.setting_url.text().strip()
        selected_model = self.setting_model.currentText().strip()

        if not ollama_url:
            QMessageBox.warning(
                self,
                "Apollo",
                "Enter an Ollama URL first.",
            )
            return

        if not selected_model:
            QMessageBox.warning(
                self,
                "Apollo",
                "Choose or enter an Ollama model first.",
            )
            return

        # Verify the chosen model when Ollama is reachable. If Ollama is offline,
        # keep the user's selection so Apollo can use it when the service returns.
        test_client = OllamaClient(
            ollama_url,
            selected_model,
            self.config.get(
                "temperature",
                0.65,
            ),
            self.config.get(
                "num_ctx",
                8192,
            ),
        )

        ollama_online = False
        installed_models = []

        try:
            installed_models = test_client.models()
            ollama_online = True
        except Exception:
            ollama_online = False

        if (
            ollama_online
            and installed_models
            and selected_model
            not in installed_models
        ):
            QMessageBox.warning(
                self,
                "Apollo",
                (
                    f"'{selected_model}' is not installed in Ollama.\n\n"
                    "Press Refresh Installed Models and choose one of the installed models."
                ),
            )
            return

        old_model = str(
            self.config.get(
                "model",
                "",
            )
            or ""
        )

        self.config["ollama_url"] = ollama_url
        self.config["model"] = selected_model
        self.config["auto_model_routing"] = bool(
            self.setting_auto_model_routing.isChecked()
        )

        (BASE_DIR / "config.json").write_text(
            json.dumps(
                self.config,
                indent=2,
            ),
            encoding="utf-8",
        )

        # Hot-swap the client used by new ChatTask instances.
        self.client = OllamaClient(
            self.config["ollama_url"],
            self.config["model"],
            self.config.get(
                "temperature",
                0.65,
            ),
            self.config.get(
                "num_ctx",
                8192,
            ),
        )

        # The pending-module repair engine keeps its own client reference, so it
        # must follow the same selected brain instead of silently using the old one.
        if hasattr(
            self,
            "module_repair_engine",
        ):
            self.module_repair_engine.client = (
                self.client
            )

        self.setting_model_status.setText(
            "Active selection: "
            + selected_model
        )

        self.refresh_status()

        if (
            self.chat_busy
            and old_model != selected_model
        ):
            message = (
                f"Model changed from '{old_model}' to '{selected_model}'.\n\n"
                "The response already being generated will finish on the old model. "
                "The next request will use the new model."
            )
        elif old_model != selected_model:
            message = (
                f"Apollo switched from '{old_model}' to '{selected_model}'.\n\n"
                "Memory, modules and learned knowledge were kept."
            )
        else:
            message = (
                f"Settings saved. Apollo is using '{selected_model}'."
            )

        QMessageBox.information(
            self,
            "Apollo",
            message,
        )

    def _setup_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_metrics)
        self.timer.start(1500)
        self.update_metrics()

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.refresh_status)
        self.status_timer.start(15000)

    def update_metrics(self):
        if psutil:
            cpu = int(psutil.cpu_percent(interval=None))
            ram = int(psutil.virtual_memory().percent)
        else:
            cpu = 0
            ram = 0

        for bar in [self.hub_cpu, self.sys_cpu]:
            bar.setValue(cpu)
        for bar in [self.hub_ram, self.sys_ram]:
            bar.setValue(ram)

    def refresh_status(self):
        running = self.client.is_running()

        if running:
            self.online_dot.setStyleSheet("color:#4cff9b;")
            self.online_text.setText("Apollo Online")
            try:
                model = self.client.best_model()
            except Exception:
                model = self.config["model"]

            configured_model = str(
                self.config.get(
                    "model",
                    model,
                )
                or model
            )

            if model != configured_model:
                model_text = (
                    f"{model} (fallback; selected {configured_model})"
                )
            else:
                model_text = model

            self.hub_model.setText(
                f"Model: {model_text}"
            )
            self.chat_model.setText(
                f"Model: {model_text}"
            )
            self.sys_model.setText(
                f"Model: {model_text}"
            )
            self.sys_ollama.setText("Ollama: online")

            status_items = [
                "●  Local model online",
                "●  Memory synced locally",
                "●  Approval-first design",
                f"●  {sum(1 for m in self.module_manager.list_modules() if m.get('enabled') and m.get('loaded'))} modules active",
                "●  Privacy by design",
            ]
        else:
            self.online_dot.setStyleSheet("color:#ff6969;")
            self.online_text.setText("Ollama Offline")
            self.hub_model.setText("Model: unavailable")
            self.chat_model.setText("Model: unavailable")
            self.sys_model.setText("Model: unavailable")
            self.sys_ollama.setText("Ollama: offline")

            status_items = [
                "●  Ollama offline",
                "●  Memory available locally",
                f"●  {sum(1 for m in self.module_manager.list_modules() if m.get('enabled') and m.get('loaded'))} modules active",
                "●  Start Ollama to chat",
            ]

        while self.hub_status_list.count():
            item = self.hub_status_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for text in status_items:
            self.hub_status_list.addWidget(
                label(text, 10, "#81ddca" if running else "#e2a1a1")
            )

    def refresh_stats(self):
        s = self.memory.stats()
        learned = s["lessons"] + s["facts"]
        self.hub_learning.setText(f"{learned} learned items")

    def closeEvent(self, event):
        # Persist UI and stop speech/background work before shutdown.
        try:
            self.stop_apollo_speech()
        except Exception:
            pass
        try:
            self._save_ui_state()
        except Exception:
            pass

        if self.chat_task is not None:
            self.chat_task.cancel()

        self.thread_pool.waitForDone(1800)

        try:
            self.memory.conn.close()
        except Exception:
            pass

        try:
            self.runtime.mark_clean_shutdown()
        except Exception:
            pass

        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Apollo")
    app.setStyle("Fusion")

    win = ApolloWindow()
    win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
