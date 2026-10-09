# Installing Apollo on a new device

## Windows desktop (supported)

1. Download/clone the **apollo_ui** folder into a writable directory with enough disk space. Avoid Windows protected folders such as Program Files if you plan to run from source.
2. Install a healthy Python 3.11+ interpreter (3.13 preferred). The Windows `py` launcher is recommended, but not required.
3. Double-click `INSTALL_REQUIREMENTS.bat` in `apollo_ui`. Apollo creates `.venv` beside the script, installs only its core requirements there, runs `pip check`, then import-tests the desktop packages.
4. Install/configure Ollama and a compatible local LLM, then double-click `start_apollo_ui.bat`. LLM download and Ollama installation are **separate**, not yet automated by the core installer.
5. For optional XTTS, install with `INSTALL_REQUIREMENTS.bat --voice` from a Command Prompt, or run `install_xtts_v2.bat` once the core .venv is installed. This is a large Windows/CUDA stack; it might install user-scope FFmpeg Shared via WinGet and optionally download missing XTTS model data. It is not suitable for every device.
6. Use the in-app signed Update Centre for verified packaged releases or `UPDATE_APOLLO_CODE.bat` for code-only updates in a clean Git checkout.

## Repairing requirements

Run `INSTALL_REQUIREMENTS.bat` again. This updates the same isolated environment; it does not delete Apollo's user files or models. If the isolated environment is irreparably damaged, close Apollo, run `UNINSTALL_REQUIREMENTS.bat`, then `INSTALL_REQUIREMENTS.bat`. The uninstaller asks for confirmation.

**Legacy installations:** Apollo's older scripts sometimes installed Python packages directly into a system-wide interpreter. The new uninstall script intentionally does not remove them. Manually audit legacy Python environments before removing any package used by other applications.

## What remains after uninstalling requirements

The only deleted tree is `apollo_ui/.venv`, and only after you confirm. These persist:
- Apollo application source, desktop settings, module configuration and `storage/` data
- Chat history, learned knowledge, local memory and coding projects
- Voice profiles, recordings and cached XTTS model weights
- System Python, Ollama, Git, WinGet and any shared FFmpeg installation

The optional XTTS installer also installs all Python modules inside Apollo's private environment. Running the uninstaller therefore removes both core and optional voice Python packages from that venv, but not the separate shared FFmpeg package or downloaded XTTS model.

## Raspberry Pi 5, ARM64 Linux

From the `apollo_ui` directory:
```bash
bash pi/install_pi.sh
.venv-pi/bin/python apollo_pi.py --port 8766
```
This is a **headless** API, not the Windows PySide6 desktop window. It requires a suitable locally installed model/Ollama runtime. The Pi installer uses `.venv-pi` and is not affected by either Windows .bat file. Optional user-level service: `bash pi/install_pi.sh --service`.

## Supported launchers

End-user entrypoints: `INSTALL_REQUIREMENTS.bat`, `UNINSTALL_REQUIREMENTS.bat`, `start_apollo_ui.bat`, `start_apollo_safe_mode.bat`, `UPDATE_APOLLO_CODE.bat`.

Advanced/developer entrypoints: `install_xtts_v2.bat`, `build_apollo_exe_safer.bat`, `python apollo_update_server.py --root storage/updates/server --port 8765` (local development only).

## Outstanding installation work

- A signed Windows bootstrap installer (MSIX/Inno Setup) that checks prerequisites, creates shortcuts and has a graphical progress display
- First-run wizard to locate Ollama, choose/download the model and test GPU/CPU/voice capability
- Device profiles so desktop, laptop, low-RAM Windows and Raspberry Pi each receive appropriate dependencies
- Backups/restore/export for memory, voice profiles and local projects before migration
- Verified offline dependency bundles and resume support for large downloads
- Hardware compatibility/diagnostics and clear, user-facing error repair suggestions
