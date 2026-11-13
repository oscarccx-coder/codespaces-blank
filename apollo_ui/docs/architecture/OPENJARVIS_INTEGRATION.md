# Apollo / OpenJarvis integration

Date: 13 November 2026. Apollo baseline: `4a3a478eab958cb566dc0dc4f067a2cec31272ad`.
OpenJarvis source: `13706f2b5b5ba6cac9ad31bc575d9e115213784f`.

## Result and scope

The full upstream source is retained as a pinned Git submodule, with its
license, native implementations, original frontend and tests. Apollo directly
uses the upstream agent classes, tool executor, skills, routing and execution
trace implementation. These are executable code paths, not simulated results.

Apollo keeps its own identity, Qt interface, Ollama connection, tool permissions,
shared knowledge bank, Foundry, missions and release system. The new runtime is
an additional execution backend for Chat and an app in Apps → OpenJarvis.

## How to use

1. Update Apollo from `main`.
2. Open Apps → OpenJarvis → Set up / repair, or run
   `Setup/19_SETUP_OPENJARVIS.bat` once.
3. Check readiness. Ollama must be running and the configured local model must
   already be installed. Setup does not download model weights or change the
   existing Ollama model directory.
4. Enter a task and choose Do task. Once setup is ready and the Chat toggle is
   enabled, ordinary tool-enabled Chat can also use this execution backend.
5. Use Stop to cancel generation. An in-flight Apollo tool is allowed to return
   its receipt; completed side effects are not silently undone or replayed.

Chat also recognises `openjarvis status`, `openjarvis runs`,
`openjarvis capabilities`, `openjarvis skills`, and `openjarvis do: <task>`.
Temporary/Tools-off chat keeps its existing model-only execution path.
Research and explicit Foundry/mission workflows retain their dedicated paths.

## Code and data map

| Component | Integration |
|---|---|
| Entire upstream source | `vendor/openjarvis`, pinned by `.gitmodules` and lock file |
| Interpreter and prerequisites | `tools/setup_openjarvis.py`; isolated `storage/environments/openjarvis` |
| Process and request broker | `apollo_openjarvis.py` |
| Actual upstream execution | `openjarvis_worker.py` |
| Qt app and chat tools | `modules/openjarvis`, `apollo_openjarvis_ui.py` |
| Scoped chat routing | `apollo_openjarvis_chat.py`, `workers.py` |
| Task records and tool receipts | `storage/databases/openjarvis_runs.db` |
| Upstream execution traces | `storage/openjarvis/traces.db` |
| Proposed learned routing | `storage/openjarvis/routing_candidate.json`; not auto-adopted |
| Shared knowledge | Existing Apollo Memory Bank through the broker |
| Ongoing missions and engineering | Existing Learning Missions and Foundry tools |

## Execution contract

The worker receives a bounded subset of real Apollo tools and the current
chat's actual context. Its model requests return to Apollo's local Ollama
client. Tool calls return to `manager.execute_tool` and the existing runtime
permission gate. It cannot grant permissions, pick a remote endpoint, call its
own agent recursively, or execute generated Python on the host. Native/direct
execution agents and hybrid/cloud agents that require separate adapters are
reported as unavailable rather than silently executing outside Apollo.

Upstream iteration and duplicate-call guards are retained. Apollo additionally
enforces a 28-tool-call budget, a run deadline, bounded protocol frames and one
OpenJarvis run at a time. Cancellation closes this run's model connection and
worker. A blocked or failed tool prevents a successful completion receipt and
the chat reports the failure rather than repeating a false success claim.

Every run has an ID, state, final result and tool checkpoints. Explicit recovery
marks interrupted work without replaying possibly completed writes. Resume is
currently a new reviewed run: automatic exactly-once resumption is not claimed.

## Readiness and optional capabilities

| Area | Current integration state |
|---|---|
| Core local agent execution | Implemented; real upstream orchestrator and simple-agent integration tested |
| Native ReAct and other tool-oriented agents | Available through upstream registry, subject to their prerequisites and broker restrictions |
| Apollo file and arithmetic tools | End-to-end tests exercise real tools and real permission denial |
| Model routing | Actual upstream heuristic policy exposed; no forced model replacement |
| Traces and route proposals | Actual trace store/analyzer and learned policy, candidates only |
| Skills | Full upstream skill catalogue; execution requires matching granted Apollo tool names/capabilities |
| Knowledge and research | Apollo's existing memory/research tools; no separate personal-memory duplication |
| Persistent research and scheduling | Apollo's existing mission/workflow services; no second scheduler automatically started |
| Code execution | Apollo Foundry's existing container-only boundary; direct upstream host execution denied |
| Original OpenJarvis frontend | Source included; Apollo uses its existing Qt app rather than starting a second web server |
| Cloud engines/accounts and messaging channels | Source included; not automatically connected or allowed to transmit data |
| Native retrieval, additional engines and training | Source included; optional dependencies/native builds and separate evaluation required |
| Self-modification and production policy adoption | Existing human-approved Foundry/release process remains authoritative |

## Setup profiles

Default setup installs only the dependencies needed for the bridged core into
the isolated environment, on the drive containing Apollo. Python 3.10–3.13 is
supported by this upstream pin. A Python 3.14 GUI does not have its environment
replaced: setup looks for a compatible Python installation.

`--full` adds the optional upstream research/server/learning packages selected
by the installer. `--native` builds its Rust extension and requires Rust plus
the platform linker. Neither option connects accounts, starts autonomous jobs,
trains weights, or changes Apollo's active model by itself.

## Performance strategy

Keep one model warm for 15 minutes during integrated tasks, cap agent output,
bound the tool catalogue to relevant candidates, and retain Ollama loading and
prompt timing alongside generation timing. Ordinary conversation can use the
simple agent for streamed delivery. This is not a promised speedup: compare
cold load, warm first response, total duration, output tokens/second, RAM/VRAM,
tool correctness and failed-task rate on the owner's 12 GB VRAM / 24 GB RAM PC.

## Remaining rollout plan

1. Run the regression suite and Windows/Linux integration CI before release.
2. On the owner's PC, run setup and readiness, then verify real Ollama tasks,
   Home activity updates, Stop and restart recovery.
3. Benchmark the same task set against the previous backend before changing
   model/context defaults.
4. Add explicit mappings for remaining imported skill tool names and native
   adapters; test each before marking it ready.
5. Expand optional engines, sandboxed coding adapters, distributed execution
   and training only when their actual dependencies and acceptance tests pass.

Do not describe the whole OpenJarvis capability surface as validated on this
PC merely because its complete source and registries are present.
