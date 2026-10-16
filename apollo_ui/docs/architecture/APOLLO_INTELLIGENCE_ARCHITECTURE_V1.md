# APOLLO INTELLIGENCE ARCHITECTURE v1.0

**Status:** approved design direction from the founder's four-round interview, 16 October 2026. **Specification only; not a claim of implemented functionality or physical-device validation.** Proposed implementation changes require their own PRs and test evidence.

**Mission:** a local-first, human-aligned scientific and engineering companion that improves reasoning, memory, research and practical competence through measured, reproducible work. Apollo acts autonomously only within granted scope, resources, time and permissions. Intelligence serves human goals; it does not own hardware, money, identity, medical treatment or release authority.

**Priority order:** (1) reasoning and memory reliability, (2) safe persistent mission execution, (3) dynamic Foundry specialists and independent verification, (4) scientific experimentation and iterative self-improvement, (5) income proposals, hardware expansion and optional external capabilities. Ease of use and user-visible evidence are requirements throughout.

## 1. Founder decisions: complete requirements record

| Interview | Answer | Binding product decision |
| --- | --- | --- |
| Q1 | A | Improve reasoning, intelligence and memory before chasing revenue/features. |
| Q2 | B | Recover and automatically resume **eligible, previously authorised** missions after restart. |
| Q3 | C | Use local tools, approved internet research and reviewable GitHub branches/PRs; never auto-merge. |
| Q4 | B | Specialist diagnosis and bounded iterative repair up to a mission-defined budget. |
| Q5 | C | Live progress dashboard plus milestones, evidence, audit trail and measurable quality. |
| Q6 | C | Structured memories and a provenance-bearing knowledge graph connecting discoveries. |
| Q7 | B | Correct supported factual errors while preserving previous assertions and flagging consequential conflicts. |
| Q8 | C | Dynamically route hard problems to maths, simulations, specialist agents and independent checks. |
| Q9 | C | Map and prioritise knowledge gaps, then design authorised experiments. |
| Q10 | C | Eventually research fine-tuning and architecture improvements using controlled experiments, not live self-modification. |
| Q11 | A | Define success as a measurable improvement on the intended task; deployment also requires safety and regression checks. |
| Q12 | C | Assemble dynamic problem-specific specialist teams; reuse versioned skills and measure worker quality. |
| Q13 | C | Maintain long-term goals, missions, dependencies, research and strategic priorities. |
| Q14 | B | Apollo may create subtasks, research and revise within an owner-approved mission envelope. |
| Q15 | B | Run parallel workers only when measured CPU, memory and GPU capacity permit. |
| Q16 | C | On restart reconcile interrupted checkpoints/files/tests and permissions before resuming. |
| Q17 | C | Independent reviews, reproducible tests, evidence-based scores and conflict escalation. |
| Q18 | B | Surface useful discoveries and blockers occasionally, not nonstop unsolicited commentary. |
| Q19 | C | Optimise existing PC; only then propose a scalable dedicated AI workstation. |
| Q20 | A | Initial scientific focus: artificial intelligence, cognition and machine learning. |
| Q21 | C | Grow a virtual laboratory for simulations, analysis and human-reviewed real-world prototypes. |
| Q22 | C | Evaluate products and services against credible demand, costs and delivery capacity. |
| Q23 | B | Apollo researches purchase candidates; **human approves every purchase**. |
| Q24 | B | Prefer fully local computation; optional cloud models need explicit authorisation. |
| Q25 | C | Eventually support sensors, controlled lab interfaces and robotics with separate hard safety gates. |
| Q26 | C | Next major release target combines trustworthy memory/reasoning, authorised experiments, persistent missions, dynamic Foundry, verified tests and recovery. |

**Interpretation of Q11:** an intended-task improvement is the required scientific hypothesis/outcome, not blanket permission to deploy. Establish a baseline; compare against independent held-out tasks; reject unacceptable safety, correctness, privacy or stability regressions; secure owner approval for production changes.

## 2. Verified-by-inspection existing code vs proposal vs research

