# Apollo Foundry: engineering facility v2

## Purpose
Foundry is Apollo's owner-controlled, local software engineering facility.
It builds standalone project applications in `workspace/app_development`.
It **does not** have permission to rewrite Apollo's trusted core, publish
releases, install dependencies, access secrets, or run generated code directly
on Windows without an explicit separate owner action.

## Prerequisites (Windows)
1. Apollo Python environment and PySide6:
   `Setup/01_INSTALL_APOLLO.bat`.
2. Ollama running with the model named in `apollo_ui/config.json`.
   For the default coding model: `ollama pull qwen2.5-coder:7b`.
3. Hardware virtualization and WSL 2, if required by Docker Desktop.
   Enable Windows virtualization in BIOS/UEFI if Docker reports it missing.
4. Docker Desktop: `Setup/14_INSTALL_DOCKER_DESKTOP.bat`. This asks permission
   before invoking official `winget`; it may require a restart.
5. Start Docker Desktop in Linux-container mode and finish first-run setup.
6. Build Apollo's trusted test image with
   `Setup/09_SETUP_FOUNDRY_SANDBOX.bat`. This requires Internet during
   the *owner-controlled image build only*. Runtime test containers have no network.
7. Verify with `Setup/15_CHECK_FOUNDRY_PREREQUISITES.bat` and
   Foundry > Sandbox > Check Docker.
8. Leave adequate free disk space on the Windows system drive. Docker/WSL
   images may occupy C: even if Apollo itself is installed on F:.

The trusted Docker image includes pinned Python 3.13, PySide6, NumPy, SymPy
and Matplotlib. These are for scientific, calculator, graphing and general
Python UI projects. Extra third-party dependencies are not installed by the
model. Extend the trusted image only after owner review.

## Build workflow
1. Enter a project brief with concrete features and examples.
2. **Start Continuous Build** and approve a single session authorization.
3. Six local model roles hold a kickoff meeting.
4. The Manager proposes a bounded implementation subtask plan with explicit
   dependency indices. Within this explicitly authorised continuous session,
   these project-local tasks are queued without requiring separate clicks.
   Task drafts still require owner acceptance.
5. Implementers receive actual bounded generated project source, current
   task, owner requests, previous feedback, meeting decisions and recorded
   Docker test output. They return changed project-local files as JSON.
6. The artifact writer refuses path traversal, symlinks, non-owned overwrites,
   oversized bundles and manually edited files.
7. Static checks verify syntax and declared UI-to-backend links.
8. The Tester runs, in order, **Docker unit tests**, **actual declared Qt
   UI interactions**, and **GUI startup smoke**. Tests are bounded and run
   inside network-disabled, read-only, non-root containers with dropped
   capabilities, resource limits and no Docker socket mount.
9. Real failures produce repair tasks and further team checkpoints.
   Repeated failures pause for owner review rather than looping forever.
10. Passing test suites produce a hashed source checkpoint. The current
    source fingerprint must match successful unit, UI interaction and
    startup test reports before Foundry labels a build as verified.
11. When no ready tasks remain, Foundry waits for your review or more changes.
    Pause/Resume/Stop remain available. **I'm Happy / Review** stops the
    session and opens owner review, not automatic project approval.

## Test limitations
- The automatic UI interaction runner reads `foundry.json`, instantiates the
  declared UI class with its backend instance, clicks declared Qt controls
  and verifies backend method invocation. Currently supported signals are
  `clicked`, `triggered`, and `returnPressed`. Unsupported contracts
  fail verification rather than falsely reporting a pass.
- GUI startup smoke only verifies that `launch.py` survives three seconds.
- Even when all checks pass, visual correctness, performance, usability and
  all application behaviours are **not** proven. Human acceptance is required.
- Generated code is not a trusted application merely because static checks
  pass. The separate **Launch App Window (Local)** is unsandboxed and always
  asks for owner permission. Do not use it for unreviewed generated source.
- Docker reduces risk but does not provide an absolute security guarantee.
- The manager can propose project-local code changes but not commit to the
  Apollo core repository or change Apollo's medical safety controls.
- Continuous sessions run only while Apollo is open, and stop/pause takes
  effect after the currently running Ollama or Docker operation completes.

## Version control and recovery
- **Save Checkpoint** snapshots only Foundry-generated, hash-matched files.
- **Restore Selected** requires owner confirmation, saves a pre-restore
  backup and refuses to overwrite manually edited files.
- Files introduced after a snapshot are retained.
- Checkpoints are limited to 30 per project and 2 MiB of owned source each.
- After restoring code, re-run Docker tests; stale results do not validate
  the restored revision.
- These local checkpoints are not Git commits. Future Apollo-core coding
  needs a separate isolated branch/PR workflow with explicit owner review,
  CI and signed release gating.

## Development and CI
The regression suite covers:
- legacy project database migration and dependency-ready task dispatch;
- manager plan validation, including cycles/invalid references;
- actual generated source context and private untracked file exclusion;
- checkpoint integrity, manual edit protection and restore/undo;
- read-only prerequisites;
- Docker missing/image missing, timeouts, bounded logs, read-only mounts;
- real PySide6 UI click-to-backend tests and intentionally broken UI wiring;
- pinned scientific dependencies inside the offline runtime image;
- Windows Qt controls, preview consent and continuous-session safeguards.

GitHub Actions jobs: `python-regressions`, `foundry-sandbox-integration`,
`windows-installer-smoke`. A green CI run is not a substitute for testing
the Ollama model and Docker Desktop on the owner's own Windows computer.

## Future engineering milestones
- Richer UI automation with screenshots, mouse coordinates, accessibility
  trees and visual regression comparison inside an isolated interactive GUI.
- Persistent job queue and checkpointed restart/recovery (currently
  continuous sessions are UI-lifetime only).
- Git branch and pull-request staging for **Apollo core** changes with
  per-file diff approval, trusted CI and release signing.
- Quantitative worker evaluations, task duration budgets and searchable
  architecture/bug memory.
- Explicit dependency installation approval, vulnerability audits and
  reproducible application packaging.
