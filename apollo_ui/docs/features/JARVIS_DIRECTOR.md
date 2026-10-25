# Apollo JARVIS Director: local-first engineering autonomy

**Status:** candidate feature branch, not an installed or released update.

## What it actually does
Apollo's JARVIS Director coordinates bounded specialist drafts through the existing local `apollo_project_workers` Ollama backend. The owner starts a mission from an Apollo App. Apollo then asks its local planning model to break the objective into up to eight specialist tasks. Roles are Foundry's manager/architect/implementer/tester/reviewer/integrator contracts. If a plan omits essential engineering roles, a documented deterministic fallback is used.

Each specialist receives the approved mission objective, relevant allowlisted public source excerpts, and short previous draft summaries. The local model performs one call at a time. Results persist in `storage/databases/apollo_jarvis.db`, survive Apollo restarts, and are displayed in the App mission console. Generated implementation files are checked for path traversal and basic Python/JSON syntax, then written under `workspace/jarvis_director/mission_*/task_*/candidate/`, accompanied by a SHA-256 manifest.

**Drafted is not tested.** JARVIS does not run or import generated code, execute arbitrary shell commands, merge branches, patch Apollo core, bypass module permissions, or install production updates. It is a useful local coding and reasoning team, not a fully production-safe self-modifying AI. Real execution and regression testing remain with owner-approved Foundry sandbox and human release gates.

## Goals and workflow
The default mission focuses on the Windows installer/updater, Foundry handoffs, durable mission state, measurable reasoning and memory, source evidence, voice reliability and usable PySide6 interfaces. The owner may replace the objective with a specific brief. Improvements require measured evidence, testable hypotheses and counterexamples, not optimistic agent self-grading.

1. After tests and owner-approved merge, open **Apps → JARVIS Director**.
2. Enter a mission title and objective; select **one cycle** or **continue until stopped or budget exhausted**.
3. Set maximum Ollama calls (2–60) and spacing (30–3600 seconds), then explicitly confirm starting.
4. Review agent notes, staged source and event history. Pause, resume, stop or request the next step. An in-flight call may finish and checkpoint when stopping.
5. Inspect files in Workspace. Transfer appropriate candidates into owner-approved Foundry sandbox testing only after code review. Never run untrusted generated files directly.
6. Compare test results and release readiness in Foundry and the normal updater before approving any integration.

## Guarantees and limits
- Local Ollama at 127.0.0.1; configured model. No ChatGPT/OpenAI cloud API is required. An absent model produces an error, not fabricated results.
- Persistent SQLite ledger: approved scope, model, budget, states, attempts and bounded agent history.
- One active mission at a time to avoid GPU saturation; running missions can resume after Apollo restarts.
- Existing Foundry worker semaphore limits overlapping local model draft calls.
- At most two attempts per specialist before blocking. An explicit owner resume retries; each failure consumes budget.
- A fixed mission ends with **drafts completed**, never **tests passed**. Until-stop mode cycles until its finite budget, planning-round limit, or user stop. Infinite autonomous use requires renewed authorisation and budget.
- Model/chat API is read-only. Start, pause, resume, stop and priority changes are owner UI controls, not exposed to model-generated tools.
- Source selection reads fixed allowlisted source excerpts, not private memories, logs, credentials or arbitrary user files. Owner-entered mission objectives and agent drafts persist locally. Do not paste secrets into mission briefs.
- No automatic releases, signed update installs, GitHub publication, API purchases or medical/vehicle actions.
- Coexists with existing Foundry, Learning Missions, Self-Improvement Lab, Architect Bridge and Update Centre.

## Next integration (not yet implemented)
A safe second phase would route candidates into an owner-authorised ephemeral Foundry Docker session for real tests, compare actual benchmarks and regressions, then create an isolated development pull request and a human-approved update transaction with rollback. This is future work, not part of this release candidate.

## Verification
From `apollo_ui`, run `APOLLO_BASE_DIR="$PWD" python module_validator.py modules/jarvis_director`. Module tests use deterministic fake Ollama workers and cover agent roles, owner gates, path restrictions, budgets, restart recovery and candidate staging. They do not claim a real model, live UI, or Docker was exercised.
