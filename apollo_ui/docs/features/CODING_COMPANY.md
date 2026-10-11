# Apollo Coding Studio v1

Apollo's **Coding Studio** is available in **Apps → Coding** after modules are
reloaded. It uses five sequential specialist roles:

1. Architect proposes a plan and acceptance criteria.
2. Developer writes candidate files under a private project workspace.
3. Tester reads files and receives the actual static Python syntax report.
4. Reviewer can accept the proposal or send it back for limited rework.
5. Integrator produces a final description and suggested manual run steps.

A deterministic manager advances one role at a time; the complete-team button
repeats role turns until user review, a failure, a pause or a hard turn limit.
Each role uses a distinct system prompt and the last role-turn records. This
can run on **one local Ollama model** without loading five models at once.
The optional **Safe demo** mode uses no model, network or GPU.

## Quick start

1. Open Apollo → Apps → Coding → Coding Studio.
2. Enter a project name and plain-language requirements.
3. Choose Local Ollama or Safe demo; select a turn budget (5–40).
4. Click Create Project, then Next Role or Run Team (bounded).
5. Inspect the candidate file preview, role log and displayed validation label.
6. Approve Candidate, Request Changes with notes, or Reject.
7. To actually run the generated program, explicitly review its contents,
   dependencies and intended effects, then use your own isolated test
   environment. This is **not** automated by the studio.

Outputs are in \`apollo_ui/workspace/coding_company/<project-id>/candidate/\`.
Records are in \`apollo_ui/storage/databases/coding_company.db\`.
Neither should be pushed to a public GitHub repository.

## Safety and current limitations

- **No generated code execution or live Apollo core writes.** Python files
  receive an AST syntax check only, not a unit test run or launch test.
- The AI tester and reviewer offer advisory opinions; they cannot certify
  functional correctness, security or successful test execution.
- No sandbox, containers, Git worktrees, signed integration, CI on each
  generated candidate, or automatic live-module update yet.
- Role turns are sequential, but Apollo currently has **no shared GPU lease
  with XTTS**. Pause voice generation if your 12 GB GPU is out of memory.
- Ollama connections are restricted to a local HTTP endpoint on port 11434.
  Requests have a 120-second HTTP timeout; a running call cannot be
  instantly interrupted. Stop prevents *subsequent* turns and takes effect
  after the current model call ends.
- File paths are allowlisted, candidates are limited to 20 files/250 KB
  and each generated file is at most 60 KB. Data remains in the project
  candidate folder. This is *not* a full OS security sandbox.
- Max 40 role turns and max 5 automatic reviewer/static reworks per project;
  retry/failure evidence persists across restarts.
- User approval only marks a candidate reviewed. It does **not** install it.
- Role lessons require explicit evidence and a user-approved completed
  project. There is no background fine-tuning or model weight training.

## Next engineering milestones

- Hard-isolated subprocess/container testing with no network or secrets by
  default, real unittest/pytest evidence and integration launch checks.
- JobController with cross-process leases, heartbeats and termination,
  GPU coordination with XTTS, disk/output limits and 12-hour opt-in schedules.
- Git worktrees, diff review, file collision controls, independent integration
  test pipelines, rollback and signed deployments.
- Optional automatic promotion of *verified* lessons after owner approval,
  with a lesson browser, source revisions and deletion controls.
- Windows interactive GUI + RTX 3060/Ollama smoke test, and a separate
  Raspberry Pi headless compatibility check.

These are next milestones, **not** claims of implemented features.
