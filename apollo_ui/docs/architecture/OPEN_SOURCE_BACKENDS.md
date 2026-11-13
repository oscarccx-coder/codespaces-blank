# Open-source backends in Apollo's main abilities

This change adds adapters to Apollo's existing systems. It does not replace Apollo with eight separate applications or automatically install every backend. All upstream revisions and original licence files are recorded in `integrations/sources.lock.json` and `integrations/licenses/`.

| Upstream | Apollo entry point | Execution | Prerequisites beyond Python dependencies |
|---|---|---|---|
| hexgrad/kokoro | Voice Center / text_to_speech `speak_text`, `save_wav` | Private worker; default CPU; existing bounded speech queue | First-use model/voice assets; Windows audio playback; bundled English voice |
| SYSTRAN/faster-whisper | Existing dictation `_recognize_wave_file` | Private CPU int8 or explicitly selected CUDA worker | Selected Whisper weights; existing microphone capture uses Windows |
| docling-project/docling | File Manager `read_document` | Private worker, max 50 MiB and 100 pages | First PDF/OCR use downloads models; CPU by default |
| unclecode/crawl4ai | Web Explorer `fetch_url` / `explore_web` | Private Chromium worker | Playwright Chromium and OS browser libraries |
| browser-use/browser-use | `capabilities__browser_task` via chat/tools | Docker only, fresh profile, no host file mounts, 3 GiB / 2 CPUs / 256 PIDs | Working Docker daemon; locally running compatible model; explicit runtime permission and task domain list |
| getzep/graphiti | Memory Bank `index_temporal_memory`, `temporal_search` | Private worker with local model and embedding endpoint | Local Neo4j, credentials, local embedding model; lexical CPU reranking |
| assafelovic/gpt-researcher | Web Explorer `research_report` | Private bounded worker with local inference | Local embedding model; 1–8 supplied evidence URLs |
| ggml-org/llama.cpp | Existing chat client supports `/v1` server URLs; bounded benchmark tool | Separately started local llama-server; existing cancellable transport | CMake/C++ toolchain; CUDA toolkit for CUDA build; compatible GGUF model |

## Install and select

Update the source checkout, then open **Apps → Capability Backends** (also embedded in Voice Center) and install selected backends. The source checkout and each isolated Python environment live under Apollo's `storage/integrations/` on its installation drive. HF/Torch model caches and Playwright browser files also live there for normal workers. Docker image storage follows Docker's configured disk location.

The installer requires Git and Python 3.12 or 3.13. It fetches the exact upstream GitHub commit, checks the original licence hash, refuses modified checkouts, and records installed dependencies. No install/configuration action is exposed to the LLM. It never changes Apollo's main Python environment. Transitive packages are resolved during setup and recorded with `pip freeze`; the upstream source pins are not a complete transitive lockfile.

Windows examples from `apollo_ui`:

```bat
Setup\20_SETUP_CAPABILITIES.bat kokoro faster_whisper docling crawl4ai
Setup\20_SETUP_CAPABILITIES.bat graphiti gpt_researcher
Setup\20_SETUP_CAPABILITIES.bat browser_use
Setup\20_SETUP_CAPABILITIES.bat llama_cpp --cuda
```

A default CPU setup avoids adding GPU-resident models alongside the main LLM. CUDA use needs a corresponding CUDA dependency/build setup and owner selection in the page. Select speech, dictation and web backends only after installation. Existing choices remain available. First-use model downloads and external-service readiness can still fail after dependency installation; the page deliberately reports **installed**, not fully validated.

Browser Use 1.x executes generated Python. The Apollo adapter therefore refuses a host-process fallback. Its container has no Docker socket, host directories or user browser session mounted. A fresh profile does not inherit logins. Container networking includes access to the host model service; this is not a complete network isolation boundary. The upstream domain policy restricts browser navigation, not arbitrary generated Python network access. Keep consequential actions behind owner approval and use disposable sessions.

## Local memory and research

Graphiti is an explicitly indexed historical snapshot store. Apollo's existing Memory Bank remains the source of current named records. Indexing a numeric named-memory ID sends only that record; it does not import chat history. Reindexing a changed record produces a new snapshot. Local edits/deletions do not automatically remove historical graph snapshots. Temporal results must be reconciled with current named records before being treated as current facts.

