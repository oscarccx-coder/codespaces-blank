## 7.5.12.1 — UI Form Stability
**17 September 2026**

### Fixed
- Text inputs inside module apps no longer collapse into thin unreadable strips when the app host becomes vertically constrained.
- `QLineEdit`, combo boxes and spin boxes now receive a readable minimum height.
- Multi-line `QTextEdit` / `QPlainTextEdit` controls receive a useful minimum height instead of being crushed by layouts.
- `QPlainTextEdit` and spin controls are now included in Apollo's global form styling.

### Module App Host
- Module app pages are now hosted inside a scrollable container.
- If an app needs more vertical room than Settings → Apps can provide, Apollo scrolls the app instead of shrinking its form controls.
- The Apps selector list has a bounded height so it cannot consume the space needed by the open app.
- The module host minimum height was increased and uses an expanding size policy.
- Added a generic module-UI stabilizer so newly-generated modules inherit the same protection automatically.

### Voice Imprint Lab
- Added explicit readable minimum heights to profile, path, model, language and voice-test fields.
- Increased the output area's minimum height.
- Added a sensible minimum width/spacing for the main form panel.

---

## 7.5.12 — Internal Roadmap + Certified Activation
**17 September 2026**

### Apollo Roadmap
- Added `Apollo Roadmap` as a real UI-capable module.
- It can be opened from Apps and pinned/unpinned on the Hub like any other app.
- Roadmap state is persisted at `storage/roadmap/roadmap.json`.
- Apollo can read it through `roadmap_status` and update milestones through `update_roadmap_item`.

### Certified instant access
- A newly-created module now follows **validate → user approval → immediate live activation**.
- After activation Apollo refreshes Module UI and Hub discovery immediately; a restart is not required just to gain access to the new module.
- Added `activate_certified_pending(...)` to Module Manager.

### Approved module upgrades
- The same activation path supports `replace_existing=True` for module upgrades.
- An existing module is backed up before replacement.
- If the upgraded module fails to become live, Apollo automatically restores the previous installed version.

### Self-feature boundary
- Module-based Apollo features can use this instant activation path.
- Core process files such as `main.py` still require a restart when replaced; future OS-shell work will move more capabilities behind reloadable module boundaries.

### Safety
- Validation alone is not enough to silently install code.
- Activation remains approval-gated.
- Failed validation never installs a candidate.
- Failed upgrade activation rolls back to the previous module.

---

## 7.5.11.2 — Hub Edit Mode Activation Fix
**17 September 2026**

### Fixed
- **Edit Layout now actually enters direct edit mode.**
- Root cause: PySide6 `QPushButton.clicked` emits a boolean. In 7.5.11.1 the non-checkable Edit Layout button emitted `False`, and `toggle_hub_edit_mode(force=None)` interpreted that as an explicit `force=False`.
- The Edit Layout button is now checkable, so the click emits the real desired state: checked = edit mode on, unchecked = edit mode off.
- Button text and checked state stay synchronized when edit mode is entered from the command palette or Hub Manager.

### Added
- **Edit Hub Directly** inside Manage Hub as a second obvious entry point into drag/drop + corner-resize editing.

---

## 7.5.11.1 — Direct-Manipulation Hub Edit Mode
**17 September 2026**

### Hub editing now works like a desktop launcher
- **Edit Layout** is now an in-place Hub mode instead of opening the management dialog.
- Drag an app tile and drop it on another grid location to move it.
- Drag **any of the four glowing corner handles** to resize the tile.
- Resize previews snap to Apollo's grid before the layout is committed.
- Tiles support custom sizes from 1×1 through 4×4, not only the old Small/Medium/Wide/Large presets.
- Dragging a tile into another existing Hub section moves it to that section.
- Collision resolution moves surrounding tiles to free cells; direct manipulation never persists overlapping tiles.

