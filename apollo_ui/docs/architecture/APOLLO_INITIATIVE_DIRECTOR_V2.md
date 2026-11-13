# Apollo Initiative Director V2: integration slice 1

**Status:** development branch / owner review required. This is an implemented *proposal and goal-planning slice*, not a completed general-purpose autonomous executor, and not a signed or deployed release.

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

## Permission boundary

- The model-facing module tools remain read-only: \`list_suggestions\` only.
- All goal mutations and next-step requests use owner-only UI methods.
- A suggestion does not grant execution rights, network access, file writes or approvals.
- Public research still requires the existing Suggestions UI approval and separately enabled research tool permission.
- No automatic GitHub publishing, merging, purchases, model changes or physical-device actions.
- Existing reasoning and mission workers remain as before; this slice does **not** introduce a new autonomous background execution thread.

## Verification

Focused independent regression cases are in \`tests/test_initiative_director.py\` and cover owner permission, validation, persistence, hierarchy, status, deduplication, ranking and active-goal limits.

**Developer verification:** the eight isolated tests passed using a SQLite runtime stub on Python 3.13. They do not establish Windows/PySide6 UI correctness, Ollama interaction, updater reliability or an end-to-end production run. GitHub CI and the owner's Windows smoke test remain necessary.

Recommended integration testing:
- Run new Initiative Director tests plus existing Suggestions, Learning Missions, Idle Learning and Workflow tests.
- Run Module Validator on \`modules/suggestion_center\`.
- Smoke-test **Apps → Apollo Initiative Director**, add a goal, propose a next step, pause and resume, and verify that existing suggestion/research buttons still work.
- Verify Ollama idle reflection only runs under its pre-existing local, idle and daily-budget guards.
- Run Windows updater rollback checks separately before any signed release.

## Deliberately deferred V2 work

- No universal Mission Director or unattended Windows service yet.
- No dynamic execution of self-generated steps; owner approval remains required.
- No cross-domain budget broker, semantic deduplication, independent outcome verifier or cross-app resource scheduler yet.
- No automatic model fine-tuning, live core patching or self-assigned permissions.

Next iteration should first consolidate mission lifecycle state, global resource limits, typed action grants, durable receipts and recovery tests across Learning Missions, Workflows and Foundry before enabling broader initiative execution.
