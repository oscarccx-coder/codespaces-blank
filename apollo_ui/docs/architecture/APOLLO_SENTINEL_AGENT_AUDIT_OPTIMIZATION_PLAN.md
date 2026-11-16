# Apollo Sentinel: Cross-Agent Auditing, Conflict Detection and Optimisation

**Status:** PROPOSAL ONLY. Not implemented, tested, merged or installed.
**Project:** ZSS Laboratories / Apollo Foundry
**Target:** after reliability baseline, as small reviewable pull requests
**Branch:** `feature/apollo-sentinel-audit-optimization-plan`
**Reference:** user-provided screenshot of an AI assistant reportedly auditing agents, catching conflicts and flagging repairs. It is a *design inspiration*, not proof of a working implementation.

## 1. Mission

Make Apollo Foundry independently check whether its specialists are doing the *correct work*, agreeing on a single authoritative specification, producing actual files, running appropriate tests, using local resources responsibly and reporting real evidence.

Sentinel must be able to answer:

- Which agent is working on which exact requirement and source revision?
- Did the result exist on disk? Which files and SHA-256 hashes changed?
- What tests **actually ran**? What were their exit codes, artifacts and limits?
- Did two specialists contradict each other, edit the same interface or use incompatible assumptions?
- What is the smallest safe next action to resolve each problem?
- Did a proposed optimisation improve held-out project outcomes or measurable resources, compared with a recorded baseline?
- Can a mission be paused, resumed or recovered without losing findings or silently repeating side effects?

**Not in scope:** consciousness claims, unbounded self-modifying core code, autonomous releases, external system control, arbitrary user-home scanning, scraping personal data, or describing static checks as proof of functional correctness.

## 2. Confirmed starting point (main, inspected 2026-11-01)

- `apollo_project_studio.py`: SQLite `projects`, `tasks`, `issues`, `events`, `test_runs`, `meetings`, `task_dependencies`; existing review states and project-local folders.
- `modules/project_studio/module.py`: Foundry PySide6 UI and human-controlled continuous build / pause / resume / stop; model worker tasks.
- `apollo_project_workers.py`: bounded local Ollama drafting, serialised via `MODEL_LOCK`; specialist roles manager, architect, implementer, tester, reviewer, integrator.
- `apollo_foundry_checks.py`: non-executing AST / UI-backend contract checks.
- `apollo_foundry_sandbox.py`: opt-in restricted Docker unit/UI/GUI tests, recorded limitations; no host execution of untrusted generated code.
- `modules/verification_engine/module.py`: static workspace and action-history verification, NOT end-to-end functionality.
- `modules/activity_trace/module.py`: action/task and event history.
- `modules/benchmark_suite/module.py`: syntax/module availability checks, not agent task-success benchmarking.
- `modules/self_improvement_lab/module.py`: existing TODO/FIXME audit, staged candidate proposals, no live-core auto-application.
- `docs/architecture/APOLLO_WORKSTATION_ROADMAP.md`: calls for a durable JobController, compute brokerage, isolation, peer review, and owner-controlled releases.

**Do not replace these systems.** Extend the existing Foundry storage and UI, reuse the runtime permissions, existing verification and sandbox engines. Verify exact live code before each implementation slice. Some documented features are experimental and may not be installed.

## 3. High-level architecture

```text
Project requirements + human-approved mission scope
              |
Foundry Manager -- shared specification/version, task dependency DAG
              |
Workers (architect, implementer, tester, reviewer, integrator)
              | structured evidence envelopes, events, tests, file hashes
              v
      Apollo Sentinel Coordinator
       /         |         |          \
 Evidence      Conflict   Benchmark    Risk / permission
 Inspector     Detector   Analyst      Inspector
       \         |         |          /
              Findings Ledger
                 |
     Deterministic severity / action policy
                 |
      Reviewer + bounded Repair Planner
                 |
  Project-local candidate -> Sandbox tests -> independent re-audit
                 |
          Human review and approval
```

### 3.1 Component boundaries

Recommended additive modules, subject to inspection:
- `apollo_foundry_audit.py`: read-only evidence collector, deterministic rule evaluators, normalised findings, stable IDs.
- `apollo_foundry_conflicts.py`: dependency / task / file / interface / requirement consistency checks.
- `apollo_foundry_metrics.py`: baseline capture, actual test and token/timing/resource measurements.
- `apollo_foundry_remediation.py`: proposals and restricted repair task creation, no direct promotion to trusted core.
- `modules/project_studio/module.py`: integrate a **Sentinel** tab or panel in existing Foundry; do not create a competing Project Studio.
- `apollo_project_studio.py`: **additive** migration for audit runs, findings, measurements and repair associations, preserving existing IDs/data.
- `tests/test_foundry_sentinel.py`, `tests/test_foundry_sentinel_conflicts.py`, `tests/test_foundry_sentinel_recovery.py`: deterministic synthetic tests.