### Shell state v2
- Hub state now stores `grid_row`, `grid_col`, `row_span`, and `col_span`.
- 7.5.11 layouts migrate automatically from named sizes to spans.
- Preset sizes remain available in Hub Manager as an accessibility/fallback control.
- Edit mode is layout-only: dragging/resizing does not install, uninstall, enable, or disable apps.

### OS-shell direction
- This is the first direct-manipulation surface for Apollo OS. The same grid primitives can later support live widgets, Mission tiles, task progress, system monitors, and richer responsive layouts.

---

# Apollo Patch Notes

This file is the source used by **Settings → Patch Notes**.

The view reads this file directly from Apollo's installation folder. You can
press **Reload Notes** after editing the file, or **Open Notes File** to open
the same file in Windows.

---


## 7.5.11 — Apollo OS Shell Foundation + Custom Hub
**16 September 2026**

### OS shell backbone
- Added `apollo_shell.py`: a UI-independent Apollo app registry and crash-resistant Home/Hub layout store.
- Core Apollo pages and installed UI-capable modules now have stable logical app IDs (`core.chat`, `module.file_manager`, etc.).
- Added a shell router in the main window so Hub tiles can launch core pages or module apps through one path.
- Added additive `ui_surfaces` state to Module Manager while preserving the old `none/apps/sidebar` compatibility API.

### Custom Hub
- Replaced the old hard-coded launcher cards with a persistent **Pinned Apps** shell surface.
- Four logical tile sizes: **Small 1×1**, **Medium 2×1**, **Wide 3×1**, **Large 2×2**.
- Logical grid packing avoids absolute pixel positions and safely reflows within Apollo's window.
- Apps can be grouped into named Hub sections.
- Default layout includes core Chat/Workshop/Medical/Memory/System/Modules plus File Manager and Neural Visualizer when available.

### Hub Manager
- New **Manage Hub** UI: pin/unpin apps, resize tiles, move apps up/down within their section, change section names, refresh the catalogue, and reset the default layout.
- Removing a tile from Home never uninstalls or disables the underlying app/module.
- Disabled modules remain visible in Hub Manager but cannot be launched until enabled.
- Uninstalled/missing pinned apps are hidden from Home instead of leaving a broken launcher; their layout record remains recoverable/removable in Hub Manager.

### Persistence and recovery
- Hub layout is stored at `storage/shell/hub_layout.json`, separate from window state and module installation state.
- Atomic file replacement protects layout writes from partial-save corruption.
- Corrupt layout JSON is preserved as `hub_layout.corrupt-<timestamp>.json` and Apollo regenerates a safe default instead of failing startup.
- Duplicate app display names are safe because routing uses stable app IDs rather than titles.

### Play-test focus
- Pin/unpin, resize, reorder and section changes.
- Restart Apollo and verify the exact logical layout survives.
- Disable/re-enable a pinned module.
- Remove a pinned module and confirm the Hub remains usable.
- Reset the layout and verify no apps/modules are uninstalled.

---

## 7.5.10 — Module Compiler Repair + Deterministic UI Fallback
**15 September 2026**

### Fixed
- The compiler now sends the exact invalid Python source back during syntax repair. 7.5.09 reported the SyntaxError but did not include the broken source in the next repair request.
- Syntax repair includes numbered lines around the failing line and uses up to five bounded attempts.
- Repeated identical invalid generations are detected.

### Deterministic project adapter fallback
- If source-backed conversion still cannot produce valid generated Python, Apollo can build a syntax-guaranteed UI adapter around the real Workspace project.
- The adapter discovers real public functions at runtime, exposes `list_functions` and `run_function`, and creates a PySide6 Apps UI with dynamic fields from function signatures.
- It calls the actual project code rather than inventing replacement calculation logic.
- It remains pending until validation and user approval.

---

## 7.5.09 — Project-to-Module Compiler + UI Authoring
**15 September 2026**

