"""Apollo Vehicle Diagnostics: ELM327 serial/Bluetooth OBD-II reader UI."""
import json
from pathlib import Path

from apollo_obd import OBDService, BAUD_RATES, demo_snapshot, demo_fault_codes

# Reference labels, not diagnoses; vehicles may require make-specific testing.
COMMON_DTC_HINTS = {
    "P0101": "Mass-airflow signal outside expected range",
    "P0128": "Coolant temperature below thermostat regulating range",
    "P0133": "Oxygen sensor response appears slow",
    "P0171": "Fuel mixture reported too lean (bank 1)",
    "P0300": "Random or multiple-cylinder misfire detected",
    "P0420": "Catalytic converter efficiency below threshold (bank 1)",
    "P0442": "Small evaporative-emissions system leak detected",
}


class Module:
    def __init__(self, context=None):
        self.context = context or {}
        self.base = Path(self.context.get("base_dir") or ".").resolve()
        self.service = OBDService()

    def tools(self):
        return [
            {
                "name": "obd_list_ports",
                "description": "List USB/Bluetooth serial ports to select an ELM327-compatible OBD-II adapter.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "obd_live_snapshot",
                "description": "Read supported OBD-II live engine sensors from a selected adapter. Read-only. Use only while parked.",
                "parameters": {"type": "object", "properties": {
                    "port": {"type": "string"}, "baud": {"type": "integer"},
                }, "required": ["port"]},
            },
            {
                "name": "obd_fault_codes",
                "description": "Read stored, pending and permanent diagnostic trouble codes; does not clear codes.",
                "parameters": {"type": "object", "properties": {
                    "port": {"type": "string"}, "baud": {"type": "integer"},
                }, "required": ["port"]},
            },
            {
                "name": "obd_demo",
                "description": "Return explicitly simulated live data and trouble codes; no car is accessed.",
                "parameters": {"type": "object", "properties": {}},
            },
        ]

    def run(self, action, arguments):
        args = arguments or {}
        if action == "obd_list_ports":
            return {"ports": self.service.list_ports()}
        if action == "obd_live_snapshot":
            return self.service.snapshot(args.get("port"), args.get("baud", 38400))
        if action == "obd_fault_codes":
            return self.service.read_codes(args.get("port"), args.get("baud", 38400))
        if action == "obd_demo":
            return {"snapshot": demo_snapshot(), "fault_codes": demo_fault_codes()}
        raise KeyError(action)

    def self_test(self):
        names = {item["name"] for item in self.tools()}
        assert names == {"obd_list_ports", "obd_live_snapshot", "obd_fault_codes", "obd_demo"}
        assert demo_snapshot()["simulated"] and demo_fault_codes()["simulated"]
        return "Read-only OBD-II module and explicit demo mode ready."

    def build_ui(self, parent=None, ui_context=None):
        import threading
        from PySide6.QtCore import QObject, Qt, QTimer, Signal
        from PySide6.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
            QCheckBox, QComboBox, QPlainTextEdit, QTableWidget,
            QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
        )

        page = QWidget(parent)
        root = QVBoxLayout(page)
        root.setSpacing(10)

        heading = QLabel("Apollo Vehicle Diagnostics")
        heading.setStyleSheet("font-size:24px;font-weight:800")
        root.addWidget(heading)
        sub = QLabel(
            "USB / Bluetooth COM-port ELM327-compatible OBD-II scanners. "
            "Park the vehicle and turn the ignition on. Read-only: no ECU programming, "
            "actuator control or fault-code clearing. Some cars do not support every PID."
        )
        sub.setWordWrap(True)
        root.addWidget(sub)

        connection = QHBoxLayout()
        connection.addWidget(QLabel("Adapter"))
        port_combo = QComboBox()
        port_combo.setMinimumWidth(200)
        connection.addWidget(port_combo, 1)
        connection.addWidget(QLabel("Baud"))
        baud_combo = QComboBox()
        for value in BAUD_RATES:
            baud_combo.addItem(str(value), value)
        baud_combo.setCurrentIndex(baud_combo.findData(38400))
        connection.addWidget(baud_combo)
        refresh_btn = QPushButton("Find Adapters")
        connection.addWidget(refresh_btn)
        root.addLayout(connection)

        controls = QHBoxLayout()
        live_btn = QPushButton("Read Live Sensors")
        codes_btn = QPushButton("Scan Fault Codes")
        demo_btn = QPushButton("Demo Mode")
        save_btn = QPushButton("Save Report")
        auto_refresh = QCheckBox("Auto-refresh every 12 seconds")
        for button in (live_btn, codes_btn, demo_btn, save_btn):
            controls.addWidget(button)
        root.addLayout(controls)
        root.addWidget(auto_refresh)

        connection_status = QLabel("No adapter selected.")
        connection_status.setWordWrap(True)
        root.addWidget(connection_status)

        readings = QTableWidget(0, 3)
        readings.setHorizontalHeaderLabels(["Parameter / Code", "Reading", "Notes"])
        readings.horizontalHeader().setStretchLastSection(True)
        readings.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        readings.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        readings.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        readings.setMinimumHeight(210)
        root.addWidget(readings, 1)

        details = QPlainTextEdit()
        details.setReadOnly(True)
        details.setMinimumHeight(140)
        details.setPlaceholderText("Live sensor values and diagnostic scan results appear here.")
        root.addWidget(details, 1)

        class Signals(QObject):
            done = Signal(str, object)
            failed = Signal(str, str)

        signals = Signals(page)
        state = {"busy": False, "result": None, "destroyed": False}
        timer = QTimer(page)
        timer.setInterval(12000)

        def add_row(parameter, reading, notes):
            row = readings.rowCount()
            readings.insertRow(row)
            for column, value in enumerate((parameter, reading, notes)):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                readings.setItem(row, column, item)

        def show_data(result):
            state["result"] = result
            readings.setRowCount(0)
            details.setPlainText(json.dumps(result, indent=2, default=str))
            if result.get("simulated"):
                connection_status.setText("SIMULATED DEMO DATA - nothing read from a car.")
            else:
                connection_status.setText(
                    f"Vehicle scan: {result.get('observed_at', '')} • "
                    f"Adapter: {result.get('port', 'unknown')}. Read-only."
                )
            if "sensors" in result:
                for value in result["sensors"].values():
                    add_row(value["name"], f"{value['value']} {value['unit']}", f"PID {value['pid']}")
                for pid in result.get("unsupported_pids", []):
                    add_row(f"PID {pid[2:]}", "Unavailable", result.get("problems", {}).get(pid, "Not supported"))
                if not result["sensors"]:
                    add_row("Engine data", "Not available", "Check ignition, adapter and vehicle compatibility")
            if "codes" in result:
                for category, codes in result["codes"].items():
                    for code in codes:
                        add_row(code, category.upper(), COMMON_DTC_HINTS.get(code, "Look up vehicle-specific diagnostic guidance"))
                    if not codes:
                        issue = result.get("unavailable", {}).get(category)
                        add_row(category.title() + " codes", "Unavailable" if issue else "None returned",
                                issue or "No codes reported by adapter")
            if result.get("message"):
                connection_status.setText(connection_status.text() + "\n" + str(result["message"]))

        def refresh_ports():
            if state["busy"]:
                return
            selected = port_combo.currentData()
            port_combo.clear()
            try:
                ports = self.service.list_ports()
                for item in ports:
                    port_combo.addItem(
                        f"{item['port']}  •  {item['description']}", item["port"]
                    )
                if selected:
                    match = port_combo.findData(selected)
                    if match >= 0:
                        port_combo.setCurrentIndex(match)
                if not ports:
                    connection_status.setText(
                        "No serial adapter found. Connect or pair an ELM327 USB/Bluetooth SPP adapter, "
                        "then select Find Adapters. Wi-Fi adapters are not supported in this version."
                    )
                live_btn.setEnabled(bool(ports))
                codes_btn.setEnabled(bool(ports))
            except Exception as exc:
                connection_status.setText(f"Serial port discovery failed: {exc}")
                live_btn.setEnabled(False)
                codes_btn.setEnabled(False)

        def busy(value):
            state["busy"] = bool(value)
            for control in (refresh_btn, live_btn, codes_btn, demo_btn, port_combo, baud_combo):
                control.setEnabled(not value)
            save_btn.setEnabled(not value and state["result"] is not None)

        def launch(mode):
            if state["busy"]:
                return
            if mode != "demo" and not port_combo.currentData():
                connection_status.setText("Select an available ELM327 adapter first.")
                return
            port, baud = port_combo.currentData(), baud_combo.currentData()
            busy(True)
            connection_status.setText(
                "SIMULATED demo data..." if mode == "demo" else "Communicating with OBD-II adapter..."
            )

            def work():
                try:
                    if mode == "demo":
                        result = {"snapshot": demo_snapshot(), "fault_codes": demo_fault_codes()}
                    elif mode == "live":
                        result = self.service.snapshot(port, baud)
                    else:
                        result = self.service.read_codes(port, baud)
                    signals.done.emit(mode, result)
                except Exception as exc:
                    signals.failed.emit(mode, f"{type(exc).__name__}: {exc}")

            threading.Thread(target=work, name="ApolloOBDRead", daemon=True).start()

        def done(mode, result):
            if state["destroyed"]:
                return
            busy(False)
            if mode == "demo":
                demo = dict(result["snapshot"])
                # Explicitly show both kinds of fictional data without a car connection.
                demo["codes"] = result["fault_codes"]["codes"]
                show_data(demo)
            else:
                show_data(result)
            refresh_ports()

        def failed(mode, error):
            if state["destroyed"]:
                return
            busy(False)
            connection_status.setText(f"{mode.title()} scan FAILED: {error}\nNo simulated data substituted.")
            details.setPlainText(json.dumps({"ok": False, "error": error}, indent=2))
            refresh_ports()

        def save_report():
            data = state["result"]
            if data is None:
                return
            folder = self.base / "storage" / "reports" / "vehicle_diagnostics"
            folder.mkdir(parents=True, exist_ok=True)
            target, _ = QFileDialog.getSaveFileName(
                page, "Save local vehicle diagnostic report",
                str(folder / "apollo-obd-report.json"), "JSON reports (*.json)"
            )
            if not target:
                return
            try:
                Path(target).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
                connection_status.setText(f"Saved local report to {target}. Keep vehicle data private.")
            except OSError as exc:
                QMessageBox.warning(page, "Save report", str(exc))

        def auto_refresh_changed(checked):
            if checked:
                timer.start()
            else:
                timer.stop()

        signals.done.connect(done)
        signals.failed.connect(failed)
        refresh_btn.clicked.connect(refresh_ports)
        live_btn.clicked.connect(lambda: launch("live"))
        codes_btn.clicked.connect(lambda: launch("codes"))
        demo_btn.clicked.connect(lambda: launch("demo"))
        save_btn.clicked.connect(save_report)
        auto_refresh.toggled.connect(auto_refresh_changed)
        timer.timeout.connect(lambda: launch("live") if not state["busy"] and port_combo.currentData() else None)
        page.destroyed.connect(lambda: state.update({"destroyed": True}))
        save_btn.setEnabled(False)
        refresh_ports()
        return page
