# Apollo V6.2 — Automatic Pending-Module Repair

This build adds an iterative module development loop.

## What changed

Apollo can now:

1. Read the official Apollo module contract/template.
2. Create a module under `pending_modules/`.
3. Validate it immediately.
4. Read the exact compile/import/API/self-test/test failure.
5. Modify the pending module files.
6. Validate and run tests again.
7. Repeat until the module passes or the retry limit is reached.
8. Leave the passing module PENDING until you explicitly approve installation.

Apollo does **not** silently install repaired modules.

## Automatic repair from normal chat

When Apollo uses `module_factory__create_candidate` or
`module_factory__update_candidate_file`, ChatTask now immediately validates the
candidate and gives the validator result back to Ollama.

The model is instructed to continue repairing the candidate in the same tool
conversation until it passes.

## Repair existing broken/unimplemented modules

Open:

`Modules -> Pending / Not Yet Installed`

Select a broken module and press:

`Auto Repair + Test`

Apollo will use Ollama to:

- inspect the current candidate
- inspect Apollo's official module template
- read validation errors
- rewrite the candidate
- rerun validation/tests
- repeat up to 6 repair attempts

Every pre-repair version is copied under the candidate's hidden:

`.repair_history/`

folder.

## Files automatic repair may change

Only files inside the selected pending module:

- `manifest.json`
- `module.py`
- `tests.py`
- `README.md`

It cannot use this repair engine to modify:

- `main.py`
- `module_manager.py`
- other Apollo core files
- accepted/live modules

## Stronger validation

`module_validator.py` now checks:

- manifest JSON
- module ID
- every top-level Python file compiles
- entrypoint imports
- configured Module class exists
- `tools()` structure
- duplicate/invalid tool names
- parameter schema basics
- `run()` exists if tools exist
- optional `self_test()`
- optional `tests.py`

`tests.py` runs in another Python process with a timeout.

## Module factory tools

The module factory now exposes:

- `get_contract`
- `read_candidate`
- `create_candidate`
- `update_candidate_file`

`update_candidate_file` can repair:

- module.py
- manifest.json
- tests.py
- README.md

## Approval boundary

PASS does not mean installed.

The final state is:

`VALID - WAITING FOR APPROVAL`

You still have to press:

`Accept Valid Module`

before Apollo moves it into the live `modules/` folder.

## Install

Run:

`install.bat`

Then:

`start_apollo_ui.bat`


## V6.3 — No permanent CMD window

For normal use, double-click:

`Apollo.vbs`

This starts Apollo through `pythonw.exe` with no command prompt attached.

`start_apollo_ui.bat` also now launches Apollo detached and exits immediately,
instead of keeping a console open until the GUI closes.

Module validation and `tests.py` subprocesses use Windows hidden-process flags,
so validation should no longer flash or leave command windows open.

### Hidden error logging

Because `pythonw.exe` has no visible console, an unhandled startup/runtime
traceback is written to:

`apollo_error.log`

If Apollo ever fails to open, send that file when debugging.


# V6.4 — Memory + Neural Learning

This full build includes all previous V6.3 fixes plus two installed modules.

## Automatic persistent memory

`modules/chat_memory_module`

Every completed chat is stored locally in:

`storage/chat_memory_module.db`

Before each Ollama request, Apollo searches that database for relevant previous
exchanges and injects the best matches into the model context.

The module also exposes:

- `save_chat_memory`
- `search_chat_memory`
- `recent_chat_memories`
- `chat_memory_stats`

## Trainable neural network

`modules/neural_learning`

This is a real one-hidden-layer multilayer perceptron (MLP) implemented in pure
Python, so there is no PyTorch dependency just to start Apollo.

Persistent neural state:

`storage/neural_learning_state.json`

Open:

`Train / Learn -> Neural Learning`

Add examples such as:

- `make me a Python program` -> `coding`
- `fix this script` -> `coding`
- `hello Apollo` -> `greeting`
- `good morning` -> `greeting`

Use at least two labels, with several examples per label, then press:

`Train Neural Net`

When trained, Apollo automatically adds the strongest neural category prediction
to Ollama's context.

This small network does NOT replace or retrain Qwen. Ollama/Qwen remains the
main local LLM and can continue using the GPU independently.

## Launch without CMD

Double-click:

`Apollo.vbs`

Errors are still recorded to:

`apollo_error.log`


# V6.5 — Working Web Tab

The Web page is no longer a placeholder.

It now provides:

- Web search through the `web_explorer` module
- Fetch readable text from a URL
- Open a URL in the system browser
- Send fetched page/search content into Apollo Chat
- Background web requests so the UI does not freeze
- Apollo-chat access to the same web tools

Installed module:

`modules/web_explorer`

Tools:

- `web_explorer.search_web`
- `web_explorer.fetch_url`

The module uses Python's standard library and therefore does not require
`requests` or BeautifulSoup.

Some modern sites require JavaScript or actively block automated requests; those
pages may still need to be opened in the normal browser.


# V6.6 — Dynamic Module UI + GPU Monitor

## Module UI placement

Apollo modules can now optionally provide a Qt page.

Add this to `manifest.json`:

```json
{
  "ui": {
    "enabled": true,
    "title": "My Module",
    "default_placement": "apps"
  }
}
```

