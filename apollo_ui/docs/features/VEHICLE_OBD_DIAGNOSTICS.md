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

Future improvements could include time-series graphs and maker-specific code interpretation. Write features would require new, explicitly approved design work.