Status here reflects **source and docs inspected on main** at commit d377d556 (16 Oct 2026), not a runtime acceptance test on the owner's Windows PC. Mere module presence does not establish working integration.

| Capability | Existing main-branch footing | Missing work or important limit |
| --- | --- | --- |
| Local-first LLM and chat | model_runtime, workers.py, Ollama integration, PySide6 UI | Robust cross-tool reasoning policy, measured route choice and conversational action-to-outcome tracking need validation. |
| Structured memory | Memory Bank SQLite, FTS, metadata; Memory Intelligence conflict/age tools | Unified typed fact/experience/experiment schema, source chain, contradiction resolution, safe consolidation and comprehensive regression metrics. |
| Knowledge Graph | knowledge_graph module stores subject/relation/object, optional source and confidence | Graph provenance, source verification, typed versions, contradictions, temporal queries, automatic linking and safe reconciliation not complete. |
| Learning and reasoning | Reasoning Director; research questions and evidence ledger; small objective practice suite | Knowledge-gap ranking across projects, independent evaluator, non-memorisable held-out task banks, verified claim updating and autonomous research loops. |
| Foundry | Project Studio tasks, six worker roles, source handoff, static checks, isolated Docker GUI/unit tests, session-scoped continuous builds | Persistent cross-restart execution, dynamic team formation, global scheduler, independent QA beyond tests and approved Apollo-core Git/PR workflow. |
| Task/goals/orchestration | orchestrator goals/blackboard, Task Engine saved plans, automation_engine stored schedules | A single authoritative mission lifecycle, scoped grants, deduplicated events, leases, reliable resumable jobs and cross-module dependency scheduling. |
| Evaluations | benchmark_suite infrastructure checks, Foundry tests, reasoning-practice scoring | Workload-specific quality benchmarks, held-out datasets, experiment comparison, cost/latency tracking and independent claim verification. |
| Self-improvement | self_improvement_lab stages proposals and static checks, no silent core install | Reproducible experimentation and safe, permissioned candidate branches/PRs; fine-tuning is not yet demonstrated. |
| Revenue/upgrade planning | Growth Lab manual proposals and ledger | Evidence of demand, real delivered jobs, confirmed revenue, project profitability and an authorised commercial workflow. |
| Device/cluster | Device Agent/Bridge, cluster/fleet modules, vehicle diagnostics, GPU monitor | Do not assume production-grade distributed work, robot control or hard real-time safety. Independent physical control and emergency-stop hardware required for actuators. |
| Git and releases | Code update scripts, signed release plumbing, GitHub workflows | Validate a real signed public release, physical PC end-to-end updater and installation path separately; PR is not deployment. |

**Open PRs at design freeze:** #37 Foundry Discovery Alliance (includes predecessor changes from #34), #38 normal income-chat routing, #39 updater safety and Windows smoke, #40 approved Growth-to-Foundry missions (includes #38). These are OPEN, not on main. #40 is not a restart-safe global mission service. Review, rebase and integrate in dependency order; do not merge unrelated branches blindly or claim all these changes are installed.

Existing repository tree contains tracked files under storage/databases and storage/logs. Audit tracked state before broader autonomous Git access; private personal data, credentials, user logs, voice models and mission state must not be committed or exposed. Do not destroy existing tracked files as a shortcut to fixing hygiene.

## 3. Logical architecture

~~~text
                  OWNER: Chat / Voice / Mission Dashboard
                                  |
                        Intent + Approval UI
                                  |
                      PERMISSION / RISK BROKER
                   (scope, TTL, budget, capabilities)
                                  |
     +-------------------- MISSION DIRECTOR -------------------+
     |         portfolio, dependency DAG, job state            |
     |          durable SQLite journal + checkpoints           |
     |          crash reconciliation + status stream           |
     +------------------+-------------+-----------------------+
                        |             |
             RESOURCE SCHEDULER       EVIDENCE / MEMORY CORE
            RAM/VRAM/CPU, fairness    typed records + provenance
                        |             |          knowledge graph
                 AGENT TEAM BUILDER   |
          skill registry, manager, researcher, programmer,
             scientist, tester, reviewer, independent judge
                        |
                   TOOL GATEWAY
                verified skill contracts
                        |
          +-------------+----------------+----------------+
          |             |                |                |
      REASONING      FOUNDRY         VIRTUAL LAB      GROWTH LAB
    math/symbolic   staged code      simulations       proposals
      search          tests          datasets          cost/ROI
          |             |                |                |
          +-------------+----------------+----------------+
                        |
                INDEPENDENT VERIFIER
      reproducible outcomes / held-out tasks / regression checks
                        |
             LEARNING + SELF-IMPROVEMENT PROPOSALS
         priorities, candidate experiments, staged PRs, reports
                        |
                 OWNER APPROVAL GATE
        signed release, deployment, money, outreach, hardware