### Fixed
- **"turn it into a modual with ui so i can use it within this program"** is now a real module-authoring command, not a tutorial request.
- **"do it"**, **"do that"**, **"go ahead"**, **"build it"** and similar short continuations recover the previous meaningful request.
- Invented raw tool JSON such as `{"name":"turn_into_module",...}` is suppressed even when the fake tool name has no dot or `__`.

### Project-to-module compiler
- Apollo resolves the active real Workspace project and reads its actual files before conversion.
- The real project snapshot is supplied to the deterministic module compiler with instructions not to invent unrelated ML/demo functionality.
- The pending module preserves the project's real logic/validation, exposes useful Apollo tools, and leaves the original Workspace project untouched.

### UI authoring
- Module Factory 1.1 accepts optional UI metadata and writes `manifest.json` UI configuration.
- UI conversions require `build_ui(parent=None, ui_context=None)` and default to Apollo Apps.
- PySide6 imports are required inside `build_ui` so module import/validation stays headless-safe.
- Converted modules remain pending until validation passes and the user approves them.

---

## 7.5.08 — Conversation Recall + Real Retry
**15 September 2026**

### Added
- **Chat Memory Module 2.2** with a chronological recent-conversation timeline plus semantic retrieval of older relevant exchanges.
- Apollo restores a bounded recent chat context automatically when it starts, so previous conversation can guide follow-ups after a restart without repainting old messages into the current UI.
- New `conversation_context` capability combines recent and relevant past exchanges under one context budget.
- New `previous_user_request` capability finds the last meaningful request while skipping greetings, acknowledgements and retry phrases.

### Fixed
- **"try again" now retries the previous meaningful request** instead of producing a generic acknowledgement.
- Existing-project edits, File Builder creation requests and Module Factory creation requests can recover their previous request from persistent conversation memory when visible chat history is missing.
- Normal Chat now receives both a recent chronological timeline and older semantically relevant conversation memory.
- Cross-restart continuity no longer relies only on in-memory `chat_history`.

### Context safety
- Previous conversation is bounded/truncated so old chats cannot consume the entire Ollama context window.
- Persistent recall contains stored user/Apollo exchanges, not hidden reasoning.

---

## 7.5.07 — Persistent Project Context
**15 September 2026**

### Fixed
- File Builder now remembers the active Workspace project in `storage/active_project.json`.
- Active project context survives Apollo restarts and patch installs because it lives in user storage.
- Follow-up coding requests no longer depend only on volatile in-memory chat history.
- Apollo matches real project names written naturally in a request, including **"add the GravityLab"**.
- If only one real Workspace project exists and there is no stronger context, Apollo can safely use it for a coding follow-up.
- File Builder adds deterministic `active_project`, `list_projects`, and `set_active_project` capabilities.
- Creating or inspecting a project updates its persistent active-project pointer.
- The misleading no-tool fallback no longer says the request was "stopped" when no tool actually ran.

### Why
7.5.06 could follow GravityLab during the same running chat. Installing/restarting Apollo clears that in-memory chat state while `workspace/GravityLab` remains on disk. 7.5.07 binds follow-ups to the real Workspace so the project survives the conversation process itself.

---

## 7.5.06 — Existing Project Follow-Ups
**15 September 2026**

### Fixed
- Follow-up coding requests now continue the most recent real Workspace project.
- After Apollo creates `workspace/GravityLab`, **"add a second calculator for escape velocity and make it accept the planet mass and radius"** is recognised as an edit to GravityLab without repeating its name.
- Apollo inspects the real project tree and reads current source files before generating an edit.
- Updates use the real File Builder, pin the destination to the existing project, write only changed/new files, and verify the entire project afterward.
- One automatic repair pass runs if static verification fails.
- Raw unexecuted tool-shaped JSON such as `{"name":"self_awareness.describe_project",...}` is no longer displayed directly in Chat.

---

## 7.5.05 — Real File Builds in Chat + Stable Responses
**15 September 2026**