Then implement:

```python
def build_ui(self, parent=None, ui_context=None):
    from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

    page = QWidget(parent)
    layout = QVBoxLayout(page)
    layout.addWidget(QLabel("Hello from my module"))
    return page
```

In Apollo:

`Modules -> select module -> Selected Module UI`

Choose:

- Hidden / Tool Only
- Apps Page
- Sidebar Tab

Then press:

`Apply UI Placement`

Apollo stores the user's choice in `modules_state.json`.

## Apps page

The new Apps page lists every UI-capable module assigned to Apps. Selecting one
opens its module-built page inside Apollo.

## Sidebar modules

A UI-capable module can instead be promoted to its own direct sidebar tab.

## GPU Monitor

Installed module:

`modules/gpu_monitor`

It reads NVIDIA data using `nvidia-smi` and exposes:

- `gpu_monitor.gpu_status`
- `gpu_monitor.gpu_processes`

The System page now displays:

- GPU model
- GPU utilization
- VRAM used/total
- temperature
- power draw / power limit

The GPU Monitor module itself also has an optional mini-app page and defaults to
the Apps page. You can move it into the sidebar from Modules.

The UI refreshes approximately every two seconds.


# V6.6.1 — Fixed Research & Training Module

Installed:

`modules/training_module`

This module replaces the generated placeholder that only imported
`web_explorer`.

It now provides working web research, safe local research storage, validator-safe
tests, Apollo tool definitions, and an optional Apps/Sidebar UI page.

Default UI location:

`Apps -> Research & Training`


# V6.6.2 — Tool Loop Controller Fix

This build fixes requests ending with:

`Apollo stopped the request because the model exceeded the maximum number of tool-call rounds.`

## Root causes fixed

### Coding page/module conflict

The old Coding page always instructed Apollo to use `file_builder`, even when the
request was for a real Apollo extension module.

That conflicted with the safety rule that Apollo modules must use
`module_factory -> pending_modules -> validation`.

The Coding page now routes:

- ordinary projects -> `file_builder`
- Apollo modules/plugins/features -> `module_factory`

### Duplicate tool-call guard

Apollo fingerprints every tool name + argument object.

An identical call is executed only once. If Qwen tries to repeat the exact same
call, Apollo blocks it and moves to a final no-tools response.

### Batch project writing

`file_builder` now exposes:

`file_builder.write_files`

This lets Qwen create a whole multi-file project in ONE tool call.

Example:

- project: `neural_net_visual`
- files:
  - `index.html`
  - `README.md`
  - `app.js`

A successful batch write is considered terminal; Apollo immediately disables
tools and asks Qwen to give the user the final file list/run instructions.

### Module validation terminal state

When a `module_factory` create/update operation passes validation, tool execution
ends immediately.

Apollo cannot keep rewriting an already-valid candidate.

### Graceful tool budget

If the model still reaches the tool budget, Apollo no longer discards completed
work and returns only an error.

It disables tools and generates a truthful final summary from the actions that
actually completed.

### Smaller tool catalog for Coding requests

Coding requests no longer expose every installed Apollo tool to Qwen.

Ordinary coding generally sees:

- file_builder
- self_awareness

Apollo-module requests generally see:

- module_factory
- self_awareness

This substantially reduces tool confusion for smaller local models.


# V6.6.3 — Module Lifecycle Controls

The Modules page now supports moving and removing module folders without manual
File Explorer work.

## Installed modules

Select an installed module and use:

### Move Back to Pending

Apollo:

1. unloads the module
2. calls its optional `close()` method
3. removes its tools/UI from the live system
4. moves the entire folder from `modules/<id>` to `pending_modules/<id>`
5. immediately validates it as a pending candidate

The module can then be edited or repaired with `Auto Repair + Test`.

The user's module UI-placement preference is preserved for when the module is
accepted again.

### Remove Module

After confirmation, Apollo permanently deletes:

`modules/<id>/`

and cleans the module's enabled/UI-placement state.

Module-created data outside the module folder, such as databases under
`storage/`, is intentionally left alone.

## Pending modules

A new `Remove Pending` button permanently deletes the selected candidate folder,
including its `.repair_history` directory if present.

All destructive actions require an explicit confirmation dialog.


# V6.6.4 — Persistent UI + Real Learning

## Dynamic module UI fix

V6.6 had two wiring defects: the sidebar layout was not stored on the Apollo
window and the static sidebar did not include the Apps page. UI-capable modules
could therefore save a placement without reliably producing a usable button.

This build gives dynamic module tabs their own sidebar host, adds Apps to the
sidebar, removes stale module widgets/keys correctly during rebuilds, and
restores the current page/app after a rebuild.

## UI state is persistent

Apollo now writes `ui_state.json` atomically whenever the UI state changes.
It restores:

- window position and size
- current page, including dynamic module sidebar pages when still available
- currently opened module app
- selected installed module
- selected pending module

Module enable/disable and UI placement still live in `modules_state.json`, which
is now also written atomically.

## Neural learning V2

The auxiliary neural classifier no longer marks itself trustworthy simply
because a tiny training loop finished.

Training now uses:

