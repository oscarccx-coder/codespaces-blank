## 7.5.12.10 — Clean XTTS Runtime Stack
**24 September 2026**

### Fresh dependency install
- XTTS installation now removes the old/conflicting Torch/Coqui/Transformers runtime before installing anything.
- The installer no longer attempts to adapt to arbitrary future PyTorch versions such as 2.14.
- Apollo now installs one known runtime stack in dependency order:
  - torch 2.11.0 (CUDA 12.8)
  - torchvision 0.26.0
  - torchaudio 2.11.0
  - torchcodec 0.16.0
  - coqui-tts 0.27.5
  - transformers 4.57.6
- PyTorch family packages are installed from the official PyTorch CUDA 12.8 wheel index.
- `--no-cache-dir` / forced reinstall is used for the critical runtime packages to avoid stale wheels.

### Installation order
1. packaging tools
2. uninstall conflicting runtime
3. shared FFmpeg
4. pinned PyTorch GPU family
5. pinned TorchCodec
6. Coqui-TTS
7. Transformers pin last
8. full import + pip dependency verification
9. XTTS model download only if missing
10. Apollo Voice Imprint configuration

### Safety
- Existing speaker profiles are preserved.
- A complete XTTS model is preserved/reused rather than redownloaded.
- Model data is still stored under `%LOCALAPPDATA%\Apollo\models\voice\xtts_v2`.
- Apollo now reports exact installed-vs-expected XTTS runtime versions in readiness diagnostics.

---

## 7.5.12.9 — XTTS Windows Batch Quoting Fix
**24 September 2026**

### PyTorch detection
- Fixed the Windows `cmd.exe` quoting failure that caused the quoted Python executable path to be parsed as part of the command text.
- PyTorch major/minor detection no longer uses `FOR /F` around a nested quoted Python command.
- The installer now writes the Python result to a temporary file, reads it with `set /p`, validates the version format, and then selects the matching TorchCodec version.
- This specifically fixes errors like:
  `...python.exe" -c "import' is not recognized as an internal or external command`.

### XTTS installer
- All 7.5.12.8 TorchCodec, shared FFmpeg, C-drive model location, Transformers pinning, legacy model migration and readiness checks remain intact.

---

## 7.5.12.8 — TorchCodec + C-Drive XTTS Runtime Fix
**24 September 2026**

### TorchCodec fix
- Fixed the PyTorch 2.9+ Coqui failure requiring TorchCodec.
- XTTS installer now detects the installed PyTorch minor version and selects the matching TorchCodec runtime.
- PyTorch 2.9 uses TorchCodec 0.9.1; 2.10 uses 0.10.0; 2.11 uses 0.11.0.
- Installer verifies TorchCodec before importing Coqui/XTTS.
- On Windows, the installer can locate/install the shared FFmpeg DLL build required by TorchCodec and verifies the runtime before the large XTTS model download.

### C-drive model layout
- XTTS engine now defaults to `%LOCALAPPDATA%\Apollo\models\voice\xtts_v2`.
- Apollo itself can remain on F: while Python/TTS/model runtime assets live on C:.
- A complete legacy F-drive XTTS engine is moved to the C-drive model location rather than downloaded again.
- Voice Imprint model discovery now includes the C-drive Apollo model directory.

### Voice Imprint runtime hardening
- Voice Imprint now records and reuses the shared FFmpeg DLL directory so TorchCodec can load after Apollo restarts.
- Added Torch, TorchCodec and Coqui import diagnostics to Voice + Engine Readiness.
- Fixed the earlier standalone helper writing `backend_settings.json`; Voice Imprint actually reads `settings.json`.
- Existing accidental `backend_settings.json` is automatically migrated into the real settings file.
- `ready_for_xtts` now checks config.json, model.pth and vocab.json plus the actual Python runtime dependencies.

---

## 7.5.12.7 — XTTS Runtime Compatibility + Installer Hardening
**24 September 2026**

### XTTS compatibility fix
- Apollo now ships `install_xtts_v2.bat` as the permanent XTTS installer/repair path.
- Coqui-TTS is pinned to 0.27.5 and Transformers is pinned to 4.57.6 for the current Apollo XTTS runtime.
- The installer explicitly verifies `transformers.pytorch_utils.isin_mps_friendly` before attempting XTTS.
- The installer verifies Coqui/XTTS imports before downloading the large model.
- Existing partial model downloads are retained when a download fails, instead of pretending installation completed.

