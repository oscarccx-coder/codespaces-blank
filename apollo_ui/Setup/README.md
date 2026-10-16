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
| `09_SETUP_FOUNDRY_SANDBOX.bat` | Build the trusted isolated PySide6 Docker test image (requires running Docker Desktop) |
| `14_INSTALL_DOCKER_DESKTOP.bat` | Optional, explicitly confirmed official Docker Desktop installation using winget; complete WSL 2 / Docker first-run setup manually |
| `10_SETUP_WIZARD.bat` | Open the setup wizard directly |
| `12_SETUP_RELEASE_SIGNING.bat` | Generate/reuse a persistent signing identity OFFLINE, display its public fingerprint, and guide first secure release setup (no automatic GitHub secret upload or key trust) |
| `11_FINISH_XTTS_SETUP.bat` | Retry XTTS step 10 configuration without uninstalling/reinstalling packages or downloading the model |

The installer offers user-approved Desktop shortcuts after the private Python dependencies install.

The main launch, installer and repair files remain in `apollo_ui/` as **compatibility entry points**. These Setup scripts are user-friendly front doors, not second conflicting installers. The source directory is derived relative to each script, so Apollo can live on drive F:, C: or another drive.

**Backups:** memory, research, voice profiles and workspace projects; excludes external Ollama/XTTS model weights, update keys, caches and private Python packages. Archives are **not encrypted**. Keep the ZIP confidential and do not sync it to a public repository. Backups may include private medical notes. Test restoring on a spare installation first.

**XTTS:** dependency reinstall can be several GB and may need CUDA and FFmpeg. Existing voice profiles and model weights are not automatically erased. If the clean XTTS installer reached 10/10 and failed saving `settings.json`, use `11_FINISH_XTTS_SETUP.bat` after updating the code. It checks the existing model and writes settings without rerunning heavy dependency installs.

**Raspberry Pi 5:** Use `pi/install_pi.sh` from a Linux terminal instead of Windows .bat files. Its headless service has separate requirements and no Windows GUI.
