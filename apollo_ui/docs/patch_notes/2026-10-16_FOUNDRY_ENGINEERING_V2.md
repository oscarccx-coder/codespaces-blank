# Foundry engineering v2

This update extends Apollo Foundry from discussion-led drafting toward
owner-controlled, evidence-based software engineering.

### Added
- Real generated-code context supplied to every worker draft and repair.
- Manager-generated, bounded implementation subtask plans in authorised
  continuous sessions; persisted task dependencies and ready-task dispatch.
- Real PySide6 click-to-backend checks in restricted Docker, alongside unit
  tests and GUI startup smoke. UI interaction failures become repair tasks.
- Pinned NumPy, SymPy and Matplotlib in the owner-built Docker image.
- SHA-256 source fingerprints on Docker test reports; old passing tests
  do not certify changed source.
- Hashed local generated-file checkpoints with owner-confirmed rollback,
  pre-restore backups and manual-edit protection.
- Automatic checkpoint creation after all continuous Docker test stages pass.
- Worker scorecard showing recorded drafts, reviews, accepted and blocked tasks.
- Read-only `Setup/15_CHECK_FOUNDRY_PREREQUISITES.bat` diagnostic.
- Regression tests for dependency migration, source context, rollback,
  preflight, UI wiring and real Docker scientific dependencies.

### Existing safety rules retained
- No untrusted generated code executes in Apollo's host Python environment
  automatically.
- Owner approval is required for unsandboxed local preview, final task
  acceptance, project approval, installation and release.
- Docker tests use read-only source, no network, non-root user and
  resource/capability limits.
- Continuous mode pauses on repeated failures, does not persist after
  Apollo closes, and waits for input when work is exhausted.
- Generated workers cannot directly modify Apollo core or medical rules.

### Limitations
The Docker UI runner covers declared Qt signals/backend calls, not arbitrary
visual appearance, screenshots or accessibility interaction. A model still
needs to produce suitable runnable code and meaningful tests. End-to-end
Ollama and Docker Desktop operation on the owner's PC must be tested locally.

Full engineering notes: `docs/FOUNDRY_ENGINEERING_V2.md`.
