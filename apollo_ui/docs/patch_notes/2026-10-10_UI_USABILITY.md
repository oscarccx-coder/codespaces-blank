# Apollo 7.5.13.9: UI Follow-up and Repository Cleanup

Date: 10 October 2026

## User interface (merged in 7.5.13.8)
- Voice Imprint Lab has individual voice menus with select, use, retrain, rename,
  recoverable delete and reorder actions. Separate scrollable Build / Retrain,
  Test / Use and Advanced Settings tabs keep technical controls out of the way.
- Learning & Reasoning has a clean Learn tab with **Research This Topic**.
  This explicitly invokes Research & Training to fetch public sources and save
  a dated local research file. Source text is not automatically verified.
- Update Centre has one prominent **Update Apollo** button, while source/channel,
  signing-key trust, staged update controls and diagnostics sit under
  **Advanced options**.

## 7.5.13.9 follow-up
- Fixed a one-click update edge case: when the current version is already
  installed, Apollo no longer launches an obsolete previously staged package.
- Existing GitHub signed-release download caching remains in place, so
  an already verified ZIP can be reused without fetching it again.
- Moved all 46 top-level developer regression tests into `tests/`.
  Updated their project-root fixtures, GitHub Actions regression, Pi and
  signed-release checks.
- Signed updates back up and remove the old root-level test scripts on existing installations.
- Excluded developer tests from future signed application bundles, reducing
  update payload clutter while retaining checks in the repository.
- Consolidated patch notes and the older workstation changelog under
  `docs/patch_notes/` with an index.
- Kept primary application, install, repair, update and launch scripts at
  their existing root paths to avoid breaking Windows shortcuts.
- Aligned version metadata to 7.5.13.9.

## Release safeguards
- Live user recordings, XTTS models and local storage are never replaced
  by a signed code release.
- Releases require a pinned Ed25519 signing key, explicit user approval and
  safe backup/rollback behaviour. Merging source code does not itself create
  a signed release.
- Linux CI tests and Pi checks must pass; real Windows GUI and XTTS
  operation still require a local smoke test before a stable release.