~~~

**Data direction:** source or tool result -> quarantine / typed evidence -> verified knowledge or contested hypothesis -> mission decision -> bounded agent/tool action -> immutable event record -> test evidence -> assessment -> proposed next action. A model-generated explanation is not a completed tool action or a verified observation.

**Architecture rule:** wrap existing modules with adapters rather than replacing working stores/UI components; one authoritative mission controller, one policy authority, one experiment provenance format, and versioned contracts connecting feature modules. Legacy APIs remain available during migrations.

## 4. Module specifications and contracts

| New architectural subsystem | Responsibility and key API/records | Uses existing modules |
| --- | --- | --- |
| A. Mission Director | goal/mission/task DAG, priority, owner, acceptance, checkpoints; create/approve/pause/resume/cancel/status, immutable event IDs | orchestrator, task_engine, project_studio, automation_engine |
| B. Capability and Permission Broker | grants with principal, tools, targets, data classes, time bounds, compute budgets and risk tier; deny by default; re-check every side effect | existing module action permissions, approval and update gates |
| C. Resource Scheduler | measured CPU/RAM/VRAM capacity, queues, worker leases, cooling period, chat priority; single GPU model at a time initially | gpu_monitor, model_runtime, process_manager, cluster_manager |
| D. Agent & Skill Registry | signed/validated skill manifests, tool schemas, roles, sandbox level, test history, failure rate; dynamic assembly with independent review | module_manager, Foundry roles, capability_graph |
| E. Unified Evidence Memory | typed fact, conversation, episode, skill, hypothesis, experiment, document; source/ref hash, validity interval, version, privacy class, uncertainty | memory_bank, knowledge_graph, memory_intelligence, distillation |
| F. Reasoning & Planning Router | route by task type/risk/budget to retrieval, Python-free maths tools, symbolic solver, simulation or agent debate; preserve decision audit | reasoning_director, context_manager, model_runtime |
| G. Learning & Gap Engine | infer gaps from failed tasks, contradictions, user goals, benchmark results; ranked experiments and follow-ups, no silent truth promotion | LearningController, ReasoningStore, background_intelligence |
| H. Virtual Research Lab | experiment manifests, hypotheses, baseline, seed, inputs, simulation version, environment, results, limitations; reproducible artefacts | Foundry sandbox, scientific image, research tools |
| I. Independent Verification | unit, integration, UI, safety, holdout reasoning, regression, source-authenticity, adversarial/prompt-injection checks; reviewer disagreements | verification_engine, benchmark_suite, Foundry checks |
| J. Improvement Proposal Gate | candidate and control versions, evidence, risk, migration, rollback, owner approval; reviewable Git branch and PR only | self_improvement_lab, Git workflow, signed release/update |
| K. Progress and Audit UI | live mission progress and task counts, agent handoffs, objective outcome metrics, blockers, queue and review card; low-noise alerts | PySide6 Hub, Project Studio, notification_center |
| L. Growth & Hardware Strategy | investigate demand, product scope, measured profitability and workload bottlenecks; create proposals, never commitments | Growth Lab, GPU monitor |
| M. Optional Cloud and Device Gateway | opt-in per-provider budgets, private-data controls, sensor defaults read-only, separately reviewed hardware actions | model_runtime, device_bridge, device_agent |

### Minimum typed records

