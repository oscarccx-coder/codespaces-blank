# Apollo: Chase AI and ECC feature plan and delivery map

Owner request: plan and implement useful features from both Chase AI and Everything Claude Code, then publish a ready Apollo update. This native, local-first implementation builds on existing Apollo services. ECC itself is not installed; paid course contents are not copied.

Public sources reviewed:
- https://chaseai.io/blog/how-to-build-an-agentic-os-claude-os
- https://chaseai.io/blog/loop-engineering-four-phase-process
- https://chaseai.io/masterclass
- https://ecc.tools/
- https://github.com/affaan-m/ECC

## Feature and acceptance plan

| ID | Feature | Delivered behavior and acceptance criteria |
|---|---|---|
| W01 | Knowledge layers | A memory map identifies original source receipts, searchable topic knowledge, finished outputs and work state. Keep URLs, source IDs and uncertainty; do not silently promote notes into trusted facts. |
| W02 | Reusable workflows | Versioned registry: public research brief, saved-knowledge brief, Foundry assessment, local application benchmark and configuration audit. An owner can name and reuse a reviewed recurring procedure. |
| W03 | Graph execution | Explicit specialist roles, stages and dependencies. Durable runner commits one allowlisted stage at a time; no arbitrary shell commands or model-chosen operations. At most eight stages per registered graph. |
| W04 | Pause, stop and recovery | Persist state, attempts, failures and partial outputs with expiring leases. Pause/stop prevents the next stage; current work can finish. Restart never replays a committed stage. Failed stages require an owner retry. |
| W05 | Operational dashboard | Show current stage, roles, dependencies, attempt counts, wall times, last activity, blockers, handoffs and actual report outputs. No fabricated worker activity or test results. |
| W06 | Persistent handoffs | Commit an output receipt hash, factual summary and next action after each stage. Include existing project-scoped Foundry handoffs in fresh worker and meeting contexts as untrusted reference data. |
| W07 | Reviewed procedural learning | Two completed runs with passing narrow contract checks propose a reusable procedure. Show supporting run IDs and failed stage attempts. Only the owner approves/promotes or revokes it. No self-approval by the model. |
| W08 | Context management | Bound receipts and model inputs; retrieve relevant memory rather than dumping global chat. Reject oversized inputs, retain provenance and preserve the selected model. No automatic cloud escalation. |
| W09 | Topic progress map | Aggregate observed practice results into topics, concepts, weak areas and suggested review dates. Show cloze and application results separately. Counts do not establish broad intelligence or mastery. |
| W10 | Application practice | Fresh parameterised workload, numeric and source-independence problems. Withhold the answer key from the local model and grade deterministically. Preserve a grounded lesson if the extra application call fails. |
| W11 | Independent checks | Match research quotations against fetched text, check citation IDs against retrieved memories, independently grade benchmark answers, and inspect actual Foundry checks/source-matched Docker history. A model opinion cannot grant test/release approval. |
| W12 | Routing and configuration audit | Optional Auto chat mode routes explicit research/coding requests through existing guarded paths while respecting Tools and temporary-chat boundaries. Read-only configuration audit redacts credentials and reports registered high-risk grants; it does not change permissions. |

## Workflow contracts

1. **Public research brief:** fetch up to three public pages → local source-linked study/cloze recall → deterministic exact-quotation check → report and optional selected-node indexing. Public web authorisation is explicit per run; private conversation history is not added to web queries.
2. **Saved-knowledge brief:** retrieve up to four topic memories within 5000 characters → local synthesis → citation-ID check → report. Source references remain unverified; identifier checks are not semantic verification.
3. **Foundry assessment:** read actual project/task/issue state → existing non-executing static inspection and source-matched Docker history → report/handoff. No generated code or tests run, no project is approved, and no release is published by this workflow.
4. **Application benchmark:** prepare four fresh questions → local answers without the key → independent exact/numeric grading → durable report. This is a narrow benchmark rather than topic expertise or model training.
5. **Configuration audit:** inspect allowlisted settings and registered permission metadata → redacted findings → report. No secrets are printed and no configuration is changed. This is not a full AgentShield implementation or a safety guarantee.

## Existing systems reused

- Knowledge Nodes and Memory Bank organise and recall notes.
- Training retains full original page receipts.
- Learning Missions retain continuous-until-stop operation, budgets, duplicate suppression, leases and memory retry.
- Foundry retains specialist workers, sandbox controls, owner reviews, source-matched tests, checkpoints and rollback.
- Chat retains scoped conversations/projects, attachments, Tools/temporary boundaries and selected-model behavior.

The new Workflows & Learning app connects these systems; it is not a replacement for their established permission gates.

## Execution and privacy

Only owner controls or exact newest-user commands start runs. Model tools are read-only: registry, runs, status/handoffs, procedures, memory map, curriculum and route preview. No model can add executable stages, grant permissions or promote a procedure.

Runs are finite, with at most twelve active/paused jobs, one stage at a time per worker and ten-minute expiring run leases. Each local workflow model call has a 90-second deadline. The selected loopback Ollama endpoint/model remains authoritative; external endpoints and cloud-labelled models are refused. Context and receipt sizes are bounded. Source and memory text remain untrusted data.

Continuous study continues through the existing Practice app, rather than introducing a competing scheduler. It now makes a third model call for fresh application problems within its existing shared 120-second deadline. Its 24-batches-per-mission UTC daily budget remains in effect. Weak application skills can guide later topic-anchored queries.

Runtime data stays under `storage`, outside tracked code. Existing databases/preferences are preserved. Reusable procedures wrap known versioned graphs; they are not arbitrary generated executable skills or permission grants. No weights are retrained, software auto-installed, purchases made, or physical systems controlled.

## Validation and release checklist

- [x] Pure contracts: dependency ordering, invalid graphs, malformed receipts, quote/citation checks, independent scoring and redacted audit output.
- [x] Durable integration: actual SQLite state, cross-worker leases, pause/stop during a stage, restart recovery without replay and failed-stage retry.
- [x] Real Memory Bank and Foundry integration: node routing, stable report/memory identifiers, source-scoped handoffs and no code execution/approval by assessments.
- [x] Actual Qt controls: start/control/inspect a run, choose a memory destination and approve/revoke a procedure through owner UI.
- [x] Existing chat/practice/knowledge/Foundry/updater regressions; source health and package checks.
- [ ] Linux, Windows, Docker and Raspberry Pi CI on the exact final commit before merge.

Status and exact validation are recorded in the pull request. Fixture tests do not benchmark live Ollama reasoning quality or establish ChatGPT feature parity. The owner guide is [Workflows & Learning](APOLLO_WORKFLOWS_AND_LEARNING.md).

The W01–W12 implementation is included in this update. External ECC adapters, a general plugin marketplace, paid-provider account integration, unrestricted skill generation and autonomous production releases remain outside this scope.