### Voice Imprint integration
- Added **Install / Repair XTTS Engine** directly inside Voice Imprint Lab.
- Added `launch_xtts_installer` tool.
- Backend status now reports the installed Transformers version and whether it is compatible with Apollo's XTTS path.
- Voice Imprint continues to keep the speaker/reference pack separate from the shared pretrained XTTS engine.

### Apollo Python/install reliability
- `install.bat` now validates that Python can import the built-in `encodings` module.
- `install.bat` stops immediately on pip/dependency/import failures; it can no longer print `INSTALL COMPLETE` after a failed Python command.
- `start_apollo_ui.bat` clears stale `PYTHONHOME`/`PYTHONPATH` values and selects a Python interpreter that actually passes a standard-library health check.
- Added `repair_apollo_python.bat`.

---

## 7.5.12.6 — One-Click Voice Build + XTTS Readiness
**18 September 2026**

### One-click voice workflow
- Added **Use This Audio → Build Voice**.
- Apollo now takes one selected audio file through local copy, 24 kHz mono normalisation, speech segmentation/quality scoring, acoustic-signature training, XTTS-ready speaker reference packing and profile activation.
- The workflow creates `voice_pack/reference.wav`, up to five ranked reference candidates and `voice_pack/voice_pack.json`.
- Standalone acoustic-signature training also refreshes the voice pack automatically.

### Clear XTTS engine boundary
- Voice-source audio creates the **speaker-specific** files; it does not recreate XTTS's pretrained `config.json` / `model.pth`.
- Backend/readiness output now clearly separates `speaker_voice_ready` from `xtts_engine_ready`.
- Missing-engine errors now explain that the speaker voice is ready and only the shared XTTS base engine is missing.

### Local XTTS discovery
- Added **Find Installed XTTS**.
- Apollo searches its configured model folder and common local Coqui/TTS cache locations for a folder containing both `config.json` and `model.pth`.
- If found, Apollo selects it automatically. No model is downloaded automatically.

### Test the extracted voice immediately
- Added **Play Extracted Reference** so you can hear the exact reference Apollo prepared even before the XTTS base engine is installed.
- Added `voice_readiness`, `find_xtts_model`, `play_reference`, and `build_voice_from_audio` tools.

---

## 7.5.12.5 — Voice Training Progress + Responsive Trainer
**18 September 2026**

### Voice Imprint training UI
- Training no longer blocks the PySide6 UI thread.
- Added a live training progress bar.
- Added explicit phases: Preparing, Training, Saving, Complete and Error.
- Displays current epoch / total epochs, live loss and elapsed time.
- The Train button and conflicting controls are locked while training is active.
- The result panel now reports when training starts instead of appearing frozen.
- Training failure restores UI controls and leaves a visible error state.

### Voice training runtime
- Added `training_status` so Apollo can inspect the live trainer state programmatically.
- Acoustic feature preparation reports progress before neural epochs start.
- Autoencoder training now exposes bounded progress callbacks without flooding the UI event loop.
- Concurrent Voice Imprint training runs are blocked to prevent profile/model corruption.
- Existing synchronous tool calls remain compatible; progress callbacks are optional.

---

## 7.5.12.4 — Fleet + Cluster Foundation + Personal Voice Mode
**18 September 2026**

### Apollo Fleet foundation
- Added **Apollo Device Agent**: authenticated LAN node identity/status service with an allow-listed worker API.
- Added **Apollo Fleet Manager**: enrol trusted devices, refresh online/offline state, group nodes and revoke/remove nodes.
- Device communication uses timestamped HMAC-SHA256 request signatures and replay protection.
- The Device Agent deliberately does **not** expose a remote shell or arbitrary Python execution.

### Apollo Cluster foundation
- Added **Apollo Cluster Manager** and task-parallel scheduler.
- Main Apollo can distribute independent allow-listed tasks across enrolled workers based on advertised capabilities.
- Initial worker tasks: ping, text SHA-256, JSON validation, Python syntax validation, workspace file hashing and local Ollama prompt subtasks.
- Parallel worker results include worker identity/status/evidence and are stored under `storage/reports/cluster/`.
- This is task parallelism, not model-layer splitting; later releases add isolated project snapshots, worker leases/reassignment and Verification Engine integration.