- unigram + bigram text features
- at least 3 different examples per label
- stratified train/validation split
- multiple independent random restarts
- held-out validation accuracy/loss
- early stopping
- persistent training metrics
- a quality gate (`ready_for_use`)
- background training so the Apollo UI remains responsive
- live training progress in Train / Learn

Apollo chat only consumes neural predictions when the validation quality gate
passes and prediction confidence is at least 55%.

A tiny network can genuinely train quickly; duration is now reported rather than
artificially slowed down. What matters is the held-out validation score.

## Research learning is now real source reading

`training_module.explore_web_and_save` no longer saves only search snippets. It
searches the web, fetches readable text from up to five source pages, and stores
that source-backed research locally.

Apollo can search those saved research files with:

`training_module.search_local_research`

Relevant saved research is automatically injected into later Apollo chats, so
research becomes usable long-term knowledge instead of a file Apollo forgets to
look at.


# V6.6.5 — Closable Apps + Neural Fix

## Apps can now be closed and reopened

The Apps page now has:

- Open Selected App
- Close App
- an in-app `✕ Close` control
- a current-app indicator

Closing an app only closes the visible page. It does not disable, unload, move,
or remove the module.

Reopen it by selecting it in Apps and pressing Open Selected App, or by
double-clicking it.

Apollo persists whether an app was open or closed in `ui_state.json`.

## Neural Learning validator fix

Neural Learning V2 reports:

`pure_python_mlp_v2`

but its older tests still expected:

`pure_python_mlp`

That caused Apollo's module validator to reject a working module.

The test contract now matches the V2 backend.

## Neural Visualizer included in the full build

`modules/neural_visualizer`

is now included directly in Apollo, with default placement:

`Apps -> Neural Visualizer`

It reads:

`storage/neural_learning_state.json`

created by Neural Learning.

Train Neural Learning first, then open Neural Visualizer and enter text to inspect
active features, hidden-neuron activation, output probabilities and strongest
connections.


# V6.6.6 — Chat-Integrated Learning + Train UI Fix

## Train page compression fixed

The Train / Learn page is now inside a vertical `QScrollArea`.

Qt can no longer shrink the neural controls into tiny rows when the Apollo
window is not tall enough.

The duplicate neural-example fields were removed from the Train page. The full
neural editor remains available as the `Neural Learning` app.

## Main Chat is now the learning interface

Apollo performs deterministic persistent learning before Ollama answers when the
user explicitly teaches something.

Examples:

`remember that my circuit project uses a 12V supply`

-> stored in Apollo's core fact memory

`when I ask what model I use, answer Qwen 2.5 Coder`

-> stored as a preferred-response lesson

`learn this as coding: debug this Python program`

-> stored as a labelled Neural Learning example

`research and learn about multilayer circuit boards`

-> Apollo is instructed to use the Research & Training module from normal Chat,
store the research locally, and use it in later conversations

`train your neural network`

-> Apollo can invoke the Neural Learning training tool from normal Chat

The user does not need a separate learning conversation.

## Train / Learn page role

Train / Learn is now mainly a management/status page:

- explanation of chat-integrated learning
- manual preferred-answer fallback
- manual fact-memory fallback
- Neural Learning status
- Train + Validate button
- Open Neural Learning App
- Open Neural Visualizer

## Duplicate prevention

Exact duplicate preferred answers and facts are no longer inserted repeatedly
into Apollo's core SQLite memory.


# V6.6.7 — The Pile + Compiled Knowledge Base

Apollo now has:

`modules/pile_knowledge`

## What "The Pile" means here

Apollo does not download the entire corpus.

It searches the Parquet-backed uncopyrighted Pile mirror through Hugging Face's
Dataset Viewer REST API and stores only selected relevant passages locally.

Default remote dataset:

`monology/pile-uncopyrighted-parquet`

## Compiled knowledge

Selected knowledge is stored in:

`storage/compiled_knowledge.db`

Sources can include:

- The Pile search results explicitly learned by the user
- Research & Training files under `storage/training_module/`
- text explicitly added through the module

Normal Chat automatically searches this database before the Ollama/Qwen request.

## Examples

`learn from The Pile about PCB ground planes`

`search The Pile for transformer core saturation`

`what have you learned about multilayer PCB vias?`

## Knowledge Base app

Default:

`Apps -> Knowledge Base`

It can:

- search local compiled knowledge
- search The Pile online
- learn/compile Pile results
- sync existing Research & Training files
- show local knowledge statistics

## Web research fallback

Research & Training still tries DuckDuckGo HTML first.

If that provider returns no results or blocks the automated request, Apollo now
falls back to Wikipedia's public API instead of simply failing with no research
results.


# V6.6.8 — Pile Access Reliability Fix

This release fixes the exact failures shown by Apollo:

- `pile_knowledge__learn_from_pile`: timeout
- `pile_knowledge__search_knowledge`: SQLite cross-thread error
- Qwen falling through to unrelated `self_awareness` tools

## Fixed dataset ID

V6.6.7 used:

`monology/pile-uncopyrighted-parquet`

The current Hugging Face Dataset Viewer exposes the real dataset as:

`monology/pile-uncopyrighted`

Apollo now uses the correct id.

## Routed Pile searches

Apollo no longer begins every request against the enormous full mirror.

