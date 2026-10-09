# Apollo updates: supported pathways

## Simple Git code updates (developers and source checkouts)

Close Apollo, then run `UPDATE_APOLLO_CODE.bat`. The script requires Git, refuses to overwrite a dirty checkout, and pulls changes from the current branch. It does not download XTTS weights. Run `INSTALL_REQUIREMENTS.bat` after a change to core requirements.

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
