# Apollo Initiative Director V2: integration slice 1

**Status:** development branch / owner review required. Implemented goal planning plus finite, approved scheduled research and local health checks, **not** a general-purpose autonomous computer executor, Windows background service, signed or deployed release.

## Purpose

Connect Apollo's existing Suggestions app and bounded idle reflection to durable owner-defined strategic goals. Make useful next-step proposals visible and ranked, without changing the execution authority of the existing Learning Missions, Foundry, Workflows, runtime or GitHub updater.

## Existing capabilities reused

- Runtime's \`goals\` SQLite table and lock: authoritative goal IDs and statuses.
- Suggestions Store: persistent questions/proposals, title fingerprints, daily reflection budgets and explicit owner guidance.
- Suggestions UI: review, dismiss, answer, edit and owner-authorised research handoff.
- Learning Missions: existing explicit public-source research consent, worker leases and budgets.
- Bounded local Ollama reflection: existing idle guard, model lock, local-only endpoint and capped daily attempts.

## Added in this slice

1. \`apollo_initiative.InitiativeDirector\` adds **non-destructive** \`initiative_goal_meta\` and \`initiative_step_links\` tables to the existing runtime SQLite database.
2. Goal creation is only available through owner UI methods and requires a title, desired outcome and success metric; priorities range from 1 to 100. Parent goals support up to five ancestry levels. The active initiative count is capped at 40.
3. Existing Suggestions UI becomes **Apollo Initiative Director**, with goal selection, add/pause/resume and proposal controls. Creating a goal does not approve external actions.
4. Bounded idle reflection receives the top eight active owner goals as untrusted *context data*. The model may create proposals/questions, never an approved tool or mission.
5. Proposal ordering uses deterministic token overlap, goal priority and existing mission references. The score is a **heuristic priority**, not a confidence value or task-success metric.
6. The **Propose next step** button creates one deduplicated review-only prompt linked to the goal. It does not start research, Foundry, a workflow, any OS action or a GPU model call.

## Owner-approved scheduling (added in this revision)

The Initiative Director now exposes **Scheduled tasks…** in the existing Apps page.

- Choose **public research** or **Apollo health check**, the local Windows date and time, and **once**, **every day** or **every week**.
- Research accepts an explicit owner-entered research topic or pre-populates the currently selected proposal. The user must tick web approval in the schedule dialog. Each due occurrence creates a distinct **one-step Learning Mission**, with a recorded mission ID; scheduling does not claim the research has already completed.
- Health checks only call the existing **background_intelligence / maintenance_pulse** capability through the module manager (which retains normal permission checks). No arbitrary command execution.
- Each schedule has a finite **1–365 run** limit, defaults to 30 repeated runs, and can be paused, resumed or stopped. Dispatch receipts and failures are retained in a separate SQLite schedule ledger; three consecutive dispatch failures block recurring schedules.
- Scheduling follows the PC's **local wall clock** and OS daylight-saving rules. When Apollo is closed, jobs cannot execute. On reopening, missed occurrences coalesce into **at most one catch-up from the last 24 hours**; older one-time jobs expire without execution.
- On restart, **reserved but unacknowledged** dispatch attempts are marked uncertain and blocked for owner review, rather than blindly duplicating a possibly completed action. Run records have a unique (schedule ID, occurrence timestamp) key.
- Only explicit owner UI actions create or change schedules. Frozen tasks do not inherit permission to operate other tools, external services, purchases, installers, email or protected files.
- The existing app-owned worker checks schedules approximately every **15 seconds** while Apollo is running. This is not a Windows startup service.

The allowed types are deliberately limited. Future releases can add typed templates for other tasks after their permissions and recovery behaviour are verified.

## Permission boundary

- The model-facing module tools remain read-only: \`list_suggestions\` only.
- All goal mutations and next-step requests use owner-only UI methods.
- A suggestion does not grant execution rights, network access, file writes or approvals.
- Public research still requires the existing Suggestions UI approval and separately enabled research tool permission.
- No automatic GitHub publishing, merging, purchases, model changes or physical-device actions.
- Existing reasoning and mission workers remain as before; this slice does **not** introduce a new autonomous background execution thread.

## Verification

New `tests/test_initiative_scheduler.py` exercises one-time/daily/weekly scheduling, explicit authorisation, local-time recurrence across DST, missed-run coalescing, concurrent reservations, uncertain crash recovery, pause/resume/stop, run limits and mocked research/health dispatch. Linux and Windows regression workflows include it.


Focused independent regression cases are in \`tests/test_initiative_director.py\` and cover owner permission, validation, persistence, hierarchy, status, deduplication, ranking and active-goal limits.

**Verification status:** The prior goal-only slice passed its isolated tests. New scheduler tests and full CI must pass before release. Real Windows/PySide6 UI correctness, Ollama research execution, updater reliability and an end-to-end workstation run remain unverified. GitHub CI and the owner's Windows smoke test remain necessary.

Recommended integration testing:
- Run new Initiative Director tests plus existing Suggestions, Learning Missions, Idle Learning and Workflow tests.
- Run Module Validator on \`modules/suggestion_center\`.
- Smoke-test **Apps → Apollo Initiative Director**, add a goal, propose a next step, pause and resume, and verify that existing suggestion/research buttons still work.
- Verify Ollama idle reflection only runs under its pre-existing local, idle and daily-budget guards.
- Run Windows updater rollback checks separately before any signed release.

## Deliberately deferred V2 work

- No universal Mission Director or unattended Windows service yet; only explicitly registered research/health schedule types run automatically while Apollo is open.
- No dynamic execution of self-generated steps; owner approval remains required.
- No cross-domain budget broker, semantic deduplication, independent outcome verifier or cross-app resource scheduler yet.
- No automatic model fine-tuning, live core patching or self-assigned permissions.

Next iteration should first consolidate mission lifecycle state, global resource limits, typed action grants, durable receipts and recovery tests across Learning Missions, Workflows and Foundry before enabling broader initiative execution.
