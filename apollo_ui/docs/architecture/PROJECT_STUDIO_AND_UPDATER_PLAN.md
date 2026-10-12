# Apollo Project Studio and full updater roadmap

Implementation branch: feature/apollo-project-studio-v1

## Release state

**Alpha integration candidate, not a beta or stable release.**
The PR implements an initial saved Project Studio and two updater reliability
improvements. It does not promise self-executing coding agents or guaranteed
recovery from unexpected power loss.

## Project Studio (new application under Coding)

### User flow
1. Select **Coding -> Project Studio** in Apollo's Apps catalog.
2. Create an **App Project** with title and requirements.
3. Apollo creates a local project folder at \`workspace/app_development/app-<id>-<slug>\`
   and five initial roles: Architect, Implementer, Tester, Reviewer, Integrator.
4. Add subtasks beneath a selected role, assign the specialist and write
   measurable instructions.
5. Select a task and choose **Draft with Local AI**. This is an *explicit*
   owner-triggered, single GPU worker: one HTTP request to the local Ollama
   model, capped output/time; it cannot call shell, web, files or modules.
6. Inspect the draft in the task panel. **Accept Draft** or **Request Changes**.
   Rejected drafts are retained with evidence and can be revised.
7. File a bug under **Issues & Rework**. **Create Fix Task** assigns it to
   Implementer. Close only after an accepted fix task.
8. If Apollo crashes while a worker runs, click **Recover Interrupted Jobs**,
   inspect the blocked task and choose **Retry / Reopen**.
9. **Approve Reviewed Project** records the owner's review only. It does not
   compile, execute, install, publish, merge a branch or upgrade Apollo.

### Persistent files and privacy

* SQLite DB: \`storage/databases/project_studio.db\`, excluded by Git ignore.
* Project folder: \`workspace/app_development/...\`, excluded by Git ignore.
* No private project text/recordings included in public CI or release assets.
* Project titles are normalised to ID-prefixed safe relative paths.
* No auto agent loop, no shell execution, and only AI read tools for project
  metadata. Real build/test execution remains a **separate permission-gated milestone**.
* Real Windows PySide6 UI and local Ollama require owner device smoke tests.
* A manually created markdown app brief is not a built executable application.

## Updating: signed release first, Git source updates for development

Existing mechanisms:
- Simple Git code updater, refusing dirty checkouts, source-only fetch/pull.
- Signed GitHub Releases, pinned public Ed25519 key, per-file SHA256 checks,
  staging, external install, backup, post-install health check and rollback.

New first-slice changes:
- Partial GitHub Release downloads persist as \`.part\` on a network interruption.
- A retry uses HTTP Range only when the server confirms the exact starting byte;
  a server ignoring Range causes a clean restart instead of appending.
- Package only becomes a final ZIP after the response completes; it is still
  untrusted until the existing signature and content checks pass.
- Full disk, permissions or file-lock errors during pre-install backup now
  refuse installation without modifying live code.
- Regression tests simulate drops, invalid ranges, redirection and backup
  errors, in addition to the existing rollback tests.

### Further work for a full updater (still outstanding)

- [ ] Reproduce the reported **14% update failure** and identify its exact phase
      (Git, Python install, signed-release download, or external install).
- [ ] Add **persistent write-ahead transaction journal** with a repair/startup
      recovery command for power loss or a killed updater halfway through.
- [ ] Run disk-space preflight for download, extracted ZIP, backup and database
      migration before installation; report available and required GB.
- [ ] Provide cancel/pause/resume UI, stage names and actionable log viewer.
- [ ] Preserve trusted key identity and allow pinned rollback to a locally
      available verified previous release.
- [ ] Verify atomic database migrations with restore on failure.
- [ ] Test real Windows launcher failure, model file locks, process crashes,
      no-network cases and interrupted filesystem operations.
- [ ] Prepare one-click installer/updater for non-Git Apollo users.
- [ ] Audit and remove tracked private runtime data from public Git *and history*
      with owner authorisation and secure credential handling.
- [ ] Confirm official 8.x beta approval gates then 1.x version migration,
      rather than accidentally presenting 8 as a final public major version.

## Further work for fully autonomous group coding (not yet in this PR)

- [ ] AI manager proposes **structured** tasks, subtasks, dependencies,
      acceptance tests and resource estimates; owner reviews before dispatch.
- [ ] Role-specific tools and least-privilege permissions per project.
- [ ] Isolated Git worktrees/project snapshots and strict resource/time budgets.
- [ ] Tool-runner sandbox with allowlisted commands, no implicit network or
      access to Apollo's private health/memory/voice files.
- [ ] Reproducible build, launch-smoke and crash-injection test jobs. Never
      claim a draft passed merely because the model said so.
- [ ] Review-gated file diffs, version tags, signed app artifacts and rollback.
- [ ] Autonomous issue reassignment only after human approval of a queued task.
- [ ] Team manager resumes after interruption without duplicate/inconsistent
      task attempts; bounded retries and deterministic job identifiers.
- [ ] Role lesson memory stores test-proven corrections rather than AI claims.

## UI redesign references and targeted improvements

* **Linear**: project list, Kanban status, bugs, dependencies, reviewer queue.
* **Cursor**: worker progress, results waiting for review, diff previews.
* **GitHub Desktop**: readable release diffs, history, rollback points.
* **Notion**: saved projects as a database, cards, tags and task drill-down.
* **Raycast**: one universal search and keyboard command palette.

Application layout target:
- Top: global search, assistant, version and important status.
- Left: Home, Chat, Projects, Workers, Updates, Settings.
- Main: friendly app cards or one project with Tasks / Issues / Files / Builds.
- Right or drawer: latest activity, active workers, concise diagnostics.
- Bottom: meaningful short success/failure messages, expandable detail.
- Put specialist controls under **Advanced** rather than filling normal pages
  with cryptic switches and endless forms.
- Use consistent actions: **Start**, **Stop**, **Retry**, **Review**, **Fix**,
  **Restore**. Keep them visible near the item instead of at page bottom.

## Pre-beta evidence checklist

- [ ] PR unit/CI, Windows installation CI and Pi software CI green.
- [ ] Real Windows Project Studio create/select/subtask/draft/review/issue
      roundtrip through two launches.
- [ ] Kill Ollama while drafting, recover failed task, retry and prove no GUI hang.
- [ ] Simulate update interruption at start, 14%, 50%, apply, health and restart;
      demonstrate last bootable build survives or recovery works.
- [ ] Confirm voice model weights, private memory, project files and keys
      have unchanged checksums through updates.
- [ ] Complete repository privacy audit before public beta release.

Open issues: #27 (14% crash), #28 (Git privacy).
This file is a design and test plan, **not evidence the unchecked work is complete**.
