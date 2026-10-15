# Vehicle starting-system recorder (15 October 2026)

- Added a Ford Fiesta (2008) and generic OBD-II starting-system test profile.
- Added a timed Start Test, manual Mark Key Turn, Stop & Analyse, live voltage/RPM status and stored local reports.
- Records ELM327 adapter voltage, ECU voltage, RPM, occasional vehicle-speed checks and communications dropouts.
- Reports low-voltage observations without diagnosing the starter motor as proven faulty or inventing missing readings.
- Added Apollo tools to access previous tests and the latest report for reasoning across sessions.
- Retains read-only hard-coded OBD commands and no automatic vehicle actuation.
- Expanded hardware-free tests; real vehicle/Windows ELM327 smoke test still required.
