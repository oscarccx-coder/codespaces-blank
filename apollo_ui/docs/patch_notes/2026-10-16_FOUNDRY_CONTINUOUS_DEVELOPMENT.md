# Apollo Foundry: owner-controlled continuous development (2026-10-16)

## New workflow
Foundry now has **Start Continuous Build**, **Pause**, **Resume** and **Stop**. This is a session-only authorization: it does not silently restart when Apollo restarts.

Start requires:
- a selected, non-approved app project;
- Docker Desktop running in Linux container mode;
- the trusted, locally built `apollo-foundry-qt:phase1` image;
- an explicit user confirmation to run generated project tests automatically **inside restricted Docker containers**.

After confirmation, Foundry holds a real six-role kickoff meeting, selects ready implementation tasks, stages generated Python source, checks syntax and UI/backend contracts, runs Docker unit tests, then a three-second Docker GUI-startup smoke test. Actual test failures are recorded and sent back as implementation repair tasks. Up to three automatic sandbox failure repair cycles are allowed per session; the session then pauses for human review. Existing local model generation retries remain capped at three per task. Additional team meetings happen after five completed worker drafts when more work is queued, or in response to issues. Manager decisions remain drafts, not owner approval.

If all available tasks have produced drafts, Foundry stays **WAITING**, checking for new tasks every 30 seconds. It does not manufacture meaningless tasks or re-run completed drafts forever. The owner can add changes or approve/reject reviews. Pause prevents new model and Docker jobs once the current operation finishes. Stop ends the session without deleting source, meeting transcripts or reports.

## Docker installation on Windows
1. Run `apollo_ui/Setup/14_INSTALL_DOCKER_DESKTOP.bat` (opt-in official `winget` installer).
2. Enable virtualization and WSL 2 if required. Restart Windows if prompted.
3. Open Docker Desktop, complete its first-run prompts, and switch to Linux containers.
4. Run `apollo_ui/Setup/09_SETUP_FOUNDRY_SANDBOX.bat` to build the trusted PySide6 image.
5. Restart Apollo, open Foundry, select a project, and click **Start Continuous Build**.

## Boundaries
- Automatic tests use `--network=none`, read-only project snapshots, dropped Linux capabilities, CPU/memory/PID limits and a non-root container user. Docker isolation is **not** an absolute security boundary.
- Generated code is **never** launched directly on Windows by the continuous session. The separate **Launch App Window (Local)** control still requires explicit approval each time and is **not sandboxed**.
- The Docker GUI smoke test checks startup survival only, **not** clicks or visual correctness. User acceptance testing is still needed.
- The model is not permitted to approve project tasks, install software, publish apps, or change Apollo core.
- Pausing/stopping does not interrupt an in-flight local Ollama HTTP call or Docker operation; it prevents subsequent jobs.
- If a task repeatedly fails, Docker becomes unavailable, or a meeting fails, the session pauses for review instead of endlessly retrying.
- Continuous operation only runs while Apollo's Foundry UI is open and active. There is no unattended service and no cross-restart execution.