Do not store model-generated recommendations as factual test results. No third-party agent runtime or cloud subscription is required for the MVP.

## 4. Auditing events and mission state

Triggers:
1. **Manual:** Audit Now / Audit Selected Task.
2. **Event based:** when a worker produces a draft, edits a project-local file, completes a test, changes a requirement or closes an issue.
3. **Periodic:** only during a user-authorised, running Foundry session, within assigned time / token / disk / CPU budgets.
4. **Before handoff:** fail closed when critical evidence is absent; publish review findings instead of approval.

Audit state machine: `queued -> collecting -> checking -> findings_ready` or `failed/cancelled/blocked`. Findings do not mutate code. Repair state machine: `proposed -> approved_in_scope -> staged -> tested -> reviewed -> rejected/awaiting_owner_release`.

Every job requires a stable ID, UTC timestamps, spec revision, source snapshot SHA, attempt number, owner/scope, cancellation token, resource cap, heartbeat, status and error. After restart, an interrupted job is marked `interrupted` and reconciled; do not silently report completion or repeat a side effect. Same audit key (project, input hash, rules version) should be idempotent.

For local RTX 3060 12GB systems, schedule model calls sequentially initially and avoid XTTS/LLM VRAM contention. Deterministic rules need no LLM. Use LLM only for explanations and non-authoritative repair suggestions.

## 5. Structured evidence contract

Every worker completion must create a validated evidence envelope. Example (**illustrative, not actual execution**):

```json
{
  "schema_version": 1,
  "project_id": 12,
  "task_id": 42,
  "agent_role": "implementer",
  "attempt": 2,
  "spec_revision": "sha256:...",
  "source_revision": "sha256:...",
  "claimed_status": "review",
  "declared_outputs": [{"path": "service.py", "sha256": "..."}],
  "actual_file_observations": [{"path": "service.py", "sha256": "..."}],
  "test_run_ids": [110],
  "started_at_utc": "2026-11-01T00:00:00Z",
  "finished_at_utc": "2026-11-01T00:01:30Z",
  "duration_ms": 90000,
  "model": "qwen2.5-coder:7b",
  "tool_errors": [],
  "notes_are_untrusted": true
}
```

Important:
- `claimed_status` is an untrusted worker assertion; `actual_file_observations` and `test_run_ids` are collected by trusted Foundry code from disk and test records.
- Persist bounded, schema-validated records in local SQLite outside Git; unique run IDs and foreign keys to actual projects/tasks/tests.
- Record reason codes: `not_run`, `tool_unavailable`, `static_pass`, `unit_pass`, `ui_interaction_pass`, `startup_smoke_pass`, `failed`. These do **not** imply each other.
- Evidence references must be valid, scoped to the project's directory, size-limited and free of symlink/path traversal.
- Keep actual stdout/stderr bounded and redact secrets, credentials, personal data and unnecessary full prompts before export.

Suggested additive tables: `audit_runs`, `audit_findings`, `audit_metrics`, `audit_remediations`; indexes on project/task/status/severity. Do not rewrite existing `events` or `test_runs`.

## 6. Deterministic audit rules (MVP first)

### Evidence and correctness
- Claimed file changes vs actual file list and hashes.
- Claimed passed test vs actual matching test run + exit status + source revision.
- Static-only passes mislabelled as full application tests.
- Unresolved critical issues, skipped acceptance tests, broken dependency DAG or task marked complete while a dependency is blocked.
- Different authoritative stack/framework/spec versions among worker outputs (e.g. React vs approved PySide6).
- Missing or mismatched `foundry.json` UI-to-backend links.

### Cross-agent conflicts
- Two edits to the same path against different base hashes, changed interface signatures or incompatible schema assumptions.
- Tester references a nonexistent function or an outdated source revision.
- Reviewer/integrator approves a different code snapshot from that tested.
- Duplicate task work, mutually exclusive requirements, missing ownership or circular dependencies.
- Two agents contend for exclusive resources (model lock, Docker sandbox, updater) without a queued handoff.
- Ambiguous user requirements => report and request owner decision. Never secretly choose a new authoritative requirement.

### Security, privacy and safety
- Attempted edits outside designated workspace or symlink/path escape; unapproved subprocess/network; unsigned update attempt.
- Secrets/keys/voice data potentially included in a staged artifact.
- No test execution on host for untrusted generated code. Docker unavailable => `blocked: sandbox_unavailable`, with static-only results shown separately.
- Ensure the auditor cannot approve its own release, change its own permissions or erase the evidence ledger.

