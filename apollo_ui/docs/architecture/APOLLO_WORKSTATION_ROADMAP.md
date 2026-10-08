# Apollo Workstation Roadmap

Updated: 2026-10-08
Repository: oscarccx-coder/codespaces-blank
Implementation branch: feature/apollo-workstation-sidebar

## Principle

Build Apollo as an offline-first, modular AI workstation, not a single screen containing every capability. Reuse ApolloShell, ModuleManager, ApolloRuntime, Model Runtime, Task & Goal Engine and the signed updater. New services must expose auditable permissions and failure recovery. Changes below are proposals unless marked IMPLEMENTED.

## Status at this branch

- IMPLEMENTED (initial): customisable core + installed-module sidebar, Home and Settings always visible, drag reorder, checked visibility, rename, width, collapsed icon mode, saved layout, corruption fallback. Persistence is a new separate JSON file, so Hub tile layout and enabled module state are not mutated.
- IMPLEMENTED (existing): Hub editor and app/module catalog via apollo_shell.py.
- IMPLEMENTED (existing): module validation/activation controls in module_manager.py, permission gate/task journal/snapshots in apollo_runtime.py.
- IMPLEMENTED (existing): git-based code-only updater in UPDATE_APOLLO_CODE.bat and signed-package foundation in apollo_update.py.
- IMPLEMENTED (existing): model inventory/routing in modules/model_runtime and task planning in modules/task_engine.
- PLANNED: items below not already listed as implemented.
- VALIDATION: unit tests are added for sidebar persistence. A full Windows/PySide6 GUI smoke test on the actual Apollo machine is still required before merge.

## P0 - Safe navigation and interface (first slice)

Files:
- apollo_sidebar.py stores sidebar preferences at storage/state/shell/sidebar_layout.json.
- main.py consumes the preferences and opens the Sidebar Manager.
- test_sidebar_layout.py tests state roundtrip and safeguards.

Acceptance:
- Home (internal ID Hub) stays at top. Settings stays at bottom, regardless of saved or edited data.
- Built-in and module UI shortcuts can be moved, hidden and renamed, without disabling modules.
- Newly installed module sidebar pages appear automatically and remain accessible even if a module temporarily disappears and returns.
- Collapsed icons have tooltips; expanded width persists after restart.
- Corrupt JSON is preserved for recovery; atomic writes avoid half-written settings.
- Existing Ctrl+K command palette and Home tile pins continue to work.
- Settings should eventually expose the same sidebar editor rather than duplicating its state.
- Later enhancement: user-created groups/folders, keyboard-accessible ordering, optional right-hand sidebar, and fully configurable icon mapping.

## P0.5 - Repository privacy and reproducible releases

The repository is currently public and previously tracked audio, voice training data and runtime storage remain in the repository and Git history. Additional ignore rules prevent newly created local media/storage from being accidentally added, but DO NOT remove historical tracked content. Before a public release, audit the tracked tree/history for sensitive recordings, personal health data, device metadata, secrets and large generated assets. Plan removals and any destructive history rewrite separately with user approval. A gitignore change alone is insufficient.

Shift any required baseline storage to sanitised seed/migration files. Keep tests on synthetic samples rather than real user voice/profile data. Include an explicit release preflight that fails if new runtime media, databases, keys or private state are tracked. If history is rewritten, coordinate backup, revocation/rotation, collaborator clones and force-push approval first.

## P1 - Voice stability and personality

Existing relevant files: modules/voice_imprint_trainer, workers.py, XTTS_RUNTIME.md, runtime config.
Deliverables:
1. Define cancellable speech jobs: queued, loading, synthesising, playing, completed, cancelled, failed; bounded queue length and distinct request IDs.
2. Run XTTS in an isolated worker process with a monitored timeout, proper termination/reaping and explicit status changes when inference hangs. Never leave a stale "generating in background" banner.
3. Avoid multiple model loads, test speaker wav/FFmpeg runtime, rate-limit synthesis, and recover cleanly from worker death.
4. Separate speech personality from model prompts: adjustable sarcasm intensity 0..3; style affects non-medical responses only, no insulting advice in health/safety workflows.
5. Add stop/play, output device selection, deterministic log captures and mock-worker tests before running actual RTX 3060 GPU tests.

Exit: 10 repeat speak/stop cycles; cancel while loading and synthesising; recover after killing XTTS subprocess; no stray workers; no GUI freezes.

## P2 - Incremental update and rollback

Existing: UPDATE_APOLLO_CODE.bat uses git fetch/pull and does NOT redownload the XTTS model. Signed release service and external updater already exist.
Deliverables:
1. Consolidate the two update paths into a clear in-app Update Centre with channels and diff preview.
2. Code-only updates transfer changed tracked files. Keep speech models and downloaded model caches outside replaceable app code.
3. Always preserve user storage, workspace, config, audio profiles, secrets and existing virtual environments unless user explicitly approves a migration.
4. Verify author/signature and hashes, stage updates, create restore point, run preflight and postflight health checks, then restart/rollback.
5. Handle dirty git trees, low disk space, unsupported Python versions, interrupted network transfers and incompatible database migrations.
6. Never automatically merge/pull over user work; never run unsigned arbitrary release packages.

