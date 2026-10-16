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

## Docker and Foundry sandbox installers that disappear on double-click

The Docker Desktop installer (`14_INSTALL_DOCKER_DESKTOP.bat`) and the Foundry sandbox image setup (`09_SETUP_FOUNDRY_SANDBOX.bat`) now display a final result and **wait for a keypress** even when an error occurs. Neither should close immediately on a missing Docker CLI, an unavailable engine or a failed image build.

Run `14_INSTALL_DOCKER_DESKTOP.bat` first if Docker is not installed. It asks before invoking the official `winget install` command. After Docker Desktop is installed, finish first-run setup, start its engine and select Linux containers. Then run `09_SETUP_FOUNDRY_SANDBOX.bat` and approve the initial test-image build. Installing Docker Desktop alone does not build Apollo's test image.

Both batches support a read-only `--check` argument for diagnostics (no install/build/approval prompts), plus `--no-pause` for already-attached terminals. The sandbox check additionally verifies that `apollo-foundry-qt:phase1` is present.

For an error that occurs *before* a window can display, use Command Prompt rather than double-clicking:

```bat
cd /d "F:\Apollo\apollo 1\apollo_ui"
call "Setup\14_INSTALL_DOCKER_DESKTOP.bat"
call "Setup\09_SETUP_FOUNDRY_SANDBOX.bat"
```

Adjust the Apollo location to your installation. Keep the Command Prompt open to read actual Docker and `winget` errors. Local summary logs are written to `%TEMP%\Apollo_Docker_Desktop_Setup.log` and `%TEMP%\Apollo_Foundry_Sandbox_Setup.log`.

If you see **Docker CLI found but engine unavailable**, open Docker Desktop and check the WSL 2/backend status, virtualization and available disk space. If you see **not running Linux containers**, change Docker Desktop's container mode. If `winget` is missing, use Docker's official Windows installer, then run the sandbox image setup separately.

The noninteractive Windows CI smoke tests mock Docker; they **never install Docker or pull/build a live image**. A real installation still requires testing on the owner's PC.