It routes the topic through smaller real Pile-derived subsets first:

- `timaeus/pile-github`
- `timaeus/pile-stackexchange`
- `timaeus/pile-arxiv`
- `timaeus/pile-hackernews`
- `timaeus/pile-wikipedia_en`
- `timaeus/pile-pile-cc`

Example:

`learn about AI coding from The Pile`

prioritizes Github, StackExchange and ArXiv.

The routed datasets are searched concurrently. A slow provider therefore does
not block all of Apollo's Pile access.

Only if the routed searches return nothing does Apollo try the full
`monology/pile-uncopyrighted` mirror.

## Thread-safe compiled knowledge

`compiled_knowledge.db` is now opened with cross-thread SQLite support and every
database operation is serialized with an `RLock`.

This fixes the error caused by the module being created on the UI thread while
Chat executes its tools on a worker thread.

## Strict Pile tool routing

When a user explicitly asks for The Pile, Qwen is only shown:

`pile_knowledge__*`

tools.

It can no longer respond to a failed Pile request by randomly calling
`self_awareness__describe_project`.

## Terminal learning state

When `learn_from_pile` successfully stores knowledge, Apollo immediately ends
the tool phase and returns a final summary instead of continuing to call tools.


# V6.6.9 — Forced, Source-Grounded Pile Commands

This fixes the case where:

`learn from The Pile advanced AI coding`

returned a generic ANI / AGI / ASI explanation.

That response was not reliable evidence that Apollo had actually used The Pile.

## Deterministic Pile routing

Messages such as:

- `learn from The Pile advanced AI coding`
- `search The Pile for transformer core saturation`
- `access the pile online about neural networks`

are intercepted by Apollo's controller.

Apollo executes the correct Pile tool **before Qwen can answer**.

Qwen can therefore no longer silently skip the source and answer the question
from its own model weights.

## No generic fallback

If the remote Pile lookup fails, Apollo now reports the actual error.

It does not substitute a generic AI explanation and pretend that it came from
The Pile.

## Relevance protection

Pile Knowledge v1.2 applies topic gates before accepting a passage.

For a query containing both AI and coding concepts, candidate text must contain
evidence of **both**.

That explicitly rejects the failure case where an ANI / AGI / ASI overview was
returned for `advanced AI coding` despite containing no programming material.

## Source-grounded response

Successful learning responses show:

- Pile subset (`Github`, `StackExchange`, `ArXiv`, etc.)
- row id
- an excerpt of the passage actually learned
- number of chunks stored
- number of unrelated hits rejected

The learned passages go into:

`storage/compiled_knowledge.db`

## Dataset Viewer limitation

The online source is:

`monology/pile-uncopyrighted`

through Hugging Face Dataset Viewer search.

Hugging Face can expose only a partial search index for datasets above its large
dataset threshold. Apollo now surfaces `partial=true` rather than claiming an
exhaustive search of the complete corpus.


# V6.6.10 — Resilient Pile Local Cache

The remote Hugging Face `/search` endpoint can time out on the enormous Pile
dataset.

Apollo now has a second retrieval path.

## Explicit learning flow

`learn from The Pile advanced ai codeing`

becomes:

1. normalize typo -> `advanced ai coding`
2. try online Hugging Face Pile search
3. if online search succeeds -> relevance gate -> compile knowledge
4. if every online failure is a timeout and no cache exists:
   - automatically download/resume one Lite Pile Parquet shard (~266 MB)
   - search it locally with DuckDB
   - relevance gate
   - compile accepted passages into `compiled_knowledge.db`

## Local cache

`storage/pile_cache/`

The Knowledge Base app now provides:

- Download Lite Cache (~266 MB)
- Add One Cache Shard
- Cache / Knowledge Stats

The ten current partial-preview Parquet shards total roughly 2.6 GB.

## Upgrade requirement

V6.6.10 adds:

`duckdb>=1.1`

to `requirements.txt`.

If updating an existing Apollo folder, run `install.bat` once before using the
local Pile cache.


# V6.6.11 — Memory Bank, Live Neural Hub and Persistent To-Do List

## Correct spelling

All new user-facing labels and tool commands use correct spelling.

The achievement command is:

`todo_list__achieve_to_do_list`

## Named Memory Bank

New module:

`modules/memory_bank`

Database:

`storage/memory_bank.db`

Apollo automatically creates named Memory Bank entries when it deliberately
learns useful source-backed information from:

- The Pile
- saved web research
- explicit facts taught in Chat
- preferred answers taught in Chat

Each memory stores its name, type, summary, full content, source, source
reference, tags, importance, learned date and updated date.

Normal Chat searches the Memory Bank automatically before Ollama answers.

## Live Neural Visualizer on the Hub

The Neural Visualizer now exposes a permanently active Hub panel.

Every normal Chat message is passed to the read-only `observe_text` action so
the Hub can show live neural input, hidden-neuron activity, output labels and
confidence without opening the separate Neural Visualizer app.

## Persistent To-Do List

New module:

`modules/todo_list`

Database:

`storage/to_do_list.db`

The To-Do List is editable directly on the Hub and is also available as an app.

Tools:

- `add_to_do_item`
- `remove_to_do_item`
- `update_to_do_item`
- `complete_to_do_item`
- `reopen_to_do_item`
- `list_to_do_items`
- `achieve_to_do_list`

