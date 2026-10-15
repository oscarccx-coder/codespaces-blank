# Apollo Vehicle Diagnostics (OBD-II reader)

Apollo's **Vehicle Diagnostics** app provides a **read-only** standard OBD-II
diagnostics layer for ELM327-compatible serial adapters.

## Hardware and first scan

- Use a USB ELM327 reader, or a Bluetooth ELM327 adapter that exposes a Windows serial COM port (Bluetooth Serial Port Profile / SPP). This version does **not** support Wi-Fi-only ELM327 or BLE-only adapters.
- Park the vehicle safely, switch ignition on, and connect the adapter to the OBD-II port. Do not interact with diagnostics while driving.
- On Windows, pair the adapter if Bluetooth, then check **Device Manager → Ports (COM & LPT)** to identify its COM port.
- In Apollo select **Apps → Vehicle Diagnostics** (or pin it to the configurable sidebar). Select **Find Adapters**, choose the correct COM port and baud.
- Default is **38400 baud**; try **9600, 57600 or 115200** if your adapter documents a different speed.
- Select **Read Live Sensors** or **Scan Fault Codes** (stored, pending and permanent).
- **Demo Mode** works without any adapter; simulated values are visibly labeled and never silently replace failed real scans.
- **Auto-refresh every 12 seconds** is off by default and skips overlapping scans. **Save Report** only writes data when you explicitly choose a local filename.

Apollo uses its existing pyserial>=3.5 dependency, not another heavy diagnostics library.

## Supported initial live data

| OBD service 01 PID | Reading | Unit |
| --- | --- | --- |
| 0C | Engine speed | rpm |
| 0D | Vehicle speed | km/h |
| 05 | Engine coolant temperature | °C |
| 0F | Intake air temperature | °C |
| 11 | Throttle position | % |
| 04 | Calculated engine load | % |
| 0B | Intake manifold pressure | kPa |
| 42 | Control-module voltage | V |

Fault-code queries use service **03** (stored), **07** (pending) and **0A** (permanent). Apollo never claims that an unavailable mode means "no faults" and does not guess manufacturer-specific fault descriptions.

## Safety boundaries

The ELM327 transport has a hardcoded read-only command allowlist: device initialisation only, service 01 readings and 03/07/0A code retrieval. It has NO raw-command API, service 04 clear, ECU writing, programming, actuator control, firmware flashing, VIN collection or wireless upload.

Only serial port names actually detected by the OS may be opened. Serial operation timeouts and response size are bounded. Session handles close after each scan, and hardware exceptions are **never** substituted with demo data. Apollo keeps diagnostic results in memory unless the user explicitly selects **Save Report**.

**This is not a certified mechanic's scanner.** Standard emissions OBD-II does not guarantee access to every vehicle module (airbags, ABS, body modules and proprietary codes are generally outside scope). A code identifies a problem area, not a proven failed component.

## Implementation

- Core driver/parser: apollo_obd.py
- Apollo app: modules/vehicle_diagnostics/
- Hardware-free safety regression suite: test_obd_reader.py
- Test command: python -m unittest -v test_obd_reader
- CI: module validator, syntax checks and regression suite

A real ELM327 adapter and car were not available in GitHub Actions. Perform a Windows USB/Bluetooth smoke test before treating physical hardware operation as verified.

## Starting-system test: Fiesta or generic OBD-II

The **Vehicle Diagnostics** screen now offers a **Ford Fiesta (2008)** preset and
**Other OBD-II vehicle**. The name is a report label only: it does not perform
Ford-specific ECU operations or assume access to proprietary modules.

1. With the car safely parked and engine off, plug in the ELM327 serial adapter.
2. Select its COM port, then choose 15, 30 or 60 seconds.
3. Select **Start Starting-System Test**. Apollo records sample timestamps,
   adapter voltage (ELM327 read-only `ATRV`), ECU voltage (service 01 PID
   `42`), engine speed (PID `0C`), and an occasional vehicle-speed PID `0D`.
4. While recording, click **Mark Key Turn** immediately before a start attempt.
   The key event is manually timed and approximate. Keep the engine off for
   several initial seconds if you want to record a baseline.
5. Use **Stop & Analyse** to finish early, or allow the chosen time to expire.
   Apollo shows the lowest measured voltage, available baseline and RPM,
   communication gaps and possibilities that justify further inspection.
6. Every successfully completed test is automatically saved as JSON under
   `storage/reports/vehicle_diagnostics/starting_tests/`, with a timestamp and
   vehicle-profile label. **Load Latest Test** reopens the last report. Saved
   history is available in Apollo chat through `obd_starting_history`, and
   the full latest report through `obd_latest_starting_test`.

**Read-only safety:** No OBD command starts the engine, engages the starter,
controls the throttle or changes ECU programming. If the vehicle speed PID
reports movement, recording stops. The captured data stays on this PC unless
the owner intentionally exports it. The local `storage/` directory is
gitignored so new vehicle reports are not shared by source updates.

**Measurement limits:** ECU voltage PID 42 may not be supported by every
vehicle. ELM327 `ATRV` gives an approximate adapter-side supply voltage,
not a precision reading at the battery posts. ELM327 serial polling is not
a high-speed oscilloscope: it can miss millisecond-scale voltage dips, and
the ECU or adapter may stop responding during a crank attempt. The report
records unavailable values as missing, never zero and never mock data.
Even a measured fall below 9.6 V does **not** prove that the starter is
drawing excessive current: a degraded battery, cable resistance, bad earth
or other load can cause similar symptoms. For a definitive battery and
starter test, use a suitable meter/battery tester and, where needed,
a mechanic's high-current clamp. Keep cranking attempts brief, with cooling
time between attempts, according to the vehicle handbook.

Unit tests: `cd apollo_ui && python -m unittest -v tests.test_obd_reader`.
Tests cover synthetic voltage collapse, absent data, blocked ECU writes,
adapter parsing, recording and history persistence. Physical Windows
ELM327 validation still requires real vehicle hardware.

Future improvements could include graphs, faster externally sampled
battery-terminal voltage with timestamp synchronisation, and maker-specific
read-only diagnostics. ECU-write functionality remains out of scope.
