# Apollo Setup

**Start here:** double-click `01_INSTALL_APOLLO.bat` (creates Apollo's private Python environment and opens the setup wizard). Afterwards use `02_START_APOLLO.bat`.

| File | What it does |
|---|---|
| `01_INSTALL_APOLLO.bat` | Install/repair core requirements, then open setup |
| `02_START_APOLLO.bat` | Launch Apollo |
| `03_UPDATE_APOLLO.bat` | Safely fast-forward a clean local Git checkout from `origin/main` only; `--check` is read-only |
| `04_REPAIR_VOICE.bat` | Install/repair optional XTTS Python runtime |
| `05_DIAGNOSE.bat` | Check Ollama, XTTS model files, packages and isolated XTTS imports |
| `06_BACKUP.bat` | Create a local, unencrypted data backup ZIP |
| `07_RESTORE_BACKUP.bat` | Restore a user-selected ZIP after confirmation (close Apollo first) |
| `08_UNINSTALL_REQUIREMENTS.bat` | Remove only Apollo's private Python `.venv` after confirmation |
| `09_START_SAFE_MODE.bat` | Troubleshoot without loading risky modules |
| `09_SETUP_FOUNDRY_SANDBOX.bat` | Build the trusted isolated PySide6 Docker test image (requires running Docker Desktop) |
| `14_INSTALL_DOCKER_DESKTOP.bat` | Optional, explicitly confirmed official Docker Desktop installation using winget; complete WSL 2 / Docker first-run setup manually |
| `15_CHECK_FOUNDRY_PREREQUISITES.bat` | Read-only check for Python, PySide6, Ollama coding model, Docker image, WSL and available Windows disk space |
| `18_TEST_APOLLO_UPDATER.bat` | **Read-only installer self-test:** verify main-branch Git preflight and execute disposable offline Git/Ed25519 signed-update/rollback regressions in Apollo's private Python environment |
| `16_INSTALL_FOUNDRY_SCIENCE.bat` | Optional, owner-confirmed SymPy and Matplotlib installation inside Apollo's private virtualenv for trusted local app previews |
| `10_SETUP_WIZARD.bat` | Open the setup wizard directly |
| `12_SETUP_RELEASE_SIGNING.bat` | Generate/reuse a persistent signing identity OFFLINE, display its public fingerprint, and guide first secure release setup (no automatic GitHub secret upload or key trust) |
| `11_FINISH_XTTS_SETUP.bat` | Retry XTTS step 10 configuration without uninstalling/reinstalling packages or downloading the model |

The installer offers user-approved Desktop shortcuts after the private Python dependencies install.

The main launch, installer and repair files remain in `apollo_ui/` as **compatibility entry points**. These Setup scripts are user-friendly front doors, not second conflicting installers. The source directory is derived relative to each script, so Apollo can live on drive F:, C: or another drive.

**Backups:** memory, research, voice profiles and workspace projects; excludes external Ollama/XTTS model weights, update keys, caches and private Python packages. Archives are **not encrypted**. Keep the ZIP confidential and do not sync it to a public repository. Backups may include private medical notes. Test restoring on a spare installation first.

**XTTS:** dependency reinstall can be several GB and may need CUDA and FFmpeg. Existing voice profiles and model weights are not automatically erased. If the clean XTTS installer reached 10/10 and failed saving `settings.json`, use `11_FINISH_XTTS_SETUP.bat` after updating the code. It checks the existing model and writes settings without rerunning heavy dependency installs.

**Raspberry Pi 5:** Use `pi/install_pi.sh` from a Linux terminal instead of Windows .bat files. Its headless service has separate requirements and no Windows GUI.

**Updater self-test:** Double-click `18_TEST_APOLLO_UPDATER.bat`. It does **not** pull, install, upgrade models, create external accounts or change live Apollo code. It prints a check result, then runs offline signed-release and disposable Git regression tests using private Python. Failure logs are preserved under `%TEMP%\Apollo_Updater_Self_Test.log`. If the folder isn't a clean `main` Git checkout, the preflight correctly reports a warning. Fix checkout issues before attempting a real source update. CI uses `--tests-only` because pull request checkouts intentionally have detached HEAD.