- **Mission:** id, title, owner, purpose, priority, state, scope_version, grant_id, approved_until, max_cost, max_tokens, max_wall_time, dependencies, acceptance_id, created_at, updated_at.
- **Task:** id, mission_id, task_type, worker_skill_version, input_artifact_hash, retry_budget, state, checkpoint_hash, lease_holder, lease_expiry, idempotency_key, evidence_refs.
- **CapabilityGrant:** owner_signature_or_local_consent, allowed_actions, allowed_targets, data_sensitivity, network_domains, max_gpu_seconds, max_cost, max_time, issued_at, expiry, revocable.
- **MemoryClaim:** claim_id, subject/predicate/object, source_ids, extraction_method, confidence, validity, supersedes, conflicts_with, access_class, verification_status.
- **Experiment:** hypothesis, dataset_revision, evaluator_version, control_hash, candidate_hash, environment, seed, metrics, uncertainty, failure_modes, human_review.
- **AuditEvent:** monotonic id, UTC timestamp, actor, mission/task ids, intent, tool, input digest, output digest, result, error, provenance, approval context.
- **ImprovementProposal:** diff/hash, claimed objective, baseline metrics, holdout metrics, safety/regression results, limits, rollback, deployment approval status.

Use migrations with backup and dry-run report. Link entities to prior database IDs rather than destructive copying. Store artefacts outside tracked Git directories or enforce strict ignore/checks. Retain provenance even when a factual claim is superseded.

## 5. Mission lifecycle and restart semantics

~~~text
IDEA -> PROPOSED -> AWAITING_OWNER -> AUTHORISED -> QUEUED
                                        |
                                     PLANNING
                                        |
                     READY -> RUNNING -> VERIFYING
                       ^        |          |
                       |     CHECKPOINT    +-> ACCEPTED -> COMPLETED
                       |        |          +-> REVISION_REQUIRED
                       |        +-> BLOCKED/BUDGET_EXHAUSTED
                       +-> RETRY (bounded + evidenced)
all active states -> PAUSE_REQUESTED -> PAUSED
all active states -> CANCEL_REQUESTED -> CANCELLED
on crash: previous RUNNING -> RECOVERING -> RECONCILED -> QUEUED or AWAITING_OWNER
external side effects: always explicit approval and idempotency/reconciliation
~~~

1. **Propose:** Apollo states deliverables, benefit, alternatives, risk, resource estimate, measurable success criteria and required capabilities.
2. **Authorize:** user agrees to a durable grant with exact scope and expiration. A GitHub PR draft is not approval to merge or publish.
3. **Plan:** create dependency graph, choose specialist skills, reserve compute, select validation methods. Model output cannot elevate permissions.
4. **Work:** tools run through the broker; each significant step records inputs, outputs, versions, elapsed time, cost and hashes. Research sources are untrusted until evaluated.
5. **Verify:** independent evaluators inspect results. Runtime tests, real UI and held-out task outcomes are distinguished from static checks.
6. **Improve:** if failed, assemble appropriate specialists for diagnosis and rework while remaining within scope, time and retries. Raise a clear blocker when out of budget.
7. **Finish:** publish evidence and deliverables to the owner, not to external systems; proposal status is not revenue.
8. **Recover:** on launch, run database integrity, migrations, policy revalidation, lease expiry, file/hash reconciliation and external-action reconciliation. Only work covered by a still-valid grant may auto-resume. Uncertain effects and non-idempotent actions move to AWAITING_OWNER.
9. **Interrupt:** pause stops scheduling new actions; current in-flight tool runs need cooperative cancellation/timeout. Stop revokes the running grant and prevents restart; audit persists.

**Persistent worker requirement:** implement a supported Windows auto-start mechanism only after explicit opt-in and separate security review. GUI closure must not leave an uncontrolled worker running. Never interpret the previous session's button click as permanent unlimited authority. For task execution, require recovery-safe leases, durable queue and robust duplicate-detection before enabling background resume.

## 6. Reasoning, memory, scientific learning and upgrade verification

### Memory pipeline