Simple normal-Chat add/remove/list/tick-off commands are handled deterministically.

When the user asks Apollo to `achieve the to-do list`, Apollo first calls
`todo_list__achieve_to_do_list`, then attempts actionable work with real installed
tools. It only calls `complete_to_do_item` after the corresponding real action
succeeds. Manual, unsupported and failed tasks remain open.

## UI persistence

The final application shutdown handler now saves `ui_state.json` before closing,
fixing the later `closeEvent` override that could bypass the earlier UI-state
save routine.


# V6.6.12 — Pile HTTP 5xx Fallback + Circuit Breaker

The Hugging Face Dataset Viewer can fail with server-side errors such as:

`HTTPError: HTTP Error 500: Internal Server Error`

V6.6.10 only activated the automatic local-cache fallback for timeout errors.

V6.6.12 treats the following as remote-service failures:

- HTTP 500
- HTTP 501
- HTTP 502
- HTTP 503
- HTTP 504
- read/connect timeouts
- connection resets/refusals
- URL/network resolution errors

For an explicit:

`learn from The Pile ...`

request, any of those failures can activate the one-shard Lite local-cache
fallback.

## Circuit breaker

After a remote Pile service/network failure, Apollo marks the remote endpoint
temporarily unhealthy for 15 minutes.

During that period:

- Apollo does not repeatedly hammer the failing search endpoint.
- If a local Pile cache exists, it searches the cache first.
- The remote-health state is visible through Knowledge Base cache/status data.

This is in-memory health state and resets when Apollo restarts.


# V6.6.13 — Pile Technical Quality Filter

The Pile connection was working, but older matching logic admitted weak results
for `advanced AI coding in Python`.

Fixed:

- `ai` and `ml` now use real token/phrase boundaries instead of substring matches.
- Python is mandatory when Python is explicitly requested.
- Advanced requests require real AI/ML technical signals and implementation depth.
- XML/Crossref/DOI metadata dumps are rejected.
- Generic career/course material is rejected unless it contains substantial
  implementation-level technical content.
- Older compiled Pile chunks for the exact same query are replaced after a new
  successful filtered learning run.
- Memory Bank v1.1 replaces the existing same-name/source/type memory with the
  better version rather than keeping stale topic copies.

Technical signals include model training/inference, neural networks,
transformers, embeddings, attention, PyTorch, TensorFlow, scikit-learn,
gradients/loss/optimizers, testing/debugging, evaluation, data pipelines,
architecture, GPU/CUDA, APIs, agents, tool calling, vector search and RAG.


# V6.6.14 — Technical-Window Pile Precision

The remaining V6.6.13 problem was a generic Pile-CC article passing the
whole-document quality check because technical terms occurred somewhere later in
the document.

V6.6.14 scores local ~2.8k-character technical windows instead.

For `advanced AI coding in Python`, the accepted section must contain:

- Python
- multiple AI/ML technical signals
- multiple software/engineering signals
- multiple implementation/library/code signals

Examples of implementation evidence:

- PyTorch / TensorFlow / scikit-learn
- training loops
- inference
- model evaluation
- debugging / profiling
- data pipelines
- APIs
- GPU / CUDA
- architecture
- code syntax such as `def`, `import`, `class`, `torch.` or fenced Python code

Broad Pile-CC career/news material receives an additional penalty and is rejected
when it lacks real library/code evidence.

Apollo now learns the accepted technical window itself rather than the generic
start of the source document.

Remote query expansion is also more technical:

- original user query
- Python + PyTorch + model training + implementation
- Python + transformer + neural network + inference + evaluation + debugging

Apollo continues to the technical variants when the first query produces fewer
than three high-quality documents.


# V6.6.15 — Dynamic Pile Parquet Discovery

This fixes the failure sequence:

`HTTP 500 Internal Server Error`

followed by:

`HTTP 404 Not Found`

The 500 came from Hugging Face Dataset Viewer search.

The 404 came from Apollo's fallback downloader using a previously hard-coded
generated Parquet path.

Generated Dataset Viewer Parquet paths are no longer hard-coded.

## New fallback flow

When the remote Pile search is unavailable:

1. Apollo calls the documented Dataset Viewer `/parquet` endpoint for the
   current `monology/pile-uncopyrighted` Parquet catalog.
2. If that discovery endpoint fails, Apollo tries the Hugging Face Hub dataset
   Parquet API.
3. Apollo stores the discovered catalog in:

   `storage/pile_cache/parquet_catalog.json`

4. Apollo downloads the first current training/partial-training shard using the
   URL returned by Hugging Face.
5. If that returned URL later responds with HTTP 404, Apollo forces catalog
   rediscovery and retries the same logical shard once.
6. The downloaded Parquet is searched locally with DuckDB.

The catalog cache expires after 24 hours for normal discovery purposes.

## Cache files

Downloaded local shards remain:

`storage/pile_cache/0000.parquet`
`storage/pile_cache/0001.parquet`
etc.

The local filenames are stable even when Hugging Face changes its generated
remote paths.


# V6.6.16 — Curated Pile Learning

This fixes three issues visible after local Parquet fallback succeeded.

