# Apollo standing improvement and funding mission

Implemented in Developer Lab → Autonomous Source Learning, backed by
`apollo_source_learning.py`. This is an idle study and experiment service, not a
claim of self-directed consciousness, guaranteed income or verified capability gains.
The full built-in self-prompt is `STANDING_PROMPT` and appears in the empty journal UI.

## What starts automatically

When the Self-Improvement Lab module is enabled and the UI idle tracker is attached,
Apollo starts after five idle minutes. The standing goal is to become more useful to
Oscar and ZSS through evidence-backed improvements. Four attempts per UTC day,
at least one hour apart, each with a 120-second wall-time budget. User interaction,
foreground chat, pause/stop and scarce host CPU/RAM defer work. One local model
call lasts at most 60 seconds and shares the existing model lock. It uses the
configured local Ollama model, never auto-selects a cloud model or installs weights.

1. Rotate four fixed public topics: retrieval/evidence, agent reliability, local
   speech latency, reasoning/evaluation. No owner chat, source code, credentials or
   private goals are sent in search queries. Discovery uses anonymous GitHub API
   reads, no inherited proxy or authentication, no redirects, at most 12 requests
   per cycle, eight-second request timeouts and 1 MiB response limits.
2. Inspect one new eligible repository. Pin its default-branch commit and retain
   verified Git blob hashes, root licence/NOTICE text, a small README and at most
   two small Python source samples. Only MIT, Apache-2.0 and BSD-2/3-Clause
   repository metadata with pinned licence text qualify automatically. This is a
   screening policy, not a full licence/dependency audit. Per-file licences,
   upstream obligations and compatibility require review before production reuse.
3. Ask local Ollama for a concrete lesson, limitations and optional three-file
   comparison. Repository text is untrusted data; the model has no tools here.
   Fixed names, bounded Python text and AST parsing precede any experiment.
4. Execute comparisons only through the existing Foundry Docker sandbox: no
   network, read-only source/root filesystem, non-root, no capabilities, 1 CPU,
   768 MiB RAM, 64 processes, limited output and a 45-second test deadline. Never
   install dependencies, clone/build whole projects, pull images automatically,
   run foreign code on the host or mount Apollo's storage/credentials/GPU.
5. Retain receipts and candidate files in the local SQLite journal. A passing
   synthetic experiment is **review**, not an approved or measured Apollo upgrade.
   Real baseline regressions and release approval are still necessary.

Missing Docker/image leaves a durable `awaiting_sandbox` study; other discovery
continues. Those experiments are retried when the installed image becomes
available. Three non-interruption failures block a study. Interrupted sampled or
studied stages resume without refetching. Seen repositories are skipped (V1 does
not revisit newer commits). There is a hard 500-study ceiling; retained records
are not silently discarded. Anonymous GitHub rate limits and unavailable local
models surface as errors, with no bypass or host-execution fallback.

Pause and Stop persist across restarts. Resume retains budgets; it does not reset
spending or grant additional permissions. Process leases prevent overlapping
research attempts. Reads, source samples and generated code are inspectable in
the journal; `source_learning_status` exposes compact provisional findings to Chat.
Accepted studies do not retrain model weights or rewrite Apollo's production code.

## Funding and upgrades

The same standing prompt can propose a small service/product opportunity with a
specific offer, deliverables, risks and demand/delivery validation. These are
hypotheses grounded in the source study, not verified market research or sales.
A new plan produces a local Apollo notification and a review item. No public
messages are sent.

The owner button **Approve £0 local preparation** grants exactly two local drafts:
`offer_draft.txt` and `delivery_checklist.txt`. Idle execution produces an auditable
receipt with zero spend, no external actions and no verified revenue. Dismissal,
pause and stop revoke/defer pending preparation. This is the currently supported
execution step. Publishing offers, contacting customers, taking payments, buying
ads or spending require separate account-specific integrations and scoped owner
approval; this version does not execute those actions. There is no blanket
"make money" tool or financial account access.

Three CPU/RAM pressure observations within ten minutes create an upgrade case and
notification, showing the measurements and recommending profiling/optimisation
before comparing a component upgrade with a new PC. GPU/VRAM is not measured by
this service. It cannot infer a need for a new PC, a hardware price, available
funds or sales from these observations. An upgrade budget must use owner-reviewed
costs and actual net income, never projected revenue treated as cash.

## Validation

`python -m unittest -v tests.test_source_learning tests.test_foundry_sandbox`
checks durable budgets/leases, owner controls, interrupted recovery, deduplication,
licence/provenance handling, containment, cancellation, funding approval and real
Qt controls when available. Set `APOLLO_FOUNDRY_INTEGRATION=1` only with the trusted
Foundry image installed to run the real Docker comparison in CI. Model/network
orchestration tests use explicit fakes; they do not establish the quality of a
particular local LLM or test the owner's Windows hardware.

## One-button Self Upgrade Plan

Home and the Source Learning page both have **Self Upgrade Plan**. Clicking starts
or resumes the standing mission and authorises one bounded public funding research
mission: three idle-only batches, 120 seconds apart, through the existing Learning
Missions/Training public research permission broker. The current focus is UK small
business AI setup and admin automation services: demand, delivery costs, fees,
competition and feasible pilots. The existing mission engine retains fetched
pages, source URLs, timestamps, errors and receipts; denied/unavailable tools stay
visible. This is research permission only, with no publishing, spending or
customer-contact grant. Repeated clicks during a plan reuse the same mission.

A completed collection is read via Training's confined local research-file API and
passed as untrusted evidence excerpts to local Ollama for a funding proposal within
the existing study/model budget. Confidence remains provisional until real demand,
ability to deliver and unit economics are validated. The prompt explicitly drives
initiative and follow-through, not unwarranted certainty or guaranteed income.

The live record is `storage/source_learning/SELF_UPGRADE_PLAN.md`. It records what
Apollo is doing, planned steps, public research and source links, findings, funding
proposals, owner grants, actual preparation receipts and upgrade evidence. It is
updated locally when controls change and while the worker runs; identical content
is not repeatedly rewritten. The UI shows the exact file path. Pause/stop also
controls the linked funding mission (an already in-flight web batch may finish
according to Learning Missions' established policy). Commercial actions still
require their own reviewed implementation and account-specific grants.
