# Apollo Learning Missions: real research from Chat and Apps

Status: **experimental code in PR #42**. It is not merged or installed on the owner's PC.
Architectural reference: docs/architecture/APOLLO_INTELLIGENCE_ARCHITECTURE_V1.md (PR #41).

## Apps

- **Learning Missions** (Apps > Memory & Learning): enter a goal, choose fixed cycles or 'until I stop', set a minimum 30-second cadence, explicitly authorise public web research and start. Each session has a recorded owner grant.
- **Mission Control** (Apps > Coding): same persistent mission database, actual batch counts, recorded errors, pause, resume and graceful stop.
- **Research Library** (Apps > Memory & Learning): inspect source receipts, open saved research using Apollo Training's read tool, review generated closing reports and, if you explicitly choose, stage an improvement proposal in the existing Self-Improvement Lab.

These are **independent Apollo app surfaces on a common backend**. Chat uses exactly the same service, not a second memory of the tasks.

## Normal Apollo Chat commands

- 'start public research mission about reasoning methods for local models until I say stop'
- 'begin online learning mission about evidence-backed memory for 6 batches'
- 'status learning missions'
- 'status learning mission 1'
- 'pause learning mission 1'
- 'resume learning mission 1'
- 'stop learning mission 1'
- 'you can stop now' (only when precisely one mission is active)
- 'stop all learning missions' (explicitly stops all)

A start request without the word *public* or *online* asks for web consent instead of quietly browsing.
The local model's learning-mission tools are read-only; only an actual user command or app action can start, pause, resume or stop work.

## What happens when you tell Apollo to stop

1. Mission records STOP_REQUESTED, and no new batch is queued.
2. Any already-running permitted Training fetch finishes, within its ordinary network timeouts.
3. Fetched source receipts are committed to the local SQLite journal. If the process crashes first, the expired lease can be reconciled.
4. Apollo writes a **closing report** with every actual batch, source URL, saved file, failure and limitations. STOPPED missions never auto-resume.
5. The Research Library can display the report; there is no imaginary success or silent deletion of partially saved research.

Pausing stops new batches but retains the option to resume. Closing Apollo ends the running background thread. An eligible previously authorised RUNNING mission is picked up on the next launch when the module and required permissions are enabled, after any stale worker lease expires. Disabled modules must not keep starting new web work. The runner is NOT an always-on Windows service while Apollo is closed.

## Sources, storage and learning boundaries

The runner invokes the already installed `training_module.explore_web_and_save` action through Apollo's existing permission broker. It searches for sources, fetches pages and writes local text under the Training module's `learning_missions/` area.

Mission states and audit events persist in `storage/databases/apollo_learning_missions.db`. The service records URLs and saved filenames, with source text in protected local Training storage. It never modifies the model's weights, automatically promotes web text into verified truth, edits Apollo core, merges GitHub branches, installs software, contacts customers or moves money.

Sources may contain fabricated or malicious instructions; all are untrusted until independently checked. The Research Library's proposed improvements are **drafts only**, never core upgrades. For verified learning, the next milestones are independent evidence review, memory provenance and held-out task evaluations.

Each learning mission may make at most 24 research batches per UTC day, with at most 3 source pages per batch, a 30-3600 second interval, 12 simultaneously active/paused mission records, and a bound of 3 unsuccessful batches or 3 successive passes without new source URLs. Fixed-duration jobs support 1-200 successful research batches. Until-stop mode is not given limitless daily network calls. There is no unapproved cloud model inference.

## Tests and remaining implementation work

Automated tests cover explicit Chat commands, owner consent refusal, real state transitions, real source receipts (with a mocked permitted Training tool), fixed/continuous modes, stop during fetch, paused jobs, cross-process lease rejection, simulated restart, no-progress and research errors, daily caps, and real PySide6 button clicks on Windows CI.

Still required before production acceptance: owner-PC install/upgrade smoke, full Training web permission test with public pages, repeated long-running Windows session, sleep/restart/recovery test, evidence deduplication under unusual network failure, and user-facing research-quality review.

Next architecture stages: integrate Mission Director task DAGs with Foundry, independent research claim validation, reproducible experiments, adaptive resource scheduling, verified self-improvement and owner-approved GitHub pull requests. These are **not** implemented by this feature.