## 1. Advanced queries reject novice material

An advanced request no longer accepts sources containing phrases such as:

- complete beginner
- new to machine learning
- no knowledge about neural networks
- beginner tutorial

unless the same accepted technical section contains unusually strong executable
implementation evidence.

## 2. English usability filter

For a generic English learning request, a technical document dominated by a
different natural language is rejected unless it contains substantial executable
code and implementation evidence.

This prevents a largely Korean README from becoming a primary memory for a
generic `advanced AI coding in Python` request.

## 3. Local-cache excerpt bug fixed

The local Parquet path was still persisting a generic 7,500-character excerpt
even though relevance was judged using a ~2,600-character technical window.

That caused six accepted documents to become twenty overlapping compiled chunks.

V6.6.16 stores only the exact accepted technical window and stores one curated
knowledge record per accepted source.

Expected behavior is now closer to:

`6 relevant documents -> 6 curated knowledge chunks`

rather than:

`6 relevant documents -> 20 overlapping chunks`

## Local source references

Local Parquet results now receive stable locators such as:

`0000.parquet#1a2b3c4d5e`

instead of displaying `row None`.

## Better local pre-filtering

For an advanced Python AI request, DuckDB now requires Python plus AI/ML and
implementation-level terms before candidates reach the expensive Python
reranker. The candidate limit increases from 350 to 700 because the SQL filter
is much stricter.


# V6.6.17 — High-Signal Pile Curation

This update targets the remaining low-value results visible after V6.6.16.

## Link/catalog dump rejection

A GitHub "awesome list" or repository catalog can contain dozens of AI framework
names and therefore look highly technical to a keyword scorer.

Apollo now detects high markdown-link/list density and rejects navigation/catalog
windows that do not contain enough explanatory prose.

## Natural-language readability

The previous language ratio counted URLs, library names and code-like text.

V1.9 removes:

- fenced code
- inline code
- URLs
- markdown link destinations

before judging explanatory-language readability.

For an English advanced query, a non-English-dominant section now needs both
substantial executable code and enough English explanation to pass.

## Traceback/log dump rejection

Raw Python/TensorFlow/PyTorch tracebacks can contain many strong technical words
but provide little durable knowledge.

Traceback-heavy windows with too little explanatory prose are rejected. If the
same source contains a useful answer or explanation elsewhere, technical-window
selection can still choose that section instead.

## Active DuckDB prefilter bug fixed

V1.8 added a stricter `_local_sql_predicates` method, but an older definition
appeared later in the class and silently overrode it.

V1.9 places the final strict implementation at the end of the class, guaranteeing
that it is the active method.

For `advanced AI coding in Python`, local DuckDB candidates now require:

- Python
- AI/ML framework/topic evidence
- a framework/model family such as PyTorch, TensorFlow, scikit-learn, Keras or transformers
- an engineering/implementation signal such as training, inference, evaluation,
  debugging, optimizers, embeddings, architecture, GPU or CUDA

The expensive Python reranker therefore sees a much cleaner candidate pool.


# V6.6.18 — Whole-Source Pile Policy

Source policy now runs before local technical-window extraction.

For an advanced English Python-AI learning request Apollo rejects entire sources
when they are:

- GitHub repository/awesome-list catalogs
- question-only StackExchange posts
- explicit novice/learning-tool StackExchange material
- Hangul/CJK/Kana-dominant explanatory documents
- extreme traceback/log dumps

Only after a source passes that whole-document gate does Apollo search it for
the best ~2200-character technical section.

This prevents a locally technical fragment from rescuing an otherwise unsuitable
source.


# V6.6.19 — AI-Core Curation

Advanced AI relevance now separates model/learning concepts from framework names.

Core AI signals include neural networks, deep learning, transformers, language
models, model training, inference, attention, backpropagation, loss functions,
optimizers, fine-tuning, quantization and RAG.

Framework names such as PyTorch, TensorFlow, sklearn, numpy or pandas no longer
prove advanced AI relevance by themselves.

Strong executable AI code can still qualify with a framework plus substantial
code syntax and engineering evidence.

PubMed/biomedical material receives an extra domain-drift gate.

Whole-source Hangul/CJK/Kana filtering is stricter for generic English advanced
queries, closing the kor2vec README leak.

# V6.6.20 — Forced Real Module Creation

Coding Workspace requests that ask for an Apollo module/plugin are no longer
left to Qwen's tool-selection discretion.

Apollo now:
1. extracts only the text after `REQUEST:`;
2. detects module/plugin/pending intent from that real request;
3. executes `module_factory__get_contract` for real;
4. gives the model only the real `module_factory__create_candidate` tool;
5. retries once with Apollo's intercepted JSON tool-call format if native Ollama
   tool calling is not emitted;
6. validates the candidate immediately;
7. reports success only when real files exist and validation passes.

The full build also contains a ready-to-review pending `text_to_speech` module
using Windows System.Speech through PowerShell. It is offline-first and does not
use gTTS, Google services, Coqui/Torch, or macOS `afplay`.


# V6.6.21 — Voice I/O + Normal Chat Fix

## Normal chat no longer enters tool-JSON mode