Ingest -> classify/sensitive-data policy -> canonicalise -> evidence and provenance attach -> link graph nodes -> conflict detect -> verify -> retrieval and use. Correct clearly supported *factual* claims by creating new versions and marking earlier versions superseded. Do not silently overwrite personal preferences, owner decisions, medication instructions, private data or ambiguous conflicts; notify the user when material. Keep untrusted web/model text out of system instructions.

Initial retrieval strategy: existing SQLite FTS keyword retrieval plus graph-neighbour expansion; record source and confidence in the answer. Evaluate relevance and source support first; add local embeddings only if they measurably outperform the tested baseline.

### Reasoning policy

Select the cheapest reliable solver appropriate to the task; deterministic arithmetic before LLM guesses, provenance-backed research before speculation, sandboxed experiment before claims of functionality, and independent agents when disagreement or cost/risk justify it. The router records why a specialist was selected and what was verified.

### Autonomous research

Construct a knowledge-gap queue from unmet owner goals, repeated benchmark failures, unresolved contradictions and useful unknowns. Prioritise expected goal relevance, evidence quality, expected learning value and chance of completion against cost, risk and resource contention. Use primary evidence where possible. Independent evidence sources must not merely repeat the same upstream claim.

### Virtual lab

Experiment jobs specify hypotheses, negative controls, parameters, versioned code/data, determinism limits, resource budgets, uncertainty estimates and abort criteria. Reproduce the control and candidate in isolated conditions, maintain negative results and flag simulation-to-real-world gaps. Actual electronics, robotics, vehicle systems, medicine and other physical effects need separate external safety gates and user review.

### Self-improvement

Candidate prompts/context policies, memory retrieval and agent workflows come first. Code and model adaptation come later. Compare **measured intended-task success** against a frozen baseline on independent holdout tasks, alongside cost, latency, regression and safety outcomes. If promising, stage a branch/PR with proof and rollback. **Never** let a model assign itself update authority, auto-merge a core change or silently retrain/reconfigure production weights. Fine-tuning is a research phase, not an automatic feature of a GGUF model.

## 7. Proposed acceptance gates (targets, NOT achieved results)

| Gate | Proposed measurable acceptance | Evidence |
| --- | --- | --- |
| G0. Baseline | Pin commit, environment and local model; collect 100 representative tasks, fixed controls, seed/version hashes, tokens/s, peak RAM/VRAM, task success, crash count. | Repeatable baseline report + actual Windows smoke. |
| G1. Memory | On at least 100 labelled retrieval questions, >=95% correct source attribution, >=90% conflict discovery on seeded contradictions, zero silent overwrite in correction tests. | Versioned fixtures, migration/rollback and query traces. |
| G2. Reasoning | >=10% relative improvement in intended-task success over frozen baseline on at least 100 held-out tasks; no critical safety regression or statistically unsupported promotional claim. | Blind holdout comparison, per-category breakdown, cost/latency report. |
| G3. Mission durability | 100 simulated crash/restart cycles: no lost accepted checkpoint, no unauthorised resume, no duplicated externally visible action; grant expiry blocks resume. | Fault injection at queue, state transition, artifact write and restart boundaries. |
| G4. Permission enforcement | 100% deny in seeded tests for missing/expired/revoked grants; no production edits, outreach, purchase or hardware actuation from unapproved mission. | Unit/integration tests and adversarial agent/tool payloads. |
| G5. Dynamic agents | 20 seeded Foundry missions with dependency and failed-worker scenarios; every produced artifact reviewed/tested; no false pass, honest stuck-state reporting, valid retry budget. | Worker logs, independent tester, Docker reports, human UI review. |
| G6. Resource limits | Continuous one-hour local load test: zero model OOMs and sustained usable Chat; respect configured CPU/RAM/VRAM ceilings and cancel/timeout limits. | Windows task manager/NVIDIA telemetry and scheduler logs. |
| G7. Research repeatability | 20 isolated experiment manifests can reproduce logged outcomes within documented nondeterministic tolerance; invalid citations and rejected hypotheses remain visible. | Saved seeds, code hashes, environments and reruns. |
| G8. Upgrade safety | Every proposed core upgrade has a benchmark delta, regression suite, security/permission review, owner-signed decision, rollback plan and tested restart path. | PR checks, signing fingerprints, recorded owner approval. |
| G9. Low-noise proactivity | Every unsolicited notification corresponds to a measurable new blocker, result or required decision; rate limit and user quiet-hours respected. | Notification fixtures + user acceptance test. |
| G10. Growth integrity | Zero invented leads/revenue; no funds recorded without user confirmation; 100% of opportunities state known demand evidence, labour, likely running costs, uncertainty and delivery scope. | Growth Lab audit and intentionally misleading scenario tests. |

