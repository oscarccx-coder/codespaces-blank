# Apollo Foundry: opt-in isolated sandbox tests

**Status:** Alpha development branch. Sandbox launch is owner-triggered only.
**Safety:** Docker Desktop (Linux containers) is mandatory. No host Python
fallback is allowed, even when Docker refuses to start. Docker containers
reduce risk but are **not equivalent to a hardened VM** against all threats.

## Install once, manually

1. Install and start Docker Desktop in Linux-container mode on Windows.
2. Back up your current Apollo storage and code before testing new branches.
3. In the Apollo test checkout run `Setup\09_SETUP_FOUNDRY_SANDBOX.bat`.
4. Approve the prompt to build the dedicated image,
   `apollo-foundry-qt:phase1`. Image setup downloads base Python and
   PySide6 packages over the internet **only at build time**.
5. Confirm `docker image inspect apollo-foundry-qt:phase1` succeeds.

This requires free disk capacity for the image and Windows Docker Desktop
configured to use Linux containers. The GUI tests run headless/offscreen;
no generated windows will appear directly on the host desktop.

## Test an app

1. Open Apollo > Coding > **Foundry** (or **Open Apollo Foundry** on Home).
2. Create an app and select it.
3. Select **UI & Code Tests → Create Starter UI**. This adds `ui.py`,
   `service.py`, `launch.py`, `foundry.json` and
   `tests/test_ui.py` without overwriting existing files.
4. Select **Sandbox Testing**.
5. Press **Run Tests in Sandbox** and explicitly approve Docker execution.
   The starter's real PySide6 test clicks Save and confirms both backend
   state and a visible confirmation label changed.
6. Press **GUI Launch Smoke Test** and approve. Foundry starts
   `launch.py` in a separate container, waits 3 seconds and fails if the
   process exits too soon.
7. Inspect the saved stdout/stderr and result. If a test fails, use
   **Send Failures to Worker** to create a new change ticket.
8. Recheck/revise and repeat. No build or review is auto-approved.

## Isolation actually used

The Docker CLI is invoked as a fixed argument list without `shell=True`.
Untrusted code is copied into a size-bounded temporary snapshot, which is
mounted **read-only** inside a container. There are no Docker socket mounts,
Apollo model/memory/voice/medical storage mounts or host user-home mounts.

Docker flags include:

- `--network=none` prevents network connectivity during execution
- `--read-only` plus limited writable `/tmp` tmpfs
- `--cap-drop=ALL` and `--security-opt=no-new-privileges:true`
- `--user=65534:65534` with CPU, memory and process limits
- `--pull=never` prohibits implicit image downloads during tests
- bounded test-run timeout, then `docker rm -f` attempt
- captured, size-limited logs and persistent test history

The sandbox executes project tests when the project includes
`tests/test_*.py`, using `python -m unittest discover`. A zero-test run
is explicitly **INCOMPLETE**, not PASS.

The launch smoke only tests that a process stays running for three seconds.
It **does not** prove controls work, screenshots look right, or a GUI is
usable. For interaction validation, the user must include Qt widget tests
that use `.click()` or QTest and assert the backend/output state.

Not all third-party Python dependencies are installed. Phase 1 ships only
a pinned Python + PySide6 image; a generated app using numpy, databases,
browser frameworks or other packages may fail, and Foundry reports this
rather than permitting runtime network package installation.

**Important limitations:** Docker's isolation depends on the host Docker
daemon and OS configuration. This is not a guarantee against malicious
container escape or kernel vulnerabilities. Keep Docker patched, do not
run Apollo with elevated host privileges, and avoid testing unknown code
on the same machine holding irreplaceable private data.

## Failure / recovery behavior

| Condition | Report |
|---|---|
| Docker CLI unavailable | UNAVAILABLE, generated code not run |
| Image not installed | UNAVAILABLE, no automatic pull |
| No unit tests or launcher | INCOMPLETE, no false green |
| Syntax/import/assertion failure | FAILED, logs captured |
| GUI closes before 3 seconds | FAILED, logs captured |
| GUI process stays active 3 seconds | PASSED startup smoke, not full UI |
| Run exceeds resource time limit | TIMEOUT, force-remove attempted |
| Symlink, too many files, oversized source | Refused, no project execution |
| Browser or network access attempted | Network disabled inside container |

The underlying local DB stores the latest 30 reports per kind per project.
A sandbox run never updates task acceptance or project approval. After a
crash or restart, reports remain visible from local SQLite. A previous
failed test can be assigned to a new Implementer task with your approval.

## Release readiness

- [ ] Python sandbox mock/security regressions pass.
- [ ] GitHub CI builds the real Qt Docker image.
- [ ] CI runs actual starter app button → backend → label test in Docker.
- [ ] CI detects a broken unittest assertion.
- [ ] CI detects an actual GUI launch exception.
- [ ] CI verifies a healthy GUI launch survives the smoke window.
- [ ] Windows PySide6 Foundry Sandbox Testing tab renders and remains responsive.
- [ ] Actual Docker Desktop test works on your Windows workstation.
- [ ] Disk quota, power loss and Docker-daemon crash scenarios assessed.
- [ ] Repository privacy/history audit (issue #28) resolved.
- [ ] Updater **process** crash at ~14% (issue #27) resolved separately.

Sandbox testing can be tried in a **separate Apollo alpha checkout** once
CI passes, but do not promote it to Apollo 8 Beta or merge automatically.