A simple greeting such as `hello` now gets no tool catalog and no callable tools.
Apollo is explicitly told never to ask for function names/arguments in ordinary chat.
Tool families are exposed only when the current request clearly asks for an action.

## Apollo reply speech

Speech output is now driven by the Chat UI after Apollo finishes a response. The user's
input is never automatically spoken.

Chat controls:

- `Voice On` — Apollo automatically reads completed Apollo replies.
- `Muted` — disables future reply speech and immediately stops current Apollo speech.
- `Dictate` — listens once using the Windows offline speech recognizer and fills the
  Chat input box. It does not auto-send, so the user can correct recognition first.

## Speech I/O module v1.1

The installed module id remains `text_to_speech` for compatibility, but its display name
is now `Speech I/O`.

Actions:

- `speak_text`
- `stop_speaking`
- `save_wav`
- `list_voices`
- `listen_once`
- `list_recognizers`

TTS uses a managed asynchronous PowerShell process, allowing the mute button to stop
speech immediately. STT uses `System.Speech.Recognition` and the default microphone.
A Windows speech-recognition language pack/recognizer must be installed for dictation.


# V6.6.22 — Voice Studio

Speech I/O is upgraded to v1.2.

Chat now includes:

`[Message Apollo...] [🎙 Dictate] [🔊 Voice On] [🎚 Voice] [Send]`

`🎚 Voice` opens the Speech I/O module's Voice Studio.

Voice Studio persists Apollo's default spoken-reply profile to:

`storage/speech_voice_profile.json`

Controls:

- installed Windows voice
- Any / Male / Female preference
- emotion preset
- voice depth
- pitch
- speed
- volume
- preview / stop / save / reset

Apollo's automatic spoken replies now call `speak_text` with only the completed
reply text, so the Speech I/O module applies the saved profile automatically.

Emotion is approximated locally through Windows System.Speech SSML prosody. It is
not neural emotional acting. The quality and available male/female voices depend
on the Windows voices installed on the user's PC.


# V6.6.23 — Accent Fix + Apps in Settings

## Voice Studio accent fix

Voice Studio now has a real Accent control based on the cultures of voices
actually installed in Windows.

Examples can include:

- British English (`en-GB`)
- American English (`en-US`)
- Australian English (`en-AU`)
- Irish English (`en-IE`)
- Canadian English (`en-CA`)

Only accents/cultures that are actually available through installed Windows
voices are offered in the UI.

Voice selection priority:

1. Exact voice
2. Accent/culture + preferred gender
3. Accent/culture
4. Preferred gender
5. Windows default

If the user changes Accent while an incompatible exact voice is selected, Voice
Studio switches the exact voice back to Automatic so the new accent can actually
take effect.

## Apps moved into Settings

The top-level Apps sidebar button has been removed.

Module mini-apps now live at:

`Settings → Apps`

Internal module placement remains `apps` for backwards compatibility, but the
Modules page now labels it `Settings → Apps`.

Old saved UI state that points to the previous top-level `Apps` page is migrated
automatically to `Settings → Apps`.


# V6.6.24 — Settings Model Switcher

Apollo's active Ollama language model can now be changed manually from:

`Settings → General → AI Model / Ollama`

The model control is an editable drop-down.

Use `Refresh Installed Models` to read the models currently installed in Ollama,
select one, and press `Save & Switch Model`.

The selection is persisted to `config.json`.

Changing models does not replace Apollo itself. The following remain intact:

- memories
- compiled/Pile knowledge
- modules
- pending modules
- To-Do data
- Voice Studio settings
- UI state

New chat requests use the newly selected model immediately. If a response was
already running during a switch, that one response finishes with the old client
and the next request uses the new model.

The pending-module repair engine is also updated to the new Ollama client so
module repair does not accidentally continue using the previously selected model.


# V6.6.25 — Workshop / Natural Voice / Self-Improvement Foundation

This patch moves three Apollo subsystems toward the long-term OS-style architecture.

## Apollo Workshop

The existing Coding surface is now presented as **Workshop** while keeping the internal
page key for backwards-compatible UI state.

Workshop modes:

- Build / edit real project files
- Full Apollo capability access
- Self-improvement — pending / approval gated

`workspace/APOLLO_CAPABILITIES.json` is generated from the actual enabled module tool
catalog, so the work surface has a machine-readable capability registry.

## Real multi-file builds

Ordinary Workshop build requests are forced through `file_builder__write_files`; a local
model can no longer satisfy a real-file request merely by printing Markdown code blocks.
The entire project is written in one coherent batch and statically checked together.
Python syntax, local Python imports, and common HTML local references are checked without
executing generated code. A `.apollo_project.json` file records project state.

## Controlled self-improvement

Self-improvement mode can inspect Apollo through read-only self-awareness, create
workspace prototypes, and create/repair pending modules. It may not silently overwrite
Apollo core or install/enable its own changes. Acceptance remains user-controlled.

## Natural Voice + future TinyVoice data

Speech I/O v1.3 adds Precise/Natural/Expressive delivery. The natural renderer creates a
separate speech version of Apollo's exact displayed response, skipping code/URLs when
enabled and adding conversational contractions and sentence/paragraph pacing.

Dictate can now record the microphone to a 16 kHz mono WAV and transcribe the same file.
When Voice Studio saving is enabled, the audio/transcript pair is stored in
`storage/voice_dataset/` as future TinyVoice training data. Samples begin unapproved.