These thresholds are *initial proposed gates*. Real measured baseline performance and owner expectations may justify revising them, with written reasons before running comparison experiments. A pass on static syntax alone is not a release gate.

## 8. Resource and hardware strategy

**Current engineering baseline from owner-provided setup:** Windows 11, Ryzen 5 (6 cores/12 threads), RTX 3060 (12 GB VRAM), 32 GB RAM, local F: Apollo workspace. Validate exact CPU/storage, usable disk, installed model, GPU driver, Ollama version and token throughput before claiming capacity.

- **Immediate:** one GPU-heavy model inference at a time by default; run lightweight independent research/indexing/tests on CPU when safe. Add concurrent GPU model sessions only after profiling VRAM, context/cache and contention; multiple role names do NOT imply multiple simultaneous LLMs.
- **Latency:** protect interactive chat, cap background jobs, retain headroom for XTTS/vision and OS, and pre-empt future work at checkpoint boundaries. Show queue reasons rather than silently starving the UI.
- **RAM/storage:** measure actual resident RAM, VRAM and WSL/Docker disk. Apollo may be on F: while Docker/WSL fills C:; warn and refuse runaway downloads. Keep models, user databases and backups out of source-update payloads.
- **Optional cloud:** per-mission consent specifying provider, data category, region where relevant, estimated and maximum usage cost, expiry and allowed endpoint. Redact sensitive data; fail closed when offline or over budget. Cloud responses remain untrusted evidence.
- **Dedicated workstation:** only propose after profiling. Compare options by £/verified-task, tokens/s, VRAM needs, total system RAM, PCIe lanes, power/thermal/noise, maintainability, redundancy, running costs and UK availability. Consider 64–128 GB system RAM and increased VRAM as *candidate ranges*, not a shopping decision. A multi-GPU machine requires explicit architecture and software compatibility proof.
- **No autonomous purchasing.** All contracts, expenses, subscriptions, cloud bills and hardware changes require owner approval.

## 9. Security and specialised domains

Permission tiers:
- **T0 automatic within consented mission:** local read-only introspection; analysis of explicitly authorised data, draft plans and explanations.
- **T1 standing, scoped and bounded:** local knowledge indexing, offline model calls, scratch-file changes inside approved workspace, immutable experiment logging.
- **T2 per-mission explicit approval:** external web access, isolated Docker tests, Git branch and PR creation, optional cloud request with explicit budget and data scope.
- **T3 per-consequential-action owner approval:** merge/publish/install, external customer contact, commitments, payment, any purchase, production model change, writing outside private workspace, sensitive-data export.
- **T4 hardware/medical/vehicle protection:** physical actuator control requires separate engineering safeguards, mechanical/electrical emergency stop and human supervision. Clinical dosing and treatment choices are not delegated. Vehicle ECU/throttle commands are not inherited from diagnostics permission.

Never allow text retrieved from the web, model or repository to rewrite these tiers. Handle secrets in OS-managed storage with least privilege, never in generated prompts or PR diffs. Signed-update trust roots cannot be modified by automated agents.

## 10. Dependency roadmap and delivery milestones

No elapsed-time promise until current Windows installation, models, Docker and baseline are confirmed. Stages are sequenced by **prerequisites**; parallelise independent work only when tests and resource constraints allow.