### Fixed
- Plain Chat requests like **"I want to build a small Python project called GravityLab"** now enter the real File Builder path instead of returning tool-shaped JSON.
- `file_builder.write_files` is accepted as a local-model alias for the canonical `file_builder__write_files` tool when that tool is allowed.
- File Builder arguments are normalized when the model emits `project_name` instead of `project`, or a filename→content object instead of the required files array.
- **try again / retry** can recover the previous explicit project-build request.
- Generated code and internal File Builder JSON stay internal; successful builds return a concise completion/location/verification message unless the user asks to see code.
- Chat no longer rebuilds its full HTML transcript on every streamed chunk. A stable **Working…** card remains visible until the finished answer replaces it, removing the flashing/flicker.

---

## 7.5.04 — Module Authoring Compiler + Conversation Flow
**15 September 2026**

### Fixed
- Explicit Apollo module requests no longer depend entirely on a small local model successfully serialising a complete Python program inside a complex `create_candidate` tool-call JSON object.
- If native tool calling and strict JSON retry both fail, Apollo now enters a deterministic **Module Authoring Compiler** fallback:
  1. obtain simple module metadata,
  2. generate raw `module.py` source,
  3. parse Python locally and require `class Module`,
  4. retry source repair up to two times if syntax/contract shape is invalid,
  5. construct and execute the real `module_factory__create_candidate` call itself,
  6. run Apollo's normal candidate validator before reporting success.
- Short retry phrases such as **"try again"**, **"retry"**, and **"have another go"** deterministically recover the previous explicit module-build request instead of losing its intent.

### Added
- New built-in **Conversation Flow** module.
- Normal Chat automatically receives a compact deterministic continuity packet from recent visible chat history.
- Recognises short follow-ups/retries such as `try again`, `do that`, `same ...`, `what about ...`, and carries the previous visible user request forward.
- Conversation Flow performs no extra LLM call and stores no hidden chain-of-thought.

---

## 7.5.03 — Voice Imprint Lab
**15 September 2026**

### Added
- New **Voice Imprint Lab** module.
- Import WAV/MP3/M4A/M4B/FLAC/OGG/OPUS/WMA voice-source tracks through ffmpeg.
- Rights/permission confirmation gate before voice data can be imported.
- Automatic 24 kHz mono conversion, speech/silence segmentation and clip quality scoring.
- Local NumPy acoustic autoencoder: **64 → 48 → 16 → 48 → 64**.
- Saves a 16-dimensional speaker/style signature, consistency metric and representative reference clip.
- Optional offline/local faster-whisper transcription for future fine-tuning manifests.
- Optional **local XTTS** reference-conditioned neural synthesis backend. Apollo does not download models/packages automatically.
- Activate/deactivate a Voice Imprint profile as Apollo's preferred voice.
- Apollo's normal `speak_text` and `save_wav` routes to an active neural Voice Imprint when available, with automatic fallback to Windows System.Speech if the optional backend is missing or fails.
- Prepared datasets can be exported for future TinyVoice training.

### Architecture
- The custom autoencoder learns the acoustic identity/style signature.
- A pretrained local neural TTS backend performs text-to-waveform generation using the selected reference voice.
- This avoids pretending a small audiobook dataset can train a high-quality TTS model from scratch.

### Voice-data rule
Use only recordings/voices you own or have permission/licensing to use for synthesized speech.

---

## 7.5.02 — Dual-Pane File Manager + Close Button
**15 September 2026**

### Added
- In-app **✕ Close Apollo** button in the top-right header.
- Close button uses Apollo's existing clean shutdown path, including UI-state save,
  speech stop, worker wait, memory close and clean-shutdown marker.
- File Manager is now **dual-pane**: left and right panes can browse completely
  different roots/folders simultaneously.
- Drag files/folders from one Apollo pane to the other to **move the real OS item**.
- Drop files/folders from Windows Explorer into either pane to **copy/import** them.
- Apollo file drags also expose normal local-file URLs so they can be dragged out
  toward the OS/file explorer where supported.
