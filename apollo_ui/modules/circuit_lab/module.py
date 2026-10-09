"""Apollo Circuit Lab: electronics planning companion for Steam CRUMB.

The local LLM advises on a user-selected project; it never controls CRUMB,
reads arbitrary files, edits saved circuits or drives physical electronics.
"""
import json
from pathlib import Path

from apollo_circuit_lab import (
    EXAMPLES, CircuitProjectStore, inspect_crumb_save, resistor_for_led
)


class Module:
    def __init__(self, context=None):
        self.context = context or {}
        self.base = Path(self.context.get("base_dir", ".")).resolve()
        self.store = CircuitProjectStore(self.base)
        self._windows = []

    def tools(self):
        return [
            {
                "name": "circuit_example_templates",
                "description": "List beginner low-voltage electronics planning templates. No hardware control.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "circuit_led_resistor",
                "description": "Estimate current-limiting resistor for a low-voltage DC LED, not a verified circuit.",
                "parameters": {"type": "object", "properties": {
                    "supply_v": {"type": "number"},
                    "forward_v": {"type": "number"},
                    "target_ma": {"type": "number"},
                }, "required": ["supply_v"]},
            },
        ]

    def run(self, action, arguments):
        arguments = arguments or {}
        if action == "circuit_example_templates":
            return {"templates": [{"id": key, "name": value["name"],
                                   "scope": value["scope"]} for key, value in EXAMPLES.items()]}
        if action == "circuit_led_resistor":
            return resistor_for_led(arguments.get("supply_v"),
                                    arguments.get("forward_v", 2.0),
                                    arguments.get("target_ma", 10.0))
        raise KeyError(action)

    def self_test(self):
        assert {x["name"] for x in self.tools()} == {
            "circuit_example_templates", "circuit_led_resistor"
        }
        assert self.run("circuit_led_resistor", {"supply_v": 5})["suggested_e12_ohms"] == 330
        return "Circuit Lab templates and bounded electrical arithmetic passed."

    def build_ui(self, parent=None, ui_context=None):
        from PySide6.QtCore import QUrl, QObject, Qt, Signal
        from PySide6.QtGui import QDesktopServices, QGuiApplication
        from PySide6.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
            QLineEdit, QTextEdit, QPlainTextEdit, QDoubleSpinBox, QFileDialog,
            QMessageBox, QGroupBox
        )
        import threading
        context = ui_context or {}

        def build_page(popout=False):
            page = QWidget(None if popout else parent)
            page.setWindowTitle("Apollo Circuit Lab | CRUMB Companion")
            root = QVBoxLayout(page)
            top = QHBoxLayout()
            title = QLabel("Apollo Circuit Lab")
            title.setStyleSheet("font-size:23px; font-weight:800;")
            top.addWidget(title)
            top.addStretch()
            if not popout:
                popout_button = QPushButton("Split-screen Companion")
                top.addWidget(popout_button)
                popout_button.clicked.connect(open_popout)
            launch_button = QPushButton("Launch CRUMB in Steam")
            top.addWidget(launch_button)
            root.addLayout(top)

            notice = QLabel(
                "Apollo helps plan, calculate and review local CRUMB saves. "
                "The game stays in its own window; snap it to the right half of your screen. "
                "No live game control, save editing or verified simulation. "
                "Do not use these sketches directly for mains, lithium charging, "
                "medical devices, moving machinery or safety-critical hardware."
            )
            notice.setWordWrap(True)
            root.addWidget(notice)

            def launch_crumb():
                if not QDesktopServices.openUrl(QUrl("steam://rungameid/2198800")):
                    QMessageBox.information(
                        page, "CRUMB", "Steam could not open the game. Launch CRUMB from Steam manually."
                    )
            launch_button.clicked.connect(launch_crumb)

            project_row = QHBoxLayout()
            project_row.addWidget(QLabel("Electronics project"))
            selector = QComboBox()
            selector.setMinimumWidth(220)
            project_row.addWidget(selector, 1)
            refresh = QPushButton("Refresh")
            create = QPushButton("New Project")
            project_row.addWidget(refresh)
            project_row.addWidget(create)
            root.addLayout(project_row)

            example_row = QHBoxLayout()
            examples = QComboBox()
            examples.addItem("Blank design", None)
            for key, item in EXAMPLES.items():
                examples.addItem(item["name"], key)
            example_row.addWidget(QLabel("Starting template"))
            example_row.addWidget(examples, 1)
            root.addLayout(example_row)

            panel = QTextEdit()
            panel.setReadOnly(True)
            panel.setMinimumHeight(170)
            root.addWidget(panel, 1)

            notes = QTextEdit()
            notes.setPlaceholderText("Build notes, failed tests, measurements, next steps...")
            notes.setMaximumHeight(110)
            save_notes = QPushButton("Save Notes Locally")
            root.addWidget(notes)
            root.addWidget(save_notes)

            measurement_box = QGroupBox("LED resistor assistant (low-voltage DC)")
            measure_row = QHBoxLayout(measurement_box)
            supply = QDoubleSpinBox()
            supply.setRange(1, 24)
            supply.setValue(5)
            supply.setSuffix(" V")
            forward = QDoubleSpinBox()
            forward.setRange(0.5, 10)
            forward.setValue(2)
            forward.setSuffix(" V")
            current = QDoubleSpinBox()
            current.setRange(0.1, 30)
            current.setDecimals(1)
            current.setValue(10)
            current.setSuffix(" mA")
            estimate = QPushButton("Calculate")
            for title, control in (("Supply", supply), ("LED Vf", forward), ("Target", current)):
                measure_row.addWidget(QLabel(title))
                measure_row.addWidget(control)
            measure_row.addWidget(estimate)
            root.addWidget(measurement_box)

            crumb_row = QHBoxLayout()
            inspect = QPushButton("Inspect CRUMB .cru Save (Read-Only)")
            crumb_row.addWidget(inspect)
            report_label = QLabel("No game save inspected.")
            report_label.setWordWrap(True)
            crumb_row.addWidget(report_label, 1)
            root.addLayout(crumb_row)

            assistant_row = QHBoxLayout()
            assistant_input = QLineEdit()
            assistant_input.setPlaceholderText("Ask Apollo: What should I build first? Check my LED design...")
            assistant_row.addWidget(assistant_input, 1)
            ask_button = QPushButton("Ask Apollo")
            assistant_row.addWidget(ask_button)
            root.addLayout(assistant_row)
            result = QPlainTextEdit()
            result.setReadOnly(True)
            result.setMinimumHeight(115)
            result.setPlaceholderText("Apollo's local Ollama advice appears here. Always verify the real circuit.")
            root.addWidget(result, 1)

            state = {"project_id": None, "inspection": None, "working": False,
                     "inspect_path": None}
            class Signals(QObject):
                answered = Signal(str)
                failed = Signal(str)
            signals = Signals(page)

            def refresh_projects(select_id=None):
                selected = select_id or selector.currentData()
                selector.blockSignals(True)
                try:
                    selector.clear()
                    selector.addItem("Choose a project…", None)
                    for item in self.store.list_projects():
                        selector.addItem(item["name"], item["id"])
                    index = selector.findData(selected)
                    selector.setCurrentIndex(index if index >= 0 else 0)
                finally:
                    selector.blockSignals(False)
                show_project()

            def show_project(_index=None):
                pid = selector.currentData()
                state["project_id"] = pid
                if not pid:
                    panel.setPlainText("Create an electronics project to begin designing.")
                    notes.clear()
                    return
                try:
                    project = self.store.get_project(pid)
                except Exception as exc:
                    panel.setPlainText(f"Could not open project: {exc}")
                    return
                parts = "\n".join(
                    f"• {p['qty']} × {p['name']}: {p.get('notes', '')}"
                    for p in project["components"]
                ) or "(Add parts as you develop your design)"
                steps = "\n".join(
                    f"{i}. {step}" for i, step in enumerate(project["steps"], 1)
                ) or "(Use Ask Apollo for a proposed step-by-step circuit plan)"
                panel.setPlainText(
                    f"{project['name']}\n{project['description']}\n\nPARTS\n"
                    f"{parts}\n\nBUILD PLAN\n{steps}\n\n{project['notice']}"
                )
                notes.setPlainText(project["notes"])

            def create_project():
                from PySide6.QtWidgets import QInputDialog
                proposed, ok = QInputDialog.getText(page, "Create Circuit Project", "Project name:")
                if not ok:
                    return
                try:
                    item = self.store.create_project(proposed, template=examples.currentData())
                    refresh_projects(item["id"])
                except (ValueError, OSError) as exc:
                    QMessageBox.warning(page, "Circuit Lab", str(exc))

            def save_notes_to_project():
                if not state["project_id"]:
                    QMessageBox.information(page, "Circuit Lab", "Create or select a project first.")
                    return
                try:
                    self.store.set_notes(state["project_id"], notes.toPlainText())
                    result.setPlainText("Project notes saved locally in Apollo's private storage.")
                except Exception as exc:
                    QMessageBox.warning(page, "Circuit Lab", str(exc))

            def calculate():
                try:
                    answer = resistor_for_led(supply.value(), forward.value(), current.value())
                    result.setPlainText(json.dumps(answer, indent=2))
                except ValueError as exc:
                    result.setPlainText(str(exc))

            def inspect_file():
                file_name, _ = QFileDialog.getOpenFileName(
                    page, "Inspect a local CRUMB save", "", "CRUMB project (*.cru)"
                )
                if not file_name:
                    return
                try:
                    summary = inspect_crumb_save(file_name)
                    state["inspection"] = summary
                    state["inspect_path"] = file_name
                    report_label.setText(
                        f"Read only: {summary['file_name']}; "
                        f"{summary['xml_element_count']} XML nodes. "
                        "No circuit simulation or electrical validation."
                    )
                    result.setPlainText(json.dumps(summary, indent=2))
                except (ValueError, OSError) as exc:
                    QMessageBox.warning(page, "CRUMB inspection", str(exc))

            def ask_apollo():
                question = assistant_input.text().strip()
                if state["working"] or not question:
                    return
                if len(question) > 2000:
                    QMessageBox.warning(page, "Circuit Lab", "Keep the question under 2,000 characters.")
                    return
                parent_window = context.get("apollo_window")
                client = getattr(parent_window, "client", None)
                if client is None:
                    result.setPlainText("Open Circuit Lab through the main Apollo desktop window for Ollama assistance.")
                    return
                project = None
                if state["project_id"]:
                    try:
                        project = self.store.get_project(state["project_id"])
                    except (ValueError, OSError, KeyError):
                        pass
                # Files may contain untrusted text. Only numeric metadata and
                # hash are passed to the model, never raw CRUMB project XML.
                inspected = state["inspection"]
                metadata = {
                    "sha256": inspected["sha256"],
                    "xml_element_count": inspected["xml_element_count"],
                    "electrical_wiring_verified": False
                } if inspected else None
                description = json.dumps({
                    "name": project["name"] if project else "",
                    "description": project["description"] if project else "",
                    "template_components": project["components"][:30] if project else [],
                    "template_steps": project["steps"][:25] if project else [],
                    "user_notes": notes.toPlainText()[:3000],
                    "crumb_read_only_metadata": metadata,
                }, ensure_ascii=False)
                prompt = [
                    {
                        "role": "system",
                        "content": (
                            "You are Apollo Circuit Lab, a practical electronics design tutor. "
                            "Suggest a safe, step-by-step low-voltage breadboard circuit, "
                            "a component list, wiring checklist and specific measurements. "
                            "Never assert you can control or read live CRUMB, or that "
                            "structural XML analysis verifies circuit wiring. "
                            "Always distinguish design suggestions from simulator results. "
                            "Avoid mains, unprotected lithium cells, medical, automotive "
                            "safety or high-current hardware. For such tasks give "
                            "high-level risks and request specialist verification."
                        ),
                    },
                    {"role": "user", "content": "Current local design notes:\n" + description +
                     "\n\nQuestion:\n" + question},
                ]
                state["working"] = True
                ask_button.setEnabled(False)
                result.setPlainText("Apollo is analysing the circuit plan with your selected local model...")
                def work():
                    try:
                        payload = client.chat_once(prompt)
                        message = str((payload.get("message") or {}).get("content") or "").strip()
                        signals.answered.emit(message or "No explanation returned by the local model.")
                    except Exception as exc:
                        signals.failed.emit(f"{type(exc).__name__}: {exc}")
                threading.Thread(target=work, daemon=True, name="ApolloCircuitLab").start()

            def finish(text):
                state["working"] = False
                ask_button.setEnabled(True)
                result.setPlainText(text)

            def open_popout():
                window = build_page(popout=True)
                window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
                screen = QGuiApplication.primaryScreen()
                if screen:
                    rectangle = screen.availableGeometry()
                    half = max(480, rectangle.width() // 2)
                    window.setGeometry(rectangle.x(), rectangle.y(), half, rectangle.height())
                window.show()
                window.raise_()
                self._windows.append(window)
                window.destroyed.connect(
                    lambda: self._windows.remove(window) if window in self._windows else None
                )
            refresh.clicked.connect(lambda: refresh_projects())
            create.clicked.connect(create_project)
            selector.currentIndexChanged.connect(show_project)
            save_notes.clicked.connect(save_notes_to_project)
            estimate.clicked.connect(calculate)
            inspect.clicked.connect(inspect_file)
            ask_button.clicked.connect(ask_apollo)
            assistant_input.returnPressed.connect(ask_apollo)
            signals.answered.connect(finish)
            signals.failed.connect(lambda error: finish("Apollo couldn't generate advice: " + error))
            refresh_projects()
            return page

        return build_page()