# Apollo 7.0 — Core Integration Release

Apollo 7 turns the existing module collection into one coordinated local AI environment.

## Shared nervous system

`apollo_runtime.py` provides one persistent action bus, event bus, permission gate,
task journal, notification store, shared blackboard, goals and recovery snapshots.
Module calls from Chat, Workshop, automation and UI surfaces pass through the same
runtime instead of each subsystem quietly doing its own thing.

High-risk capabilities such as shell execution, process termination, serial writes,
package installation and screen capture start denied. Open:

`Settings -> Apps -> Control Center`

to explicitly allow or deny individual capabilities.

## Added Apollo 7 modules

- Core Services / Control Center
- Orchestrator
- Notification Center
- Workspace Manager
- Automation Engine
- Self-Improvement Lab
- Dependency Manager
- Memory Intelligence
- Model Runtime
- Screen Vision
- Device Bridge
- Process Manager
- Terminal Bridge
- Voice Agent

## Cross-model communication

The Orchestrator persists goals and a shared blackboard. Context packets can include the
current task, active goals, shared state and recent event-bus activity, allowing a coding
model, reasoning model or future vision model to inherit the same intent.

## Model routing

Settings now include an optional automatic model-routing switch. Role-to-model mappings
are stored by Model Runtime. The router is deterministic rather than asking an LLM which
LLM should answer.

## Workspace / OS direction

The Workspace Manager gives Apollo an OS-style file surface. Existing File Builder still
handles coherent multi-file project generation; Workspace Manager handles browse/read/
edit/search and permission-gated execution.

`Ctrl+K` opens the Apollo command palette.

## Automation

Automation Engine stores one-shot/interval actions and Apollo polls due jobs every 30
seconds. The scheduled target still passes through the normal permission gate.

## Self improvement

Self-Improvement Lab can audit Apollo, create multi-file proposals in
`workspace/self_improvement/`, and create recovery snapshots. It deliberately has no
silent core-apply action. Module Factory's pending/validation/approval path remains the
safe upgrade path.

## Recovery

Core Services can create recovery ZIPs under `storage/recovery/`. Apollo also tracks an
unclean-shutdown marker and posts a warning notification on the next launch if the prior
session did not close cleanly.

Use `start_apollo_safe_mode.bat` for a recovery-oriented launch environment.

## EXE trust

See `README_EXE_SAFETY.txt`. The safer builder uses PyInstaller ONEDIR, no UPX, version
metadata, an icon and a SHA-256 release hash. A genuine code-signing certificate is still
required if you want Windows to identify Apollo as a verified publisher.


# V7.0.1 — Module Build Routing Fix

Explicit Apollo module creation is now deterministic from Chat, Coding Workspace,
Workshop and Self-Improvement Workshop. Module Factory contract lookup and creation
are executed for real; narrated fake calls and invented `module_factory__validate`
examples no longer count as module creation. Candidate validation remains automatic
and successful candidates remain pending until user approval.


# Apollo 7.5 — Coordination & OS Integration

Apollo 7.5 focuses on making Apollo behave like one persistent local AI environment rather than unrelated modules.

Major additions include the OS-backed Apollo File Manager, misplaced-file scanner, Memory Distillation, Context Manager, persistent Task Engine, Verification Engine, Capability Graph, Knowledge Graph, Activity Trace, Benchmark Suite, Upgrade History, Background Intelligence, specialist model profiles, isolated dependency environments, multi-file self-improvement staging, permission profiles and repeated-crash module quarantine.

## File Manager

The File Manager reads the real filesystem on every refresh. Move/rename/trash operations affect Windows immediately. It manages Apollo root, workspace, storage, modules and pending_modules. Apollo core files are protected from direct move/delete; self-improvement remains proposal/approval based. Delete uses recoverable `storage/file_trash`. `scan_misplaced` only suggests corrections and never moves files automatically.

## Coordination

Each normal model call can receive a compact operational context packet containing active goals, relevant shared state, recent failed actions and relevant capabilities. This is operational state rather than hidden model reasoning. Substantial work is guided toward planner → executor → verifier behavior.

## Memory

Pile raw passages stay in `storage/compiled_knowledge.db`. Memory Bank receives a compact distilled concept summary with provenance and canonical topic fingerprint, reducing duplicate/junk memories such as command text being used as a title.

## Self improvement

Apollo can audit itself, stage coordinated multi-file improvement candidates, verify Python syntax, hash candidates, run infrastructure benchmarks and create recovery checkpoints. Applying core changes is still user controlled.

# V7.5.01 — File-backed Patch Notes

Settings has a **Patch Notes** tab. The tab reads `docs/patch_notes/PATCH_NOTES.md` from the
Apollo installation directory, so future release notes can be updated by changing
that file rather than hard-coding release text into the UI.

Buttons:
- Reload Notes
- Open Notes File

# V7.5.02 — Dual-Pane Files + Close Button

File Manager now keeps two independent live filesystem locations open at once.
Drag between panes moves real files; dropping from Windows Explorer copies/imports
files into the selected pane. Apollo also has an in-app top-right close button that
uses the normal clean shutdown path.