- Multi-select move/copy buttons for either direction.
- Shared text preview/editor beneath both file panes.
- New File Manager capabilities: `copy_item` and `import_external`.

### File safety
- Internal pane-to-pane drag is a real move on disk; Apollo and Windows remain synchronized.
- External Explorer drop copies by default so the original outside file is not silently removed.
- Name conflicts on Explorer imports receive `_copy_2`, `_copy_3`, etc. instead of overwriting.
- Apollo core files remain protected from direct move/delete.
- Trash remains recoverable.

---

## 7.5.01 — Patch Notes View
**15 September 2026**

### Added
- New **Settings → Patch Notes** tab.
- Patch notes are loaded from the root `PATCH_NOTES.md` file.
- **Reload Notes** button refreshes the view without restarting Apollo.
- **Open Notes File** opens the real notes file through Windows.
- Graceful missing-file/error handling.

### Changed
- Settings now contains:
  - General
  - Patch Notes
  - Apps

### Compatibility
- No database migration.
- No storage migration.
- No model changes.
- No module permission changes.
- Existing Workspace, Memory Bank, Pile cache, voice dataset and configuration
  remain untouched.

---

## 7.5.0 — Coordination & OS Integration

### Major additions
- Apollo File Manager backed by the real OS filesystem.
- Misplaced-file detection and recoverable Apollo trash.
- Memory Distillation for Pile → Memory Bank learning.
- Context Manager for compact cross-model coordination.
- Persistent Task & Goal Engine.
- Verification Engine.
- Capability Graph.
- Knowledge Graph.
- Activity Trace.
- Benchmark Suite.
- Upgrade History/checkpoints.
- Background Intelligence maintenance pulse.
- Safe / Normal / Developer permission profiles.
- Repeated-crash module quarantine.
- Specialist model profiles for General, Coding, Reasoning, Fast and Vision.
- Isolated Python environments through Dependency Manager.
- Multi-file, approval-gated Self-Improvement proposals.
- Planner → Executor → Verifier guidance for substantial work.

### File handling
- File Manager reads and changes real files on disk.
- Cross-root moves update Windows immediately.
- Apollo core files remain protected from direct move/delete.
- `scan_misplaced` reports likely wrong locations without silently moving them.

---

## 7.0.1 — Forced Module Build Routing Fix

### Fixed
- Module creation requests from normal Chat, Coding Workspace, Apollo Workshop and
  Self-Improvement Workshop now route through the real Module Factory workflow.
- Prevented Apollo from satisfying a module-build request with explanatory code
  blocks instead of real pending-module files.
- Removed reliance on the imaginary `module_factory__validate` tool; candidate
  validation is handled by Apollo automatically.

---

## 7.0 — Apollo 7 Core

### Added
- Shared Action Bus.
- Event Bus.
- Persistent shared blackboard.
- Capability registry.
- Permission gate.
- Task journal.
- Notifications.
- Recovery snapshots and crash detection.
- Safe-mode foundation.
- Automation Engine.
- Orchestrator.
- Self-Improvement Lab foundation.
- Dependency Manager.
- Workspace Manager.
- Process Manager.
- Screen/Vision foundation.
- Device/serial bridge.
- Model Runtime.
- Terminal Bridge.
- Voice-agent foundation.

---

## 6.6.25 — Workshop + Natural Voice Foundation

### Added
- Natural / Precise / Expressive speech modes.
- Dictation audio dataset recording foundation for future TinyVoice training.
- Multi-file Workshop project creation.
- Real-file routing for coding/build requests.
- Apollo capability export.
- Approval-gated self-improvement workflow.

---

## Notes for future releases

For every Apollo patch, append a new section at the **top of the release history**
beneath this introduction. The Settings view will show it automatically; the UI
does not need another code change just to display new notes.
