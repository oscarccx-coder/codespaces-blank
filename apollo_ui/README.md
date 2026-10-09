# Apollo: offline-first AI workstation

Apollo is a local Windows/PySide6 assistant with Ollama, modular tools, a persistent Home hub, personal memory, isolated voice processing, update/recovery utilities and an evolving coding workspace.

## Start Apollo

From this directory on Windows:
- `start_apollo_ui.bat`: launch Apollo.
- `start_apollo_safe_mode.bat`: troubleshoot misbehaving modules.
- `UPDATE_APOLLO_CODE.bat`: fetch **code changes only** in an existing Git checkout, without downloading the XTTS model again. It refuses to overwrite local changes.
- `REPAIR_VOICE_KEEP_MODEL.bat`: repair the voice dependencies without deleting the downloaded voice model.

Python entry point: `main.py`. The application requires the dependencies listed in `requirements.txt` and local Ollama. XTTS requires its separate optional runtime.

## Project layout

| Path | Role |
|---|---|
| `main.py`, `apollo_shell.py`, `apollo_sidebar.py` | Qt interface, application registry and saved sidebar layout |
| `apollo_config.py`, `apollo_personality.py` | Protected local settings and configurable conversation style |
| `apollo_runtime.py`, `module_manager.py` | Permissions, tasks, recoverability and module lifecycle |
| `modules/` | Installed modules and their manifests |
| `pending_modules/` | Untrusted candidate modules awaiting validation and approval |
| `workers.py` | Background operations |
| `apollo_update.py`, `apollo_release.py`, `apollo_updater.py` | Signed release staging/installation and rollback |
| `storage/` | Local state, logs, memories and voice data: **do not commit user data** |
| `workspace/` | Generated user projects: **not part of code updates** |
| `docs/architecture/` | Current system design and improvement roadmap |
| `docs/patch_notes/` | Version-by-version patch history |
| `docs/legacy_notes/` | Archived historical update instructions |
| `tools/legacy_updates/` | Historical obsolete version-setting batch files, archived as text, **do not execute** |

## Vehicle Diagnostics (OBD-II)

Apollo's **Vehicle Diagnostics** app reads ELM327-compatible USB/Bluetooth COM-port OBD-II live sensor data and stored/pending/permanent fault codes. It has a separate clearly labelled offline demo, optional live refresh, local report export and **no write or fault-clear commands**. Use only while parked. [Set-up and limitations](docs/features/VEHICLE_OBD_DIAGNOSTICS.md).

## XTTS model and GitHub updates

- Shared drop-in folder: `models/voice/xtts_v2/` (add your own `config.json`, `model.pth`, `vocab.json`).
- Your existing `%LOCALAPPDATA%\\Apollo\\models\\voice\\xtts_v2` installation can stay where it is. Voice Lab can remember a different model location on another drive.
- Go to **Settings → Updates → Open Update Centre** to check signed GitHub Releases, download/verify and **Update & Restart** without downloading XTTS again.
- GitHub Releases must contain a signed Apollo ZIP and public key; there is not yet a published release. First run requires one-time key-fingerprint approval.
- [Full setup, signing and safe publishing instructions](docs/architecture/GITHUB_UPDATES_AND_XTTS.md).

## Sidebar and Workstation upgrade

See [Apollo Workstation Roadmap](docs/architecture/APOLLO_WORKSTATION_ROADMAP.md).

Model and personality preferences are saved in `storage/state/user_config.json`, not back into the Git-tracked `config.json`. Existing older installs with local edits to `config.json` may still need a one-time manual migration before pulling changes; back up and review those edits before restoring any tracked file.

The experimental custom sidebar is developed on `feature/apollo-workstation-sidebar`. Home and Settings remain pinned, while other page and module shortcuts can be reordered, hidden or renamed. Do not deploy from a development branch without tests.

## Tests and safeguards

From this folder, with the correct Python environment:

```powershell
python -m unittest test_sidebar_layout test_sidebar_gui_wiring
python test_apollo_shell.py
python test_module_manager_surfaces.py
python test_update_system.py
```

Run a Windows PySide6 launch check after changes to `main.py`. Medical tools and self-modifications must stay behind the existing approval/permission rules. User files and model weights must be stored outside release payloads.

## Older instructions

The previous long release-history README is archived at [docs/legacy_notes/RELEASE_HISTORY.md](docs/legacy_notes/RELEASE_HISTORY.md), so the root stays readable. Obsolete numbered update scripts have been archived rather than used to set misleading historical version numbers.