### Personal Voice Imprint mode
- Removed the mandatory recording/voice permission checkbox from Voice Imprint Lab for this personal/local Apollo build.
- `import_audio` no longer requires `rights_confirmed`.
- Existing profiles with or without the legacy rights field can train, activate and synthesize locally.
- New profiles are marked `personal_use_mode: true`; the old `rights_confirmed` field is retained only as non-blocking legacy metadata.

### Roadmap
- Added Fleet rollout, distributed snapshots, reassignment/verification and Development Mission cluster integration to the internal roadmap and future-feature blueprints.

---

## 7.5.12.3 — Update Service + Storage Layout
**18 September 2026**

### Signed Apollo updater foundation
- Added `Apollo Update Manager` as a Hub-pinnable app.
- Added signed release publishing, a lightweight LAN update server, staged download/verification and an external updater process.
- Development host can publish with `publish_current_release.bat` and serve releases with `start_update_server.bat`.
- Client devices configure one server URL/channel and can Check → Stage → Install + Restart without manually copying each patch.
- Release manifests use Ed25519 signatures and per-file SHA-256 hashes.
- Core update installation backs up changed files and automatically rolls back when post-install health checks fail.
- User `storage/`, `workspace/`, `pending_modules/` and configuration values are protected from package replacement.

### Storage layout cleanup
- Added `apollo_storage.py` and a categorized persistent-storage layout.
- Loose databases now live under `storage/databases/`.
- UI/module/runtime state lives under `storage/state/`.
- Caches, media, models, training data, environments, reports, backups, trash, updates and logs now have dedicated folders.
- Existing legacy paths migrate automatically before Apollo modules open their data.
- Conflicting legacy files are preserved under `storage/legacy_conflicts/` instead of being overwritten.
- Root runtime files such as `apollo_memory.db`, `ui_state.json`, `modules_state.json` and `apollo_error.log` migrate into storage automatically.

### Update rollout boundary
- 7.5.12.3 provides the signed package/client/server backbone for multiple devices.
- Central fleet status, staged remote rollout and policy control remain planned on top of this foundation.

---

## 7.5.12.2 — Roadmap Expansion + Future Blueprints + Docs Cleanup
**18 September 2026**

### Roadmap 2.0
- Expanded Apollo's internal roadmap through the Apollo OS preview.
- Added planned tracks for the App SDK, project templates, provenance/trust, compute management, vision, local image generation, Media Studio, recovery/security and OS discovery features.
- Existing `storage/roadmap/roadmap.json` files are automatically merged with new default milestones, preserving user/runtime status and summaries.

### Future feature blueprints
- Added machine-readable placeholders under `blueprints/future_features/`.
- Blueprints include target version, dependencies, planned tools and acceptance criteria.
- Added placeholders for VRAM / Compute Broker, Model Benchmark Lab, Experiment Lab, Vision Core, Image Core, ComfyUI backend, optional Diffusers backend, Media Studio, image edit/inpaint/variations, upscaling, Asset Library, Style / LoRA Manager, App SDK, Project Templates, Data Provenance, Trust Layer, Knowledge Provenance UI, Notification Centre, Secrets Vault, Dependency Snapshots, Recovery Console, Backup / Export, Global Search, Capability Discovery and Local Usage Analytics.
- These are inert blueprints, not installed modules. They are intended to be promoted through Module Factory and normal validation when implementation begins.

### Image-generation path reserved
- Roadmap now explicitly reserves the sequence: Compute Broker → Vision Core → Image Core → ComfyUI/Diffusers → Media Studio → Edit/Inpaint/Upscale → Asset Library → Style/LoRA.
- Apollo Roadmap can inspect blueprint metadata through `feature_placeholders` and `feature_placeholder`.

### Cleaner Apollo root
- Patch history moved to `docs/patch_notes/`.
- Historical `PATCH_README*.txt` files no longer clutter the main Apollo script directory.
- Added `apollo_docs.py` to own patch-note paths and safely migrate old root-level patch files on upgraded installations.
- Conflicting legacy root files are preserved under `docs/patch_notes/legacy_root_files/` rather than silently deleted.

---

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