**Critical rule decisions must be deterministic;** an LLM may suggest additional conflicts but must mark them `unverified` until a checked rule or human confirms them.

## 7. Finding and remediation schema

Each finding must include:
- ID and fingerprint, rule ID / version, project and task/agent refs;
- severity `critical/high/medium/low/info`, state `open/acknowledged/fixing/resolved/rejected`;
- grounded explanation, exact evidence references, confidence and provenance;
- affected files/interfaces and owner, deduplication key;
- suggested minimum remedy, proposed test, expected impact, whether approval is needed;
- resolution evidence: new file hash, test run and reviewer verdict.

Severity policy:
- **Critical:** boundary violation, secret exposure, falsified execution, unsafe generated-code execution, or promotion without approval. Stop affected job and require human review.
- **High:** proven conflicting requirements, failed required test, stale tested source, missing essential deliverable. Block integration, queue a bounded repair suggestion.
- **Medium:** retry loops, missing noncritical documentation/tests, reproducible inefficiency. Prioritise repair when budget allows.
- **Low/Info:** clean-up or speculative improvements. No interruption.

Sentinel may stop only the authorised Foundry task/session it controls under predeclared rules. It cannot change physical devices, finances, sensitive data, system settings or production Apollo automatically.

## 8. Performance and optimisation

Record empirical baselines per machine/model/test suite rather than universal advertised scores:
- Task success on fixed historical cases **and a held-out set**.
- Correctness: real unit, integration, UI interaction and startup smoke results; count separately.
- Time: task duration, model latency, token throughput, queue wait time, retry counts.
- Resources: peak RSS, sampled VRAM if available, GPU scheduling contentions, disk consumption.
- Quality: reopened bugs, dependency conflicts, unreviewed high-severity findings, rollback count.
- Efficiency: tokens/retries per verified task, duplicated context and repeated model calls.

Optimisation experiments must be A/B where practical, repeatable, traceable to the same spec/test snapshot, and labelled with variability. If measurements are missing or inconclusive => **no improvement claim**. Candidate improvements: narrower task contexts, model-role routing, fewer duplicated drafts, early deterministic checks, dependency-aware scheduling and caching validated inputs (never stale results).

Repair loop: **find -> classify -> assign -> stage -> test -> independent re-audit -> benchmark -> owner review**.
Cap retries, tokens, wall time, disk, worker count and total iterations. On exhaustion, stop with a useful blocker report and retained checkpoint. Never optimise by skipping essential tests.

## 9. Foundry user interface

One integrated `Sentinel` tab in Project Studio, using PySide6:
- Summary: `Agents active`, `Audits complete`, `Open critical/high findings`, `Verifications passed`, `Performance vs baseline`. Never invent percentages or scores.
- Agent activity table: role, task, owner, spec version, state, source snapshot, latest evidence, last heartbeat.
- Findings table: severity, type, conflicting agents/files, exact evidence, remediation owner, status, `View Difference`.
- Optimisation view: pre/post benchmark chart, token/time/VRAM data when available, confidence and limitations.
- Controls: **Run Audit**, **Audit Selected**, **Show Evidence**, **Create Repair Tasks**, **Pause**, **Resume**, **Stop**, **Export Report**, **Review Candidate**.
- A visible distinction between *detected*, *suggested*, *staged*, *tested*, *approved* and *released*. No green success badge when Docker/tests did not run.
- Default read-only mode. Opt-in continuous mode inherits Foundry session scope, budget, owner permissions and stop semantics.

Reports export to private workspace by default. Any public issue/PR must be deliberately sanitised and owner-reviewed.

## 10. Implementation work orders for Foundry specialists

**S0: Baseline / integrator (prerequisite)**
- Inspect live project DB, worker stage transitions, exact test records, cancellation behavior and existing permissions.
- Reproduce three existing project scenarios on a safe synthetic fixture; record source/branch and actual test status. Identify whether Docker is available; do not substitute host execution.
- Deliver a baseline report and amended task plan. *Gate:* existing tests and smoke checks documented; regressions are addressed before broad implementation.

**S1: Architect + DB developer**
- Define versioned audit envelope and additive `audit_runs/findings/metrics/remediations` schema. Implement idempotent read-only audits over existing tasks/events/meeting decisions/test runs/source snapshots.
- *Gate:* database migration preserves old data; repeat audit does not duplicate findings; corrupted records fail safely.

**S2: Auditor + reviewer**
- Deterministic evidence checks and severity scoring, source-hash linkage, missing test classification.
- *Gate:* synthetic falsified success and stale test output get flagged; genuine static-only result stays labelled static-only.

