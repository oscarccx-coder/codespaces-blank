# Apollo Chat Workspace

This is a local-first assistant workspace inspired by familiar ChatGPT workflows. It is not a claim that Apollo has ChatGPT's models, hosted services or reasoning quality. Based on Apollo main `84c06a2` and the Knowledge Nodes update in PR #50; neither is deployed by this feature branch.

## Features implemented

| Workflow | Behaviour |
|---|---|
| Saved conversations | Independent chats survive restarts. Search titles and message text, rename, pin, archive, restore, move to a project and delete. |
| Projects | Keep related chats, per-project instructions and explicit source snapshots together. Unrelated project sources are not automatically injected. |
| Drafts | Unsent messages, per-chat model/style settings and the canvas are saved locally. Existing compact legacy history is imported once; original memory stores remain intact. |
| Composer | Multiline text, Enter to send, Shift+Enter for a newline, file picker and local-file drag/drop. |
| Model selection | Select an installed Ollama model, refresh its model list or enter a model name. No automatic downloads and no silent replacement of the selected model. |
| Response style | Concise, balanced or detailed, plus editable standing response instructions and Apollo's existing personality preferences. |
| Replies | Live streamed text becomes formatted Markdown when complete. Copy replies/code, read aloud through existing speech tools, open a response/code block in the canvas. |
| Edit / regenerate | Preserve the original conversation and create a new branch. File/image snapshots relevant to the branch are copied; later sources are excluded. |
| Stop | Interrupt the per-turn model socket and stop further queued tool rounds. An already-running tool reaches its next boundary; Stop does not promise to undo completed actions. |
| Recovery | Partial responses are checkpointed. A crashed streaming response is labelled interrupted on restart, never complete. |
| Temporary chat | Uses a separate SQLite database in RAM. Automatic memory retrieval, tools, dictation and automatic speech are off. No temporary chat messages or attachment snapshots are written to Apollo's chat database. The selected model server's own logging is outside this control. Explicit exports are user-directed writes. |
| Document input | Read text/code, CSV/TSV, selectable-text PDFs, DOCX and XLSX with bounded extraction. Source snapshots retain hashes and readable citations. |
| Images | PNG/JPEG/WebP snapshots resized to at most 1600 pixels, up to four new images per message. The selected model must report vision capability. Recent supplied images remain available for follow-up questions. |
| Data | CSV/TSV quick statistics perform actual bounded arithmetic. Free-form Python is not executed by the chat panel. Existing Foundry sandbox execution remains a separate approved workflow. |
| Sources and activity | Inspect the file excerpts and saved knowledge used for a turn, and actual tool result logs. These are observable actions, not fabricated private reasoning. |
| Canvas | Edit a response or code block beside the chat, undo/redo, and optionally include its text in the next request. At smaller widths it opens in a separate window. |
| Exports | Export a conversation as Markdown/JSON. Save canvas text, create a real basic Word/PDF document, or convert CSV/tab-separated canvas text to XLSX. Spreadsheet formula-looking cells are treated as text. No generated code is run during export. |
| Existing Apollo apps | Open Knowledge/Memory, Voice, Foundry, Missions, Vision, Files and Updates from Chat. Web research and coding modes use existing guarded Apollo tools when enabled. |

ChatGPT's official workflow descriptions informed the project/chat organisation, source context and artifact review approach:

- https://learn.chatgpt.com/docs/projects
- https://learn.chatgpt.com/docs/artifacts-viewer
- https://learn.chatgpt.com/docs/features

## Model and agent choices

The model provides language/vision capability; an agent harness coordinates tools and work. Selecting Claude Code, Codex, OpenCode or Hermes through Ollama does not substitute a different provider's model for the one chosen.

For Apollo, Hermes is a relevant assistant-architecture reference because of its cross-session memory and skill creation. Codex is a possible dedicated Foundry coding worker; OpenCode is an alternative. These are integration options, not installed dependencies or unverified performance rankings. A compatible Mistral-family model remains a model choice, not a replacement for the chat/project/tool framework. This update installs none of these agent frameworks.

Current primary references checked:

- https://docs.ollama.com/integrations/hermes
- https://docs.ollama.com/integrations/codex
- https://docs.ollama.com/integrations/opencode
- https://docs.ollama.com/integrations/claude-code
- https://docs.ollama.com/api/chat

Ollama currently recommends a 64k context for Codex and specifies 64k+ for OpenCode. Such agent setups need separate hardware sizing; this UI does not silently increase Apollo's context allocation or download a large model.

## Practical limits

- The default model remains whatever the owner selected. A small local model may still need substantially stronger reasoning/tool-use capability; adding interface features is not model training or a frontier-quality benchmark.
- Image/video generation, a general plugin marketplace, hosted connectors, real-time duplex voice, a general MCP client and cloud-model account integration are not supplied by this change. Voice/dictation use the existing speech module where available.
- Attachments are limited to 12 MiB each and eight per message. Extraction reads at most 80,000 characters; PDFs up to 50 pages; XLSX up to eight sheets, 2000 rows/sheet and 40 columns. Source excerpts and older history may be shortened to fit a disclosed character budget. It is not an exact tokenizer.
- Scanned PDFs need a separately configured OCR/vision workflow; password-protected PDFs need an unlocked copy. Macros, attachment scripts and spreadsheet formulas are not executed.
- DOCX/PDF exports are basic text/heading/code documents, not full desktop publishing. XLSX export expects CSV/tab-separated table text. Existing complex office-file editing can be extended independently.
- Network use follows the selected Ollama endpoint and explicit existing tools. Temporary mode governs Apollo's local chat persistence, not third-party server retention. No API keys or ChatGPT-account access are assumed.

## Architecture and review

`apollo_chat_store.py` owns local conversations, projects, snapshots and preferences. `apollo_chat_files.py` handles read-only extraction, scoped context and exports. `apollo_chat_workspace.py` supplies the Qt interface and invokes existing `ChatTask` tools through the permission runtime. Legacy global conversation recall is excluded from this panel; saved Knowledge Nodes remain separately selectable through Memory.

Each turn receives its own client. Cancellation cannot stop unrelated voice/research clients. UI updates run on the Qt thread. File parsing and model calls run on the existing worker pool; chat switching is locked while a turn or attachment read is active. The original Chat view remains as a legacy fallback in source while normal shell entry points use this workspace.

Data is in `storage/databases/chat_workspace.db`; source code and runtime data remain separate. Migrations are additive. Roll back source to return to the earlier interface; the new database remains available for later restoration. Back up state before production adoption. Deleting a workspace chat removes its messages and owned attachment rows, but does not erase independent Knowledge Bank records, project sources or legacy conversation databases.

The test suite uses deterministic model fixtures, actual local HTTP streaming/cancellation, file parsers, real PDF/DOCX/XLSX exports, and real offscreen Qt interactions. This does not establish live-model answer quality or microphone/XTTS performance on the owner's PC. Owner approval is required before merging or installing a production update.
