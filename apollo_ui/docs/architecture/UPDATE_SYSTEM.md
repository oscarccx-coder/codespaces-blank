# Apollo updates: supported pathways

## Simple Git code updates (developers and source checkouts)

Close Apollo, then run `UPDATE_APOLLO_CODE.bat`, or the equivalent `Setup/03_UPDATE_APOLLO.bat`, or click **Update from Git (main)** in the Update Centre. They share one guarded updater (`Setup/13_UPDATE_GIT_MAIN.bat`). It only fast-forwards the checked-out `main` branch. It rejects an unclean checkout, an unconfigured remote, a detached head and other branches rather than switching branches or force-resetting changes. It does not download XTTS weights. Run `INSTALL_REQUIREMENTS.bat` after a change to core requirements.

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
