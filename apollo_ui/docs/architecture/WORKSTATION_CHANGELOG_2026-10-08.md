# Apollo Workstation Development Changes

Date: 2026-10-08
Branch: `feature/apollo-workstation-sidebar`
Review: GitHub pull request #5 (draft; not deployed to main)

## Implemented on this branch

**Navigation**
- Persistent `apollo_sidebar.py` state, edit/reorder/hide/rename, icons-only, adjustable width.
- Home and Settings protected; built-in and module UI shortcuts share ordering.
- Sidebar Manager available from the sidebar and Settings.
- Existing Hub layout, app registry and module placement remain independent.

**Voice**
- XTTS worker cancellation now signals the waiting request; it no longer waits until a long synthesis timeout merely to recognise cancellation.
- Fixes a speech-worker handoff race that could strand newly queued text.
- Speech I/O now reports job IDs and queued/generating/completed/failed/cancelled states.
- XTTS UI displays cancellation without raising a scary failure dialog.
- The System screen gets live task history and a background "Stop Voice Generation" action.
- The actual Windows XTTS/CUDA integration remains to be tested on the user's machine.

**Personality**
- `apollo_personality.py`: selectable 0 Neutral, 1 Dry, 2 Sharp, 3 Mad Scientist.
- Setting stored in the existing protected local `config.json`; prompt style adapts on the next reply.
- Safety, medical and other high-stakes responses stay serious regardless of setting.

**Local settings and Git updates**
- New `apollo_config.py`: editable model/routing/sarcasm settings live in protected `storage/state/user_config.json`; tracked `config.json` stays the release baseline.
- Older installations that already modified tracked `config.json` may require one-time careful migration and must not blindly discard their changes.

**Memory**
- Memory Bank supports user-edited corrections by stable record ID and a visible "Edit Selected" control.
- Keeps source, other records and timestamp metadata intact; rejects identical-record collisions.

**Updates and recovery**
- The signed release installer rejects Windows drive/UNC/traversal/device paths, duplicate entries, conflicting removals and out-of-root symlinks.
- All staged payload hashes are validated before the first live file write.
- Rollback response no longer falsely reports success if restoration itself fails.
- Release builder excludes `Audio`, `models`, `storage`, virtualenvs and build cache.
- Recovery snapshots include current core source and candidate/live module source files without private user media.
- Existing `UPDATE_APOLLO_CODE.bat` already transfers Git changes without downloading the local XTTS model again.

**Repository organisation**
- Root README replaced with concise current architecture and launch commands; full previous history moved to `docs/legacy_notes/RELEASE_HISTORY.md`.
- Seven obsolete numbered version-fixing batch scripts moved to `tools/legacy_updates/` and renamed `.bat.txt` to prevent accidental execution.
- Four historical patch notes moved to `docs/legacy_notes/`.
- Active launch, repair and update scripts remain at their original paths.
- `tools/audit_repository.py` can inspect tracked files and reject newly committed sensitive paths in CI.
- Previously committed recordings and runtime files are NOT erased from public Git history. These require a separate authorised privacy cleanup/migration.

**Coding team**
- `pending_modules/coding_team/` candidate: serial architect/implementer/tester/reviewer/integrator task turns, documented evidence, review loop and explicit user approval inside its UI.
- Candidate intentionally does not generate, execute, merge or deploy code and is not installed in Apollo.
- It is a safe workflow foundation, not yet the complete autonomous programming company.

**Automated regression infrastructure**
- GitHub Actions workflow: `.github/workflows/apollo-regressions.yml`.
- Tests: sidebar state, GUI wiring, voice queue state, update path safety, memory corrections, personality controls, system jobs, snapshots, pending Coding Team and existing shell/module/signed updater checks.
- Headless syntax, signature/update rollback and module tests can pass on GitHub's Linux runner; this is not proof the Windows GUI and GPU audio pipeline function.

## Still open (do not describe as finished)

1. Windows launch smoke test of all pages, especially sidebar drag/drop and System job monitor.
2. RTX 3060 and XTTS test with real model/reference audio: cancel during load/inference, rapid speak/stop, recovery after worker crash.
3. Multi-model GPU VRAM reservation/broker; current GPU Monitor reports resource use but does not enforce budgets.
4. Fully operational multi-agent coding engine, sandboxes, real code testing, version integration and learning. Candidate only tracks work.
5. Robust in-app update UI with signed delta bundles, low-storage handling and full migration checks. Git code-only updater and signed package updater already exist, but have distinct operation modes.
6. Unifying every asynchronous service under durable cancel/retry/heartbeat job management; current System panel is read-only history with explicit voice stop.
7. User-data and Git-history privacy cleanup after backed-up migration and review.

## Verification gates before merge

1. CI green on the exact proposed merge commit.
2. Windows PySide6 application starts and core navigation stays functional after saving/restarting.
3. Dynamic sidebar module placement, memory UI, settings persistence and voice stop verified in a live build.
4. Confirm no release/backup operation overwrites model files or user storage.
5. Review changes against production configuration and keep a local recovery snapshot.

No forced push, history rewrite, unattended module installation or changes to the production main branch were performed.
