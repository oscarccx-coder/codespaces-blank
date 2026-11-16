# Apollo updates: supported pathways

## Simple Git code updates (developers and source checkouts)

In a real Apollo Git checkout, **Update Apollo (Git main)** now runs the
guarded source updater. **Check Git main** fetches and checks incoming changes
without installing code; the dedicated **Update from Git (main)** button uses
the same guarded pathway. Apollo still asks before any source update.

The shared `Setup/13_UPDATE_GIT_MAIN.bat` delegates to
`apollo_git_source_update.py`. It requires local `main` and an origin remote;
only a fast-forward is permitted. It refuses modified/untracked **code**,
diverged branches and incoming changes to private runtime data, including
module-local `storage/`, recordings, memory databases and private keys.
Existing locally modified runtime data does not, by itself, block a code-only
update. No reset, clean, forced checkout or automatic stash is performed.

### Automatic private backups, recovery-file repair and safe restore

Each **real Git update** now creates a new SHA256-verified backup of all detected
Apollo-private files (memory databases, WAL/SHM, settings, saved recordings,
profiles, logs, keys, module-local storage and models) before changing code.
By default, backup snapshots go to `<Apollo-Git parent>/Apollo-Private-Backups/
apollo-YYYYMMDD-HHMMSS-<unique>/`, **outside** the checkout. Backups are
private **but not encrypted**; protect the drive and do not upload them.
Large voice/model installations may require significant extra space. An
incomplete backup stops the update and leaves original files in place.
Snapshots are not automatically deleted.

From **Apollo Updates → Advanced options**, choose **Preview backup and
recovery blockers** to see file count, estimated bytes, backup location and
known recovery-script blockers without copying any files. The standard
**Update Apollo (Git main)** button asks before creating the backup. The
equivalent owner-approved command is
`Setup/13_UPDATE_GIT_MAIN.bat --repair-recovery`. The two recognized,
**untracked** leftovers are:
`apollo_ui/Setup/RUN_APOLLO_UPDATER_RECOVERY.bat` and
`apollo_ui/Setup/apollo_git_source_update.py`. They are SHA256-verified,
copied outside Git and relocated only when this exact repair mode is approved.
All other local code changes remain blockers. Neither `reset --hard` nor
`git clean` is used.

After the Git fast-forward (or a failed merge attempt), Apollo verifies the
backup and automatically restores only private paths that are **missing**.
An existing file, even if modified, is never overwritten. Moved recovery
launchers are **never automatically restored into the checkout** because
they would recreate the original blocker; copies remain in the backup's
`relocated/` folder for manual inspection. There is also an
**Restore missing private files...** button accepting a selected snapshot
and asking approval. A restore must match the same checkout path and SHA256
manifest. Code changes, remote private-data changes, failed verification,
inadequate disk space and unsafe links still stop the operation.

**Important:** A backup is not a database-consistent snapshot if Apollo or
its workers are actively writing to files. Close other Apollo processes,
background workers and voice tasks before using the external update launcher.
An in-app update can itself run while Apollo is open, so its backup cannot
guarantee cross-database consistency; prefer closing Apollo and using the
BAT launcher for critical data migrations. This feature does **not** bypass
the PR #66 security gate or make tracked private data safe to publish.

Use `Setup/03_UPDATE_APOLLO.bat --check` for a strictly read-only local
preflight, or `Setup/13_UPDATE_GIT_MAIN.bat --check-remote` to fetch remote
metadata and report `[AVAILABLE]` / `[UP-TO-DATE]` without installing.
A real update reports `[UPDATED]` only after Git advances HEAD. Restart
Apollo after a successful code update; Python dependencies may need separate
setup. This source route is **not a signed release**.

**Security migration warning:** Pulling the future PR #66 cleanup can remove
old tracked private files. The guarded updater must refuse those incoming
changes. Use the verified private-data backup and separately reviewed,
side-by-side migration instead of bypassing the stop. Rotating an exposed
device token and cleaning Git history are separate owner-controlled actions.