Exit: updated code without model redownload; forced offline interruption and failed postflight return to last bootable build.

## P3 - Compute and model control

Extend modules/model_runtime and modules/gpu_monitor instead of replacing them.
- Allocate a GPU budget across Ollama and XTTS. Queue incompatible workloads with visible wait/cancel controls.
- Expose RAM/VRAM, disk, active models, profile parameters, estimated memory before load and CPU fallback.
- Persist role-to-model mappings and support offline operation.
- Do not claim precise VRAM needs from parameter counts alone; measure actual quantised model allocations.
- Test cancellation/release after failed model load and GPU OOM.

Exit: no uncontrolled VRAM contention; per-model role overrides can be changed without restarting Apollo.

## P4 - Unified jobs and diagnostics

Existing ApolloRuntime contains task history, notifications, permission gating and snapshots; Task Engine contains persistent plans.
- Add a durable JobController with IDs, states, progress, cancellation tokens, heartbeats, resource claims and retry policy.
- Differentiate terminating a worker PROCESS from merely abandoning a Python THREAD.
- Surface jobs in a Task Manager page with logs, elapsed time, error details and explicit stop/retry.
- Add crash diagnostics and a health report covering modules, model endpoints, worker processes, local disk and update consistency.
- Quarantine crash-looping modules; allow safe-mode recovery.

Exit: every long-running operation has owner, progress, stop behavior and a visible terminal state.

## P5 - Memory Explorer and module SDK

- Add searchable memory records, source/created timestamps, provenance, correction and per-record delete.
- Explicitly distinguish transient chat history, long-term user facts and model weights. UI deletions must actually delete backing records or clearly state limitations.
- Expand module manifests with UI metadata: stable ID, title, icon, category, permissions, settings schema, migration compatibility and enabled surfaces.
- Limit untrusted module filesystem/network access with existing permission gate and isolated validation.
- Keep sidebar visibility independent of module activation and installation.

Exit: user can audit and correct stored records; installing/uninstalling a module does not scramble sidebar preferences or delete unrelated data.

## P6 - Multi-agent coding studio

Existing Task Engine and module factory form the base.
- Manager decomposes request into explicit acceptance tests, dependency graph and role assignments.
- Specialists: Architect, Implementer, Tester, Reviewer, Integrator. Each agent works on branch/worktree or isolated project snapshot.
- Manager serialises conflicting edits and runs unit tests before integration, then full application startup smoke test.
- User receives build, review notes and test instructions, with manual approval before writing to Apollo's live core.
- Role learning stores only test-verified lessons with evidence, expiry and ability to revoke; never trains on an unverified failure as a success.
- Set iteration/time/token/disk caps and early-stop criteria. No unlimited 12-hour unattended upgrades without explicit resource limits.
- Rollback to last known good version, immutable task log and safe sandbox for generated programs.

Exit: end-to-end project generation, tests, staged handoff, review, bug-fix iteration and reproducible recovery, all without autonomously rewriting the trusted core.

## P7 - Controlled self-improvement and deployment

- Apollo may propose a change, write it in an isolated branch, run tests and explain the diff.
- Privileged capabilities and medical/financial/sensitive actions ALWAYS require explicit user approval where applicable.
- Apply only signed/reviewed builds to production; retain a separate stable channel and rollback history.
- Future fleet/Pi deployments must have versioned API contracts, capability-specific permission policies and offline-first behavior.

Exit: Apollo can improve a candidate version but cannot silently promote it to the running trusted version.

## Safety and implementation sequence

1. Merge P0 only after syntax check, sidebar unit tests, existing app-shell tests and Windows GUI click-through.
2. Work on P1/P2 as independent, reviewable branches to avoid destabilising navigation while fixing XTTS.
3. Introduce JobController before broad autonomous background work.
4. Implement compute brokerage before concurrent multi-agent + XTTS inference on a 12 GB GPU.
5. Build coding studio only after snapshots, approval gates, resource quotas and rollback are demonstrably reliable.

## Windows test checklist for first sidebar release

- Launch normally and in safe mode; inspect for startup/import errors.
- Click Home, Chat, Workshop, module page and Settings. Hide Chat, open via Ctrl+K, restore from Sidebar Manager.
- Drag Workshop above Chat, rename Workshop to Coding Studio, collapse to icons, restart: confirm preferences persist.
- Change dynamic module UI placement Apps -> Sidebar -> Apps; verify no orphaned button and no broken module page.
- Corrupt only a copy of sidebar_layout.json, restart, check backup and defaults. Do not damage real user profile.
- Repeat at 1100x700 and large monitor/window; check scrolling and buttons without layout clipping.
- Confirm no changes to existing Hub tile arrangement, installed module enabled flags or stored medical data.
