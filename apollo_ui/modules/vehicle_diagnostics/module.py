"""Apollo Vehicle Diagnostics: ELM327 serial/Bluetooth OBD-II reader UI."""
import json
from pathlib import Path

from apollo_obd import OBDService, BAUD_RATES, demo_snapshot, demo_fault_codes
from apollo_vehicle_starting_test import (
    StartTestControl, capture_starting_test, save_starting_test,
    starting_test_history, latest_starting_test,
)

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
                "name": "obd_starting_history",
                "description": "Review saved local starting-system test summaries; no car commands are sent.",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "name": "obd_latest_starting_test",
                "description": "Read the latest saved local starting-system sensor timeline and cautious analysis.",
                "parameters": {"type": "object", "properties": {}},
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
        if action == "obd_starting_history":
            return {"tests": starting_test_history(self.base)}
        if action == "obd_latest_starting_test":
            return latest_starting_test(self.base)
        if action == "obd_demo":
            return {"snapshot": demo_snapshot(), "fault_codes": demo_fault_codes()}
        raise KeyError(action)

    def self_test(self):
        names = {item["name"] for item in self.tools()}
        assert names == {"obd_list_ports", "obd_live_snapshot", "obd_fault_codes", "obd_demo",
                         "obd_starting_history", "obd_latest_starting_test"}
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

        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("Vehicle profile"))
        profile_combo = QComboBox()
        profile_combo.addItems(["Ford Fiesta (2008)", "Other OBD-II vehicle"])
        profile_row.addWidget(profile_combo, 1)
        root.addLayout(profile_row)

        starting_row = QHBoxLayout()
        start_btn = QPushButton("Start Starting-System Test")
        test_length = QComboBox()
        for seconds in (15, 30, 60):
            test_length.addItem(f"{seconds} seconds", seconds)
        test_length.setCurrentIndex(test_length.findData(30))
        key_btn = QPushButton("Mark Key Turn")
        stop_btn = QPushButton("Stop & Analyse")
        latest_btn = QPushButton("Load Latest Test")
        key_btn.setEnabled(False)
        stop_btn.setEnabled(False)
        for widget in (start_btn, test_length, key_btn, stop_btn, latest_btn):
            starting_row.addWidget(widget)
        root.addLayout(starting_row)
        start_hint = QLabel(
            "Timed read-only test: record baseline with ignition on, then mark the key "
            "turn immediately before attempting to start. Keep the vehicle parked. "
            "Do not repeatedly crank a failing starter or leave the ignition on indefinitely."
        )
        start_hint.setWordWrap(True)
        root.addWidget(start_hint)
        live_readout = QLabel("Starting-system recorder idle.")
        live_readout.setWordWrap(True)
        root.addWidget(live_readout)

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
            sample = Signal(object)

        signals = Signals(page)
        state = {"busy": False, "result": None, "destroyed": False,
                 "start_control": None, "sample_count": 0}
        timer = QTimer(page)
        timer.setInterval(12000)
        elapsed_timer = QTimer(page)
        elapsed_timer.setInterval(250)

        def tick_starting_test():
            control = state["start_control"]
            if control is not None:
                import time
                elapsed = time.monotonic() - control.started_at
                current = live_readout.text().split(" | ", 1)[-1]
                live_readout.setText(
                    f"Recording {elapsed:.1f}s, {state['sample_count']} readings | {current}"
                )

        elapsed_timer.timeout.connect(tick_starting_test)

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
            if result.get("type") == "starting_system_test":
                analysis = result["analysis"]
                connection_status.setText(
                    "Starting test complete. " + (
                        f"Report saved: {result['saved_to']}" if result.get("saved_to")
                        else "Report could not be saved: " + result.get("save_error", "unknown error")
                    )
                )
                add_row("Lowest sampled voltage", analysis["minimum_sampled_voltage_v"],
                        analysis["voltage_source"] + "; V")
                add_row("Pre-test voltage", analysis["baseline_sampled_voltage_v"], "V")
                add_row("Max sampled RPM", analysis["max_sampled_rpm"], "rpm")
                add_row("Samples", analysis["samples"], "Communication gaps are preserved")
                add_row("Finding", analysis["status"], analysis["summary"])
                for warning in analysis["cautions"]:
                    add_row("Caution", "", warning)
                return
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
                start_btn.setEnabled(bool(ports))
            except Exception as exc:
                connection_status.setText(f"Serial port discovery failed: {exc}")
                live_btn.setEnabled(False)
                codes_btn.setEnabled(False)
                start_btn.setEnabled(False)

        def busy(value):
            state["busy"] = bool(value)
            for control in (refresh_btn, live_btn, codes_btn, demo_btn, port_combo, baud_combo,
                            start_btn, test_length, profile_combo, latest_btn, auto_refresh):
                control.setEnabled(not value)
            save_btn.setEnabled(not value and state["result"] is not None)
            key_btn.setEnabled(value and state["start_control"] is not None)
            stop_btn.setEnabled(value and state["start_control"] is not None)

        def on_sample(sample):
            if state["destroyed"]:
                return
            state["sample_count"] += 1
            voltage = (sample["adapter_voltage_v"] if sample["adapter_voltage_v"] is not None
                       else sample["ecu_voltage_v"])
            live_readout.setText(
                f"Recording | Voltage: {str(voltage) + ' V' if voltage is not None else 'unavailable'}; "
                f"ECU RPM: {sample['engine_rpm'] if sample['engine_rpm'] is not None else 'unavailable'}; "
                f"Communication warnings: {len(sample['errors'])}"
            )
            if state["sample_count"] == 1:
                readings.setRowCount(0)
            add_row(f"+{sample['elapsed_s']:.2f}s",
                    str(voltage) + " V" if voltage is not None else "No voltage",
                    f"RPM: {sample['engine_rpm']}; errors: {len(sample['errors'])}")
            readings.scrollToBottom()

        def begin_starting_test():
            if state["busy"] or not port_combo.currentData():
                return
            auto_refresh.setChecked(False)
            control = StartTestControl()
            state["start_control"] = control
            state["sample_count"] = 0
            state["result"] = None
            port, baud, duration = (
                port_combo.currentData(), baud_combo.currentData(), test_length.currentData()
            )
            selected_profile = profile_combo.currentText()
            busy(True)
            connection_status.setText("Starting read-only test; preparing adapter...")
            live_readout.setText("Recording | Waiting for first voltage reading...")
            elapsed_timer.start()

            def work():
                try:
                    report = capture_starting_test(
                        port, baud, duration, service=self.service, control=control,
                        on_sample=lambda value: signals.sample.emit(value),
                        vehicle_profile=selected_profile,
                    )
                    try:
                        report["saved_to"] = str(save_starting_test(report, self.base))
                    except OSError as exc:
                        report["save_error"] = str(exc)
                    signals.done.emit("start_test", report)
                except Exception as exc:
                    signals.failed.emit("start_test", f"{type(exc).__name__}: {exc}")

            threading.Thread(target=work, name="ApolloOBDStartingTest", daemon=True).start()

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
            elapsed_timer.stop()
            state["start_control"] = None
            busy(False)
            if mode == "start_test":
                show_data(result)
                refresh_ports()
                return
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
            elapsed_timer.stop()
            state["start_control"] = None
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
        signals.sample.connect(on_sample)

        def load_latest():
            if state["busy"]:
                return
            result = latest_starting_test(self.base)
            if result.get("available"):
                show_data(result["report"])
                connection_status.setText("Loaded saved starting-system report. No live vehicle access.")
                live_readout.setText("Loaded saved test. No live vehicle access.")
            else:
                connection_status.setText(result["message"])

        latest_btn.clicked.connect(load_latest)
        start_btn.clicked.connect(begin_starting_test)
        key_btn.clicked.connect(
            lambda: state["start_control"].mark_key_turn()
            if state["start_control"] is not None else None
        )
        stop_btn.clicked.connect(
            lambda: state["start_control"].stop()
            if state["start_control"] is not None else None
        )
        refresh_btn.clicked.connect(refresh_ports)
        live_btn.clicked.connect(lambda: launch("live"))
        codes_btn.clicked.connect(lambda: launch("codes"))
        demo_btn.clicked.connect(lambda: launch("demo"))
        save_btn.clicked.connect(save_report)
        auto_refresh.toggled.connect(auto_refresh_changed)
        timer.timeout.connect(lambda: launch("live") if not state["busy"] and port_combo.currentData() else None)
        def close_page():
            state["destroyed"] = True
            if state["start_control"] is not None:
                state["start_control"].stop()

        page.destroyed.connect(close_page)
        save_btn.setEnabled(False)
        refresh_ports()
        return page
