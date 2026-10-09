# Apollo Circuit Lab: CRUMB Companion (first stage)

Apollo Circuit Lab is a simulator-neutral electronics assistant under **Settings → Apps → Everyday**. On Windows it can open a **detached, resizable companion** along the left half of the primary monitor, so users can snap [CRUMB Circuit Simulator](https://store.steampowered.com/app/2198800/CRUMB_Circuit_Simulator/) to the right half. A button asks the OS to open the optional Steam game through its registered steam URI. Apollo neither controls Steam nor opens the game without a user click.

## Available now

- Local private electronics project notebooks, step-by-step low-voltage build plans, component lists and editable notes. First templates: single 5 V LED + resistor, and a **555 timer planning outline**.
- **LED resistor calculator** (1–24 V DC only): supply, estimated LED forward voltage, target mA, next-higher E12 resistor, estimated current and dissipation. Check the actual component datasheet and resistor rating.
- **Inspect CRUMB .cru Save (Read-Only)**: chooses one local game-save file in the UI and displays XML root, capped element/tag counts and SHA-256 fingerprint. Never edits a .cru file, prints embedded firmware or claims to know the electrical wiring. Parsing rejects XML declarations with DTDs/entities and enforces an 8 MiB upper bound.
- **Ask Apollo**: uses the user's existing selected local Ollama model in a background thread to review a project and suggest wiring, calculations, parts and verification measurements. For the .cru file it only receives bounded numeric metadata and a SHA-256 digest, not raw game-save XML, firmware or an arbitrary path.
- The agent tool bus exposes only a bounded LED calculator and a list of templates, **not project/file editing, game automation or electrical control**.

### CRUMB limitations

CRUMB's save files may vary between versions. Apollo's first-stage parser intentionally makes **no promise** of electrical net analysis. The third-party open-source project [Circuitarium MCP](https://github.com/Craftiee/circuitarium-mcp) offers *experimental* read-only analysis for CRUMB **Unity-era 1.3.5** `.cru` files (structural validation, bill of materials, selected net inference). That tool cannot drive a live CRUMB simulation or write arbitrary CRUMB projects, and its authors explicitly do not claim compatibility with CRUMB's newer Godot 2.x versions. It would make a sensible **optional future adapter** after checking the version installed on your PC and testing safe representative saves.

For now, build and test the circuit **in CRUMB**, save your project, click Inspect in Circuit Lab, and copy readings/failures into the electronics notebook. Apollo's AI can then help plan the next test. It does not silently change the game.

## Running side-by-side

1. Launch Apollo on your Windows PC.
2. Open **Settings → Apps → Everyday → Circuit Lab**.
3. Select **Split-screen Companion** to open a detached Apollo electronics panel on the left side of the monitor.
4. Select **Launch CRUMB in Steam** (or open Steam manually). Snap CRUMB to the right side using **Win + Right**. Steam/CRUMB needs to be installed separately.
5. Create a new design, select a template, ask Apollo for a suggested schematic/wiring checklist, then assemble and simulate in CRUMB.
6. In CRUMB, **save** your design. Select the `.cru` file from Apollo for structural review and record observed simulator values in your project notes.

## Raspberry Pi distinction

Apollo's Pi 5 ARM64 edition is currently headless. Circuit Lab's calculations and project data are pure Python, but the split-screen UI needs **PySide6 desktop Apollo on Windows/Linux**. CRUMB's Steam version lists **Windows** support, not a Raspberry Pi build. The Pi can be an electronics planning server later; it will not automatically run this game or provide its proprietary GUI.

## Safety

Virtual simulation and AI text are not proof that a physical prototype is safe. Never follow speculative pinouts or apply generated wiring directly to mains power, high-power batteries or chargers, medical equipment, prosthetic control, automotive safety systems or devices that can move unexpectedly. Use protected low-voltage power, datasheets, proper fusing and physical measurement before powering a real prototype.

## Source

- `apollo_circuit_lab.py`: project storage, resistor calculator and bounded XML read-only parser.
- `modules/circuit_lab/`: Apollo GUI, split-screen companion and Ollama prompt integration.
- `test_circuit_lab.py`: math, file-format/security, project recovery and UI tool-contract regression suite.

Windows graphics/game integration still requires a real workstation smoke test; no native Steam API or live simulator control is claimed.
