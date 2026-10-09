# Apollo 7.5.13.10: Setup Centre

Date: 10 October 2026

## User-facing Setup folder
- Added `Setup/` with numbered Windows .bat launchers for installing, starting, updating,
  repairing XTTS, diagnosing, creating/restoring backups, uninstalling requirements,
  safe-mode startup and opening the setup wizard.
- Existing working root .bat entry points remain in place for shortcuts and internal callers.
- Installer offers current-user Desktop shortcuts only after a user confirmation.
- Raspberry Pi continues to use its separate ARM64 headless installer.

## First-run and Settings wizard
- Apollo displays a friendly first-run Setup & Recovery dialog until the user finishes setup.
- Available again via Settings → Setup & Recovery.
- Checks isolated Python, core Python packages, local Ollama response, XTTS model files
  and voice package versions without silently installing anything.
- Desktop, laptop and Raspberry Pi preference presets store a suggested model and
  display supported operating mode. They do not automatically switch an installed model.

## XTTS reliability
- Voice Imprint Lab's Advanced Settings adds **Troubleshoot XTTS** to report
  missing model files, mismatched runtime packages and the XTTS worker log.
- Voice generation reports worker state and elapsed time after 30 seconds instead of
  an endless, uninformative "Generating" message.
- Default worker timeout reduced from 900 to 240 seconds for new configurations;
  advanced existing timeout settings remain respected. Stop remains available.
- Deep import diagnostic runs outside the GUI, with a 30-second timeout.

## Backup and restore
- Explicit local ZIP backup of saved state, databases, research, voice profiles and
  workspace. SQLite databases use a consistent snapshot API.
- Excludes program code, caches, updater trust material, model weights and venvs.
- Archive inspection validates paths, sizes, hashes and duplicate destinations.
- Restore is a command-line-only, confirmed action with Apollo closed.
- Existing matching files are temporarily copied for rollback if an operation fails.
- Backups are **not encrypted**. Treat them as private and protect them accordingly.

## Validation
- `tests/test_setup_centre.py` checks setup scripts, persistent device choice, safe
  backup round-trips, checksum tampering, traversal rejection and missing-model diagnosis.
- Windows manual GUI/actual NVIDIA XTTS audio testing still required before stable release.
- All code updates continue to use existing signed release verification and rollback.
