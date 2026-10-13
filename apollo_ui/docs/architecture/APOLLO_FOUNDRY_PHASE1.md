# Apollo Foundry — Phase 1 test candidate

**Product name:** Apollo Foundry
**Developer module identifier:** `project_studio` (kept for update compatibility)
**Stage:** Apollo Build 8 alpha, Foundry Phase 1 internal test candidate.
**Not:** A stable beta release, a code execution sandbox, or an autonomous software company.

## What you can test now

In **Home → Open Apollo Foundry**, create or select an application project.
Each new project gets initial Architect, Implementer, Tester, Reviewer and
Integrator jobs, with optional Manager-assigned subtasks. These jobs are
stored in local SQLite and app files stay under
`workspace/app_development/app-<id>-<slug>`.

### Revise work by saying "change this"

From the Foundry Tasks & Workers tab:

1. Select the app project and optionally select the task.
2. Press **Change this…** and describe the change, e.g.
   "Make the Save button bigger, move it under the name field and show a
    confirmation after the record is written."
3. Foundry creates an **open change issue and an Implementer revision job**
   linked to this project. The previously accepted task/code is not changed.
4. Select the revision job and press **Draft with Local AI**. Ollama must be
   running with the model chosen in Apollo config.
5. Review the draft. **Accept Draft** or **Request Changes**.
6. The issue can close only when the linked fix task is accepted.
7. If the app was previously approved, **Reopen Project** explicitly first.

From normal **Apollo Chat**, the coding module exposes the tool
`queue_app_change(project_id,request,task_id?)`. An exact project ID is
required, so requests cannot silently affect the wrong app. This tool only
queues a change; it cannot execute a worker, modify project source files,
run tests, approve changes or deploy anything. Chat routing depends on
existing Apollo tool catalog and local model support.

### UI & Code Tests tab

This is Foundry's safe **Phase 1 static test runner**. It inspects only
Python files in the selected app folder (max 60 files, 2 MiB total, 256 KiB
per file) and rejects symlinked paths.

It checks:
- Python source syntax, before loading or executing anything;
- a declared Qt UI class and widget attribute;
- UI widget signal connected to an existing callback;
- callback refers to a declared backend method;
- all contract file paths are within the selected app folder;
- a persistent, timestamped pass/fail/incomplete report is recorded.

**Passing a static UI contract is not the same as a running UI**.
Foundry displays "Runtime UI: NOT TESTED" even if everything is green.
Tests of actual click-to-backend behavior in CI execute only *Apollo-owned
trusted PySide6 fixture code*. Running generated/third-party app code needs a
later real sandbox, restricted permissions and a human opt-in.

### App file contract

Place these files in the app project folder (you may use
**Open Project Folder** in the test tab):

`service.py`:
```python
class AppService:
    def __init__(self):
        self.saved = 0

    def save(self):
        self.saved += 1
```

`ui.py`:
```python
from PySide6.QtWidgets import QWidget, QPushButton

class AppWindow(QWidget):
    def __init__(self, backend):
        super().__init__()
        self.backend = backend
        self.save_button = QPushButton("Save", self)
        self.save_button.clicked.connect(self.on_save)

    def on_save(self):
        self.backend.save()
```

`foundry.json`:
```json
{
  "schema_version": 1,
  "ui": {
    "file": "ui.py",
    "class": "AppWindow",
    "bindings": [
      {
        "widget": "save_button",
        "signal": "clicked",
        "handler": "on_save",
        "backend_attribute": "backend",
        "backend_file": "service.py",
        "backend_class": "AppService",
        "backend_method": "save"
      }
    ]
  }
}
```

**How it works:** selecting **Run UI & Code Checks** validates the declared
source wiring without importing the app, importing PySide6, executing its
top-level statements or opening windows.

If something fails, the report names the disconnected widget, missing
handler, nonexistent backend method or syntax failure. Click **Request Fix
for Failures** to create a reviewable implementer task with the findings.

### Stored report states

- **PASSED:** declared source connections were located, nothing was executed.
- **FAILED:** syntax or an expected link failed; Create Fix request available.
- **INCOMPLETE:** no Python files or no UI contract; do not claim success.

History retains at most 30 reports per project. All of this is **local
and outside GitHub-tracked application source**; do not commit personal
app briefs, voice assets, medical records or project databases.

## Test matrix for Phase 1

| Scenario | Required evidence |
|---|---|
| Create/restart | Project, tasks, and issue records survive process restart |
| Real Qt buttons | Apollo-owned reference button emits clicked -> calls backend |
| UI connectivity | UI signal/handler/backend reference found, or accurate failure |
| Bad wiring | Missing connect/callback/backend produces FAILED |
| Malformed source | Syntax error produces FAILED, not a crash |
| Untrusted source | Source top-level code is never imported or executed |
| Path traversal | References to `../...` rejected |
| Symlink | Workspace symlink rejected |
| Revisions | "Change this…" records target task and editable implementer job |
| Chat | `queue_app_change` requires project ID and cannot run code |
| Failed checks | Owner can queue a fix ticket with recorded findings |
| Worker failure | Interrupted worker can be marked blocked and manually retried |
| Review gate | No AI tool can approve project, deploy or execute generated code |
| Windows | PySide6 offscreen Project Studio and Update Centre tests pass |
| Offline | Tests don't use web or install packages; local model drafting is optional |
| Update safety | Existing signed-updater checks and rollback regression continue to pass |

## Phase 1 exit criteria

- [ ] All Foundry Python tests and Windows Qt UI CI jobs green on the
  **latest commit**, not merely an earlier branch commit.
- [ ] Real Windows PC manual GUI test with the configured Ollama model.
- [ ] Create project; launch Foundry; draft/accept/revise; close and reopen
  Apollo; confirm no lost data.
- [ ] Put the sample `ui.py`, `service.py` and `foundry.json` in a new
  project folder; run checks and inspect PASS.
- [ ] Deliberately remove the signal hookup; rerun and inspect FAIL.
- [ ] Press Request Fix for Failures; confirm assigned job and issue.
- [ ] Confirm no generated code execution, install or approval by AI.
- [ ] Review that the updater **process** crashing at ~14% (#27) is still a
  separate beta blocker; this PR does not resolve its unknown root cause.
- [ ] Audit GitHub history exposure of private runtime files (#28).

**Next Phase:** generated project runner in a real sandbox; bounded dependency
graph, parallel role budgets, isolated code diffs, live GUI subprocess tests,
launch/crash/rollback evaluation, and actual build artifacts. Until that exists,
do not interpret static analysis as actual app functionality.