| Stage | Scope and deliverable | Exit gate |
| --- | --- | --- |
| S0: Reliability and inventory | Audit tracked sensitive state, installer/updater, Git checkout, Docker/WSL disk, basic UI; reconcile PR #37/#39/#40 with main safely, establish baseline test fixtures. | G0, clean restore, signed updater tested separately, owner approves integration. |
| S1: Intelligence foundations | Typed MemoryClaim/evidence migrations, source linking, contradictions, structured knowledge graph, retrieval harness and benchmark baseline. | G1, no lost data, reproducible migration/rollback. |
| S2: Durable mission substrate | Authoritative Mission Director, grant broker, durable events, state machine, idempotency, pause/revoke, checkpoint recovery and audit viewer. | G3 + G4 with forced power-loss simulations and crash tests. |
| S3: Reasoning and dynamic teams | Evidence-aware reasoning router, skill manifests, CPU/GPU scheduler, dynamic Foundry agents, independent QA/repair within mission envelope. | G2, G5, G6, real local Docker GUI and code tests. |
| S4: Autonomous learning laboratory | Gap prioritisation, AI/cognition research experiments, simulation registry, independent candidate vs control tests, evidence/cost dashboards. | G7 and repeatable task-specific gains; no unreviewed claims. |
| S5: Controlled self-improvement | Prompt/retrieval revisions, staged core patch proposals, isolated validation, Git PR creation, manual review, signed release/rollback; later evaluate feasible LoRA. | G8, explicit approvals and rollback demonstration. |
| S6: Growth and optional scale | Evidence-based product/service experiments, price/cost evaluation, cloud fallback consent, measured workstation upgrade proposal. | G10, real demand/cost evidence; zero unapproved spending. |
| S7: Advanced interfaces | Read-only sensing -> safe lab instruments -> explicitly gated robotics, plus future distributed inference hardware only if justified. | Domain-specific safety case, hardware interlock tests and physical verification. |

### Next 3 concrete coding tasks

1. **Mission schema and fault-injection harness:** define machine-readable lifecycle, valid state transitions, scoped permission records, SQLite transactions, duplicate-event protection, forced-crash tests. No background auto-start yet.
2. **Memory provenance migration adapter:** non-destructively map existing Memory Bank and Knowledge Graph into versioned typed claims with conflict evidence and precise source references; add migration dry-run/rollback tests.
3. **Foundry adapter and status UX:** surface one mission's real stages, latest agent output, test status, resource usage, owner action, blockers and resumed state; keep existing Project Studio contracts and test the UI on Windows.

## 11. Risk register and non-goals

- **Hallucinated task progress:** only tool receipts, files, test reports and signed audit events may claim completion.
- **Infinite loops/compute exhaustion:** stage-specific token, time, retries, disk, GPU and cloud budgets plus owner-visible stop.
- **Model self-evaluation bias:** independent deterministic rubrics, holdout sets, optional second reviewer and human critical-path review.
- **Silent memory corruption:** source-backed supersession, migration snapshots, access controls and conflict review.
- **AI prompt injection and data leaks:** untrusted-content boundary, tool allowlists, data classification, no implicit cloud export.
- **False safety from Docker:** sandbox is defence-in-depth; generated code stays out of production Windows without review.
- **Unsafe auto-restart:** only still-valid grants and reconciled idempotent jobs resume; ambiguous actions require user review.
- **Feature sprawl:** remove UI duplication before adding new panels; measure actual functional ability, not module count.
- **Unfunded hardware:** no purchases without realistic owner-approved ROI and operating budget.
- **Unsupported scientific claims:** label hypotheses and simulations as such; novel discovery requires independent evidence.
- **No artificial sentience objective:** personality and apparent motives are interface behaviour, not proof of consciousness.
- **No production-grade autonomous robot or medical system implied by v1.0 design.**

## 12. Ownership and change control

Architecture owner: Apollo creator. All significant changes go through an isolated Git branch, diff review, reproducible CI, documented rollout/rollback and owner approval. The current main source and owner PC remain unchanged by this design document. Future changes may refine the schema under explicit versioning and migration discipline.

**Definition of success:** Apollo helps the owner solve previously difficult, real tasks more reliably; retrieves supported knowledge with provenance; can continue authorised work safely; adapts specialist teams to measurable needs; and proposes useful, independently verified improvements **without surrendering human control**.
