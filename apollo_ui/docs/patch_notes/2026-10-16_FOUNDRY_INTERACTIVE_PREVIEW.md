# Foundry interactive local preview (2026-10-16)

## What changed
- Foundry → **4. Sandbox** now includes **Interactive Local Preview (Trusted Code Only)** with **Launch App Window (Local)**, **Stop App**, a status label, and a bounded stdout/stderr console.
- The app runs as a separate Qt-managed Windows process (QProcess), not inside Apollo's GUI process. A crash should not close Apollo.
- Clicking Launch first validates a regular project-local `launch.py` and reruns static syntax and UI/backend contract checks. An explicit, default-No warning is required **on every launch**.
- No worker, meeting, tool, or automatic build can trigger a local preview. The user must click Launch.
- Stop terminates the managed preview process. If the generated app starts child processes, these may require manual cleanup.
- Added offline validation tests and Windows Qt tests verifying the controls and refusal when consent is declined.

## Critical security limitation
**Local preview is not sandboxed.** Generated Python runs with the same user permissions as Apollo and can access local files and network. Static checks only inspect syntax and declared UI/backend links; they do **not** establish code safety. Use Docker tests and inspect the generated source before agreeing to local execution. For truly untrusted programs, do not use local preview.

## What this does not yet do
- No interactive streamed Docker GUI, embedded window, live screenshots, or click recording.
- No dependency installation for generated apps; use the Apollo environment and installed packages.
- No automatic testing, approvals, deployment, or publishing triggered by preview.
- No reliable whole-process-tree termination if a generated app spawns children.

## How to use
1. Pull main and restart Apollo.
2. Open Foundry, select the project and check its generated files and `launch.py`.
3. Run static checks and preferably both Docker sandbox tests.
4. Under **4. Sandbox**, click **Launch App Window (Local)**, read the warning, and explicitly approve only trusted source.
5. Interact with the separate app window; use **Stop App** to terminate it.
6. Use **Report Issue** and **Send Failures to Worker** to continue development.