## ZIP-to-Git bootstrap (no signed release needed)

For ZIP installations that cannot use the Git update button, select **Install Git source (no release)** in Update Centre or run `Setup/21_INSTALL_GIT_SOURCE.bat`. The batch clones the canonical GitHub `main` branch into a new sibling `Apollo-Git` directory, leaves existing user data and voice models untouched and refuses to overwrite a destination that already exists. The shallow clone is not an Ed25519-signed release.

Then run `Apollo-Git/apollo_ui/Setup/01_INSTALL_APOLLO.bat` to install the new private Python requirements, start with `Setup/02_START_APOLLO.bat` and explicitly migrate private data with Apollo Backup / Restore if needed. Future source updates use **Update from Git (main)** within that Git installation. A code commit must be merged to main before it becomes available. Do not delete the ZIP installation until data restoration and testing are complete.

## Verified signed releases (end-user installations)

The Update Centre checks GitHub Releases, verifies an explicit trusted Ed25519 signing key and every package hash, stages code, creates a backup, and uses an external installer with rollback on failed health checks. No signing key or application update may be trusted/installed by the AI itself. A stable release is published deliberately through the GitHub Actions `Publish signed Apollo Release` workflow with the required secrets, pinned public-key fingerprint, passing regression tests, and manual `PUBLISH` confirmation.

Publishing code to GitHub **does not automatically install or publish** a signed release.

## Advanced local update server (developers)

The old convenience `.bat` wrapper was removed. The underlying server remains available, when deliberately configured, via:

```powershell
python apollo_update_server.py --root storage/updates/server --port 8765
```

Do not expose this local test server publicly. See `docs/architecture/SIGNED_RELEASES_AND_RASPBERRY_PI.md` for trusted release distribution.

## Dependency handling

The Windows dependency install/uninstall launchers affect only the local `apollo_ui/.venv`. Models, voices, memory and projects persist. See `docs/architecture/INSTALLATION_AND_DEPENDENCIES.md`.

## Safe local updater test before installing anything

On Windows open Command Prompt in the **actual Git checkout** and run:

```bat
cd /d "F:\Apollo\apollo 1\apollo_ui"
call "Setup\03_UPDATE_APOLLO.bat" --check
```

Adjust the path to your real installation. This read-only preflight prints the detected repository, branch, Git availability, dirty-file status and a result code. It **does not download or replace source**. Normal double-click launches stay open to display results. The Git updater's summary log is `%TEMP%\Apollo_Git_Main_Update.log`.

After reviewing/merging the changes you actually want into **main**, close Apollo and run the same script **without** `--check` to fast-forward from `origin/main`. Never bypass the dirty-check by discarding saved files. Running the script in a ZIP/download rather than a real Git checkout will give an informative error and cannot update via Git.

## How the release update is tested

GitHub Actions exercises a disposable signed source release using ephemeral test keys, stages the verified ZIP, installs it into a temporary application directory, validates private-data preservation, and intentionally triggers a health-check failure to verify rollback. The Windows CI test creates a separate temporary **local bare Git origin** with spaces and parentheses in its path, then performs a real fast-forward and tests refusal paths. These are integration tests, not changes to your PC.

The signed updater launches in Apollo's private Python environment when available, writes external installer stdout/stderr to `storage/updates/logs/installer-*.log`, waits for Apollo to close, verifies the signature and file digests, saves a backup, installs files, runs a health check and only then attempts a restart. If code is healthy but restart fails, the update remains installed and you can start Apollo manually. A failed code health check still triggers rollback.

**Important:** until an actual signed GitHub Release asset exists and you trust the correct public key (verified independently), the one-click `Update Apollo` release flow cannot install a new release. Commit/PR updates alone do not create that asset. Never use a test key as Apollo's production trust anchor.
