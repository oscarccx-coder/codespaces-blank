# Apollo Discovery Alliance: working finite experiment stage

Status: **feature branch implementation**, not enabled in main and not evidence of AGI, independent AI consciousness or safe production self-modification.

## What the video inspired

The speculative AI alliance story demonstrates specialisation, selection, shared experiment history and descendants with modified strategies. It also illustrates the dangers of selecting agents for **self-preservation or proxy objectives**. Apollo adopts the engineering techniques without reward for survival, replication, unchecked access or acquisition of resources.

| Video concept | Apollo's present implementation | Limit |
|---|---|---|
| Team specialisation | Direct, decomposition and verified-answer recipes; future dedicated Scout/Engineer/Skeptic meetings through existing Foundry meeting code | Not multiple independent models |
| Competition and fitness | Same 40 fixed arithmetic/Python-expression cases, three repeats per candidate | Narrow smoke benchmark only |
| Successful descendants | Top qualified recipes can have up to two bounded cloned variations per generation | Recipe settings only; no new processes or model weights |
| Selection and retirement | Failed candidates put on probation, then retired; safety issues quarantined; baseline retained | Evidence never deleted |
| Shared memory | Local SQLite trial results, lineage, state transitions, audit events | No hidden broad knowledge transfer |
| Self-upgrade | Winner yields a **review-only** draft to Foundry; human must test and approve any real production change | No automatic core edits |
| Autonomy | An authorised session repeats individual local model calls, one at a time | Pauses between calls; two-hour expiry, three generations max |

## Design and files

- `apollo_discovery_selection.py` (PR #34): bounded trusted fitness/clone plan.
- `apollo_discovery_campaign.py`: persisted campaign and repeatable exact-answer benchmark, finite step function, local Ollama using the existing single-GPU lock, replayable evidence.
- `modules/project_studio/discovery_view.py`: Foundry tab with Create, Authorise + Start, Run One Test, Pause, Stop, proposal handoff, population and lineage display.
- `modules/project_studio/module.py`: one additional Foundry tab and an owner-confirmed *queue change* handoff.
- `tests/test_discovery_selection.py`, `tests/test_discovery_campaign.py`: Linux and Windows offline regression tests.

SQLite state lives in `apollo_ui/storage/databases/apollo_discovery.db`, already under the repository's ignore rules. Never commit it or any user storage to Git. Preexisting tracked user media must be audited separately.

## Running it

1. Merge/review predecessor PR #34 and its subsequent Discovery integration PR in order. Update Apollo to that version.
2. Install/launch Ollama, select a local model in `config.json`. Discovery uses only the configured model at `127.0.0.1:11434`.
3. Open **Apollo → Foundry → Discovery Alliance**.
4. **New Discovery Campaign** (draft only).
5. **Authorise + Start** explicitly. The finite testing loop runs on a Qt worker, using Ollama sequentially. Click **Pause** to stop new calls or **Stop** to make the campaign terminal. In-flight model requests finish or time out first, and their result is discarded if pause/stop was recorded.
6. Inspect results and, if a qualified narrow improvement exists, select a Foundry app project and click **Send Proposal to Foundry**. This creates only a regular change request, never a live upgrade.

**No background daemon, external search, network beyond loopback Ollama, model weight changes, shell command execution, Docker generation run, production promotions, human-safety override or financial/medical/vehicle actions are part of Discovery.** It is deliberately not a 24/7 survival-optimiser.

## Testing and acceptance

- At least 30 questions and 3 repeats, fixed SHA-256 benchmark digest; raw free-text model replies are not stored.
- No model call until owner has approved a session; stop/expired authorisation blocks future calls; no auto-resume after restart.
- Candidate correctness independently derived from the immutable answer key, never from model self-reports.
- Test failures don't create fabricated successes; the last verified baseline and audit evidence are protected.
- Descendant mutations cannot modify the evaluator, budget, tools, permission policy, model weights or actual Apollo code.
- Model calls respect the single global Ollama mutex and bounded context, output tokens and HTTP timeout.
- Winner remains experimental. The authored benchmark is **not a sealed holdout** and does not justify an "Apollo can do this perfectly" claim.
- UI must remain responsive through long model calls; closing Discovery prevents it from issuing further calls.

## Next stages before actual Apollo production self-upgrades

1. Independent, locked unseen benchmark cases with uncertainty intervals and adversarial tests (not revealed to candidate).
2. Scientific hypotheses and dedicated specialist meetings where each role performs measurable work; treat each statement as an untrusted *proposal*, not evidence.
3. Candidate generation in a reviewable **project-local code sandbox** using existing Foundry Docker tests and checkpoint/rollback architecture.
4. Owner-reviewed skill registry with unique revision IDs, signed rollback and domain-specific reliability targets.
5. Session budgets for total tokens/GPU time/disk, crash recovery and full audit metrics.
6. Explicit approval gates for upgrades touching health, vehicles, connected services, physical systems, money or production safety code.

Founding invariant: Apollo optimises **measurable service to human goals** while always remaining interruptible, auditable, and controllable by its owner.
