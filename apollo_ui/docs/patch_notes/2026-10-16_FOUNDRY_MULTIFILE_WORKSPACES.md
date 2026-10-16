# Foundry: editable multi-file app workspaces

## What changed
- The owner-created PySide6 starter now uses the same guarded generated-artifact writer as Foundry workers. Its five files are recorded in `.foundry-generated.json`; future implementer tasks can update them without bypassing manual-edit protection.
- Foundry supplies a bounded generated-file inventory in worker context, even when full source does not fit. Context prioritises task-named modules. Source which was manually modified or is not Foundry-owned is never included.
- Chat may create a private reviewable app project with `create_app_project`, or query generated-file metadata with `app_project_files`. Neither action runs arbitrary code or approves a release.
- Implementer prompts encourage incremental modules with tests rather than trying to generate a full large application in one response.
- Added offline regression tests for multi-file ownership, editing, privacy boundaries, context limits and chat project creation.

## How to use
1. In Apollo chat, ask to **create an app project** and specify the title and requirements. The new tool sets up the workspace and tasks. Alternatively use **Foundry > + New App Project**.
2. In Foundry, optionally select **Create Starter UI** to obtain a working PySide6 launcher, service, UI, test, and UI/backend contract. This source becomes Foundry-owned and editable.
3. Assign implementer subtasks by module (for example: domain logic, persistent storage, UI widgets, tests). Each worker returns a bounded set of changed files; other owned modules remain intact.
4. Review the actual source, run static UI wiring checks, then run isolated Docker unit, UI interaction and startup checks.
5. Review tested changes and optionally use the separate consent-gated **Launch App Window (Local)** control. Nothing launches automatically.

## Boundaries and verification
- This change does not turn chat into an unrestricted file editor. Chat can create tasks, while the code handoff remains tied to an authorised Foundry session and its private project folder.
- Foundry-generated code is untrusted until independently reviewed and verified.
- Python/PySide6 is the runnable app format today. Generic JavaScript/HTML/electron project support would require separate test images and controls.
- Continuous agents still stop when the Apollo UI exits. Durable cross-restart missions remain separate engineering work.
- Remote CI is required before merging and actual Ollama/Docker Desktop testing on the Windows workstation remains necessary.
