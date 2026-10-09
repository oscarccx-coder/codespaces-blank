# Apollo 7.5.13.2: Module Consolidation & RAM Optimisation

## Audit and decisions

The current Apollo repo had **50 installed feature modules plus one template**.
Not all should be separate applications. Core tool interfaces are identified by
module/action IDs, so deleting overlapping implementations would break callers
and user knowledge. This release changes *presentation and runtime cost* first.

| Canonical surface | Consolidated functions | Legacy outcome |
| --- | --- | --- |
| Voice Center | Windows fallback speech, XTTS/Voice Imprint, tuning, GPU unload | Old separate voice UIs stay hidden, engines stay loaded |
| Control Center | Permission controls, recovery, GPU/VRAM status, activity/errors, notifications | Separate backends retained; linked panels visible as tabs |
| Memory Bank | Named memory CRUD, memory health/age/conflicts, Knowledge Graph search | All persisted stores and tools kept |
| Apps → Coding | Workspace, model routing, tasks, self-improvement | Specialist agents/verifiers remain in Advanced |
| Apps → Memory & Learning | Memory Bank, research/training, knowledge cache | Web backends and distillation preserved |
| Apps → System | Control Center, dependencies, GPU monitor | Diagnostics accessible without crowding everyday apps |
| Apps → Advanced | Neural experiments, fleet/cluster/device agents, workflow internals, update history, specialist tools | Available on demand, not removed |
| Apps → Everyday | Voice Center, vehicle diagnostics, file manager, notifications, To-Dos | Prior module IDs and user custom pins preserved |

**Module execution is untouched.** UI filtering only hides list entries;
it does not disable modules, prevent existing APIs from executing or rewrite
the saved Hub/Sidebar layouts. Already-hidden standalone Voice Imprint and
Voice Studio remain hidden, while their engines are used inside Voice Center.

## Startup optimisation

Before: `rebuild_module_ui` constructed every Settings → Apps widget during
startup and on `open_module_app`. Voice Imprint, training and neural graphs
can be substantial views. Repeated builds unnecessarily consume GUI objects.

Now: the app catalog is a lightweight list. Only explicitly pinned **sidebar**
module pages are constructed during the rebuild. Settings app pages are created
on first open, kept available in the local cache, and torn down on normal UI
rebuilds. Opening a module no longer forces a full catalog/UI rebuild.

Recommended usage: pin just a few frequently used sidebar apps. Hide
everything else under its Settings → Apps category.

## Retired old helpers

These are **inert deprecation stubs**, not executable legacy repair code:

- `APPLY_XTTS_HOTFIX_AND_RUN.bat` (hard-coded old F: Apollo path)
- `finish_manual_xtts_install.bat` (old hard-coded Python/model assumptions)
- `finish_manual_xtts_install_v2.bat` (old hard-coded Python/model assumptions)
- `publish_current_release.bat` (old local-server release packaging path)

They show the replacement and exit with errorlevel 2. No model files are
deleted; the old implementations remain recoverable from Git history.

Canonical current scripts are `install_xtts_v2.bat` for an explicitly
requested environment reinstall and `UPDATE_APOLLO_CODE.bat` for incremental
source updates. For future signed GitHub release publishing use
`tools/publish_github_release.py`; **publishing is still manual and deliberate**.
The local update server is kept as an optional LAN option until after a real
GitHub Release update/restart/rollback test.

## Using the extra system RAM with Ollama

Settings → General → **Ollama RAM / Context** lets the user choose:

| Mode | Context tokens | Evaluation batch | Keep model resident |
| --- | ---: | ---: | --- |
| Balanced | 8,192 | 256 | 5 minutes |
| More Context | 16,384 | 128 | 10 minutes |
| Large Context (experimental) | 32,768 | 64 | 5 minutes |

These values are passed to Ollama's official `/api/chat` API as
`options.num_ctx`, `options.num_batch` and `keep_alive`; persisted in
ignored `storage/state/user_config.json`. They do **not** change the model
weights, use disk as VRAM, or force GPU layers onto the CPU. Ollama decides
CPU/GPU split and available memory. Models which do not support these sizes
may reject them, load more slowly or require partial CPU inference.

Apollo displays actual currently available system RAM if `psutil` is present.
Its client also supports **read-only** `/api/ps` inspection of current model
size and VRAM residency. The calculated difference is a rough loaded-model
RAM estimate, not measured OS process private bytes.

### For a Ryzen 5 / RTX 3060 12 GB / 32 GB RAM

Use **More Context** only if conversation/context needs exceed 8K and the
machine has sufficient free RAM. Try a coding prompt with 8K and then 16K,
measure response speed and `ollama ps` CPU/GPU percentages, and reduce the
context if GPU offload or speed regresses. More RAM does not make tokens
faster by itself.

On the current dedicated CUDA machine, allow XTTS GPU/VRAM alongside Ollama.
Avoid concurrently launching multiple huge Ollama models and XTTS to reduce
out-of-memory errors.

## Not retired, pending future dependency-safe consolidation

- Training Module and Web Explorer expose overlapping searching operations but
  use separate safety and research/storage paths. Keep both until merged APIs
  have contract tests.
- Knowledge Graph, Memory Distillation and Memory Intelligence retain existing
  DBs/source metadata; they are now reachable through Memory Bank without
  deleting schema.
- Context Manager, Conversation Flow, Orchestrator and Task Engine have
  overlapping coordination responsibilities but existing integration contracts.
  Keeping the engines is safer than pretending one already implements all.
- Experimental Neural Learning and Neural Visualizer are **not** Ollama's LLM.
  They are available in Advanced, and can be disabled manually if unused.
- Fleet/Cluster/Device Agents are kept in Advanced because distributed Apollo
  remains a future goal. Do not remove until their authenticated networking,
  scheduling and state dependencies are mapped.

No deletion/rewrite of local memory databases, projects, trained voices,
personal state, XTTS model folders or Git history is part of this release.

## Tests and verification

GitHub Actions covers lazy UI structure, category visibility, existing-module
preservation, Control Center/Memory Bank integration, safe Ollama settings,
user-config persistence, updated source syntax, plus the previous voice/updater
and OBD regression suites. Hardware/GPU load, actual Windows startup speed,
Ollama tokens/s and full PySide6 interactivity must still be tested on PC.