**S3: Conflict engineer**
- Requirement and framework lock, file overlap, dependency cycles, old snapshot approvals, interface/signature mismatches.
- *Gate:* injected PySide6/React conflict, duplicate edit and stale reviewer acceptance are caught with file/task references; innocuous parallel changes aren't blocked.

**S4: Benchmark engineer**
- Record end-to-end task correctness and resource measurements. Baselines from real timed runs; compare an optimisation with a held-out evaluation.
- *Gate:* missing/failed measurements report `unknown`; no passing claim without test evidence; no regression masked by faster output.

**S5: Repair coordinator**
- Convert confirmed findings to issue/subtask with owner, dependency, test requirement, retry/resource limits and checkpoint.
- *Gate:* cannot write Apollo core, promote own code, exceed budget or run untrusted code on host; restart/stop preserves findings.

**S6: PySide6 developer + UX reviewer**
- Build Sentinel tab reusing Project Studio, accessible filters and clear audit/evidence/benchmark views. No detached replacement dashboard.
- *Gate:* UI smoke tests, keyboard navigation and no blocking work on the Qt GUI thread.

**S7: Independent tester + integrator**
- Run synthetic conflicts, cancellation/restart, redaction, permission negative tests, 12GB VRAM-contention scenario where available, Docker-missing scenario.
- *Gate:* no critical regressions, all automated checks executed and logged; approval-ready diff, test evidence, rollback plan.

## 11. First minimal vertical slice (build before the full vision)

A working **read-only Sentinel audit** on an existing Foundry project:

1. Select project and click `Run Audit`.
2. Collect its real tasks, issues, dependencies, meetings, file inventory and recorded test runs.
3. Flag at least: no generated source, required tests not run, stale source vs tested hash (where recorded), blocked dependency, contradictory framework claims when evidence permits.
4. Show findings with source references and reason codes in Foundry.
5. Export bounded private JSON audit report.
6. Run the same audit twice without duplicate active findings.
7. Stop/restart and recover the same ledger.

No autonomous repair or background timer in this slice. When it passes, add event-based audit, conflict resolution and measured optimisation in separate PRs.

## 12. Acceptance test matrix (minimum)

1. Empty project: no invented success, explain missing outputs.
2. Generated files but no tests: distinguish syntax/static from functional proof.
3. Test passed on hash A, project now hash B: stale verification alert.
4. Test log `failed` but worker says success: high finding with both references.
5. Architect specifies PySide6 while implementation uses React against locked spec: flag.
6. Two agent edits target same file with diverging base hashes: conflict.
7. Two non-overlapping valid edits: no false file conflict.
8. Dependency cycle/blocked prerequisite: no task completion.
9. Docker missing: state `blocked`, never host-run generated app.
10. Malicious path / symlink, oversized log or embedded prompt injection: no escape or trusted instruction.
11. Duplicate event / audit rerun: deduplicated findings.
12. Pause/restart/resume: no duplicate side effects, evidence retained.
13. Low resource budget / GPU busy: queue or block gracefully, no UI freeze.
14. Candidate is faster but fails a required regression: rejected.
15. Auditor tries to approve/release own patch: permission denied.
16. Sanitisable report: secrets and private user storage never exported.
17. Foundry project UI and existing core regressions still pass.
18. Independent human approval gate survives agent disagreement.

**Evidence requirements:** test command, environment, actual output, exit status, timestamp, source revision and known limitations. Do not report tests as passed without execution.

## 13. Release and recovery contract

- Separate, small PRs with explicit acceptance tests and a changelog.
- No existing `main` modification before review. No automatic merge, signed release, installer run or production updates.
- Backup user data/migrate database additively, support rollback; keep models, XTTS voices and memories outside release payloads.
- Preserve existing Foundry sandbox policy and user-approved scopes. Unknown test state blocks trust claims.
- Make conditional/continuous audits durable only after a shared JobController exists with recovery and cancellation.
- User controls final approval for production changes and sensitive actions.

## 14. Instructions to Apollo Foundry Manager

Treat this document as the *authoritative feature specification* **once the owner approves it**. Start with S0 and S1, not an all-at-once autonomous rewrite. Create task IDs with dependency edges. Delegate to existing roles (architect, implementer, tester, reviewer, integrator); add Sentinel audit roles as logical worker profiles once validated, not concurrent resource-heavy processes by default.

At each handoff output: actual modified files + hashes, exact observed tests, unresolved findings, next smallest bounded task, and permission/release state. Ask for owner approval when authority is required. If a test cannot run, explicitly say `not_run`. Do not assert success based on agent conversation or a meeting.

**Exit definition:** Sentinel can detect and document injected cross-agent faults from real records, guide a reviewable project-local repair, independently verify its effects, compare it with a baseline, recover after an interruption and leave live Apollo unchanged until human approval.
