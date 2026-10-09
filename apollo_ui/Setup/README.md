# Apollo Setup

**Start here:** double-click `01_INSTALL_APOLLO.bat` (creates Apollo's private Python environment and opens the setup wizard). Afterwards use `02_START_APOLLO.bat`.

| File | What it does |
|---|---|
| `01_INSTALL_APOLLO.bat` | Install/repair core requirements, then open setup |
| `02_START_APOLLO.bat` | Launch Apollo |
| `03_UPDATE_APOLLO.bat` | Pull code changes in a clean Git checkout only |
| `04_REPAIR_VOICE.bat` | Install/repair optional XTTS Python runtime |
| `05_DIAGNOSE.bat` | Check Ollama, XTTS model files, packages and isolated XTTS imports |
| `06_BACKUP.bat` | Create a local, unencrypted data backup ZIP |
| `07_RESTORE_BACKUP.bat` | Restore a user-selected ZIP after confirmation (close Apollo first) |
| `08_UNINSTALL_REQUIREMENTS.bat` | Remove only Apollo's private Python `.venv` after confirmation |
| `09_START_SAFE_MODE.bat` | Troubleshoot without loading risky modules |
| `10_SETUP_WIZARD.bat` | Open the setup wizard directly |

The installer offers user-approved Desktop shortcuts after the private Python dependencies install.\n\nThe main launch, installer and repair files remain in `apollo_ui/` as **compatibility entry points**. These Setup scripts are user-friendly front doors, not second conflicting installers. The source directory is derived relative to each script, so Apollo can live on drive F:, C: or another drive.

**Backups:** memory, research, voice profiles and workspace projects; excludes external Ollama/XTTS model weights, update keys, caches and private Python packages. Archives are **not encrypted**. Keep the ZIP confidential and do not sync it to a public repository. Backups may include private medical notes. Test restoring on a spare installation first.

**XTTS:** dependency reinstall can be several GB and may need CUDA and FFmpeg. Existing voice profiles and model weights are not automatically erased.

**Raspberry Pi 5:** Use `pi/install_pi.sh` from a Linux terminal instead of Windows .bat files. Its headless service has separate requirements and no Windows GUI.
