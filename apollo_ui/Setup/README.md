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
| `09_SETUP_FOUNDRY_SANDBOX.bat` | Diagnoses Docker engine, optionally starts Docker Desktop, then builds and smoke-tests the isolated PySide6 image with explicit consent; always pauses and logs |
| `14_INSTALL_DOCKER_DESKTOP.bat` | Diagnoses WSL, virtualisation, disk space and installer crashes; offers user-approved official Docker Desktop install using winget; always pauses and logs |
| `15_CHECK_FOUNDRY_PREREQUISITES.bat` | Read-only check for Python, PySide6, Ollama coding model, Docker image, WSL and available Windows disk space |
| `16_INSTALL_FOUNDRY_SCIENCE.bat` | Optional, owner-confirmed SymPy and Matplotlib installation inside Apollo's private virtualenv for trusted local app previews |
| `10_SETUP_WIZARD.bat` | Open the setup wizard directly |
| `12_SETUP_RELEASE_SIGNING.bat` | Generate/reuse a persistent signing identity OFFLINE, display its public fingerprint, and guide first secure release setup (no automatic GitHub secret upload or key trust) |
| `11_FINISH_XTTS_SETUP.bat` | Retry XTTS step 10 configuration without uninstalling/reinstalling packages or downloading the model |

The installer offers user-approved Desktop shortcuts after the private Python dependencies install.

The main launch, installer and repair files remain in `apollo_ui/` as **compatibility entry points**. These Setup scripts are user-friendly front doors, not second conflicting installers. The source directory is derived relative to each script, so Apollo can live on drive F:, C: or another drive.

**Backups:** memory, research, voice profiles and workspace projects; excludes external Ollama/XTTS model weights, update keys, caches and private Python packages. Archives are **not encrypted**. Keep the ZIP confidential and do not sync it to a public repository. Backups may include private medical notes. Test restoring on a spare installation first.

**XTTS:** dependency reinstall can be several GB and may need CUDA and FFmpeg. Existing voice profiles and model weights are not automatically erased. If the clean XTTS installer reached 10/10 and failed saving `settings.json`, use `11_FINISH_XTTS_SETUP.bat` after updating the code. It checks the existing model and writes settings without rerunning heavy dependency installs.

**Raspberry Pi 5:** Use `pi/install_pi.sh` from a Linux terminal instead of Windows .bat files. Its headless service has separate requirements and no Windows GUI.

### Docker/Desktop and Foundry sandbox launchers (Windows)

Both launchers call `Docker_Foundry_Setup.ps1`, always remain visible after success/failure/cancellation, print a nonzero exit code for failures, and append local diagnostic transcripts to:

- `%LOCALAPPDATA%\\Apollo\\setup_logs\\foundry_installdocker.log`
- `%LOCALAPPDATA%\\Apollo\\setup_logs\\foundry_buildimage.log`

They do not uninstall Docker, reset WSL, delete data, modify production Apollo code, or install anything without explicit consent. The Docker installer checks prerequisites and, if needed, uses the official `Docker.DockerDesktop` winget package. Docker Desktop's initial setup and WSL restarts may still require manual interaction. When Docker is ready, the sandbox launcher builds the trusted `apollo-foundry-qt:phase1` image and runs a network-disabled, read-only smoke test. These scripts require Windows PowerShell 5.1. Do not upload local logs publicly because they may include local paths and usernames.