Configure a local Neo4j URI/user in `storage/state/capability_backends.json`. Put its password in the untracked `storage/integrations/graph_credentials.json`:

```json
{"password": "YOUR_LOCAL_DATABASE_PASSWORD"}
```

The worker uses a local inference endpoint and the `embedding_model` setting (default `nomic-embed-text`). That model must exist in the local service. It uses Graphiti's extraction and graph search with a small CPU lexical reranker to avoid a second neural reranker. No remote model API keys are inherited by normal workers.

Research reports require supplied URLs, cap planning/search iterations and run within a wall-clock budget. Reports and citations are generated evidence candidates, not a guarantee of correctness. Original source URLs are retained. The local-model endpoint is fixed by owner settings; upstream cloud defaults are overridden. A llama.cpp server configured only for generation may not provide the separate embedding model required by memory/research.

## llama.cpp in normal chat

Build the pinned source with the installer, then start its printed `llama-server` command using a separately licensed GGUF model. Select **Use running llama.cpp server for Apollo chat**, then restart Apollo. The page discovers the actual server model ID and saves the previous URL/model for reference in `storage/integrations/previous_model_settings.json`. Restore the Ollama URL/model in Settings to switch back.

The existing chat client normalizes native tool-call arguments, supplies OpenAI tool-call IDs, consumes SSE streaming and keeps cancellation interruptible. `/v1` identifies an OpenAI-compatible endpoint. Unvalidated vision attachments are refused on this path. Speculative decoding is an optional llama-server configuration requiring suitable models and benchmarks; this integration does not enable it automatically or claim a speed gain.

## Execution records and resource limits

Heavy library workers run one at a time per Apollo process. A busy backend returns a visible error instead of loading more models. Each run writes an independent receipt with completed/failed/cancelled/interrupted state, timing, source revision (returned to callers) and output artifacts. Interrupted work is never automatically replayed. Chat cancellation stops its owned backend worker; it does not stop an unrelated run. The model-generated browser task additionally requires Apollo's high-risk permission gate.

Speech uses the existing latest-request queue. Stop invalidates queued speech, stops the current Kokoro generation and interrupts Windows playback. The worker unloads models when it exits; this conserves residency but means repeated calls may incur cold-load time. Persistent warm workers are a future measured optimization.

## Validation and remaining deployment checks

Core tests cover native-system routing, blocked actions, local/path validation, actual subprocess cancellation and saved receipts, historical-memory indexing inputs, owner UI startup and real HTTP/SSE/tool-call transport. A separate CI test installs the exact Docling Git revision and converts a real document. Tests distinguish optional environment skips from passes.

Maintainers must additionally validate real audio/microphone paths on Windows, first-use PDF/OCR model downloads, actual local inference and embedding quality, Neo4j ingestion/search, Chromium installation/crawling, Docker browser tasks and the C++/CUDA build on the owner's hardware. An adapter existing does not mean these optional systems are already installed or benchmarked there.

Original licences apply to upstream code and model assets separately. In particular, this pinned GPT Researcher checkout's root LICENSE is Apache-2.0 even though its package metadata says MIT; the original root licence is preserved here. No upstream code has been renamed as Apollo-authored code.

### Development verification for this change

The exact source pins were cloned and the seven Python projects installed/imported in isolated environments. A real Docling conversion preserved Markdown content. Kokoro generated a 4.35-second, 24 kHz British-voice WAV on CPU; faster-whisper tiny.en transcribed that WAV as “Apollo integration test, the laboratory is ready.” This validates one generated-speech round trip, not general recognition accuracy or Windows playback.

The Chromium binary download returned a truncated archive in the development environment. Docker, a local Neo4j/Ollama service and CMake/CUDA were unavailable there, so browser execution, graph ingestion, complete research reports and actual llama.cpp generation remain deployment checks. The local inference transport was exercised using real HTTP fixture responses, including tool calls and SSE. CI separately exercises Windows/Linux lifecycle/UI tests, the real source installer and pinned Docling conversion.
