# Apollo Knowledge Nodes and JARVIS comparison

11 November 2026. Based on Apollo main `84c06a2`; changes are a reviewable feature branch, not a deployed release.

## What this update implements

Open **Memory Bank → Knowledge Nodes**. The same local database now contains named sections, topics, projects, people, devices, experiments and sources. Nodes have optional parents and link to existing memory IDs. Tags, sources and memory types supply exact automatic memberships; the interface also supports manual links.

For example, create an **Apollo** project and a **Voice** topic inside it, then link the relevant XTTS memories. Connect Voice to a hardware topic when hardware limitations matter. The browser shows memory counts, source details, correction history and a clickable neighbourhood map.

Chat and Context Manager use the same retrieval service. Text search is combined with node matches and at most one hop through confirmed `related` / `part_of` edges or child nodes. Suggested links, `supports`, `contradicts`, `depends_on` and low-confidence links do not expand recall. Results explain their route and retain `[memory:ID]` references. Node membership and association confidence do not verify a claim. Scientific hypotheses remain distinguishable through memory types and source information.

There is no embedding model download or additional service. Context is bounded by characters; this is not a claim of exact token budgeting. The lexical fallback no longer returns unrelated entries solely because of their importance.

## JARVIS research and adoption

The request did not identify one exact product. Several unrelated projects use this name. These primary repositories were compared; their advertised features are not independently benchmarked here. No third-party implementation was copied.

| Project | Relevant documented ideas | Apollo treatment |
|---|---|---|
| [isair/jarvis](https://github.com/isair/jarvis) | Local voice/text assistant, diary/graph viewer, MCP tools, dictation, visible task progress | Use unified local memory, readable progress and a memory viewer. Apollo already has voice, chat, tasks and runtime tools in main; hardware-level voice behaviour was not revalidated here. |
| [Szesnasty/Jarvis](https://github.com/Szesnasty/Jarvis) | Typed knowledge graph, reviewed connections, graph-aware retrieval, Markdown notes | Implement typed nodes, suggested/confirmed connections, bounded one-hop retrieval, explanations and Markdown export. Dense embeddings and a full Markdown vault rebuild are future work. |
| [Personal Jarvis, now Dodaios](https://github.com/Dodaios/Dodaios) | Coordinated specialists, persistent agent work, routines, local wiki, action approvals | Reuse Apollo's existing Foundry, mission and permission architecture. Add shared knowledge packets. Do not install another agent framework or grant new execution rights. |

## Existing Apollo features and remaining gaps

| Area | Evidence / status |
|---|---|
| Voice and local model selection | Present in `voice_center`, `text_to_speech`, Ollama client and model settings. Not replaced by this update. |
| Chat continuity | Existing `chat_memory_module` and `conversation_flow`; memory node tools are now reachable from ordinary memory-related requests. |
| Research and durable missions | Existing `reasoning_director`, `learning_missions`, `research_library` and `mission_control`; knowledge records share the Memory Bank. |
| Foundry coding agents | Existing main-branch Foundry. The more ambitious [JARVIS Director PR #47](https://github.com/oscarccx-coder/codespaces-blank/pull/47) remains unmerged. |
| Self-installing assessed updates | [PR #48](https://github.com/oscarccx-coder/codespaces-blank/pull/48) remains unmerged; this update does not activate it. |
| Sentinel audits and optimisation | [PR #49](https://github.com/oscarccx-coder/codespaces-blank/pull/49) is an unmerged documentation proposal. |
| General MCP client / tool marketplace | Future integration. Apollo's internal tool contracts are not a general MCP client. |
| Continuous room listening, global dictation, interruption handling | Require separate opt-in implementation and real microphone/speaker testing; not added here. |
| Semantic embeddings | Future measured comparison against current SQLite FTS plus graph recall, on the owner's hardware. |

## Data migration and rollback

Opening Memory Bank adds tables to `storage/databases/memory_bank.db` and backfills existing rows once without changing their IDs or contents. New memories keep their metadata links current. Automatic metadata changes do not remove manual memberships. Corrections retain previous content and provenance, including automatic same-name/source replacements. Old overwritten versions cannot be recovered retroactively.

Removing a memory also removes its memberships and saved revisions so deleted personal content cannot leak through graph recall. Nodes can remain empty for reuse. The older `knowledge_graph.db` relationship store and its tools remain available; its free-text relations are not silently promoted into confirmed node links.

The Markdown action returns a page or saves to an explicitly chosen local path. It exports at most 200 memories from the selected node and labels that limit. There is no automatic network transfer or automatic export of personal data. Exports are snapshots, not a bidirectional Obsidian sync.

Before production adoption, use the existing backup workflow. Reverting the code leaves the additive tables in place and restores the earlier app behaviour; older code ignores these tables. Restoring an actual pre-upgrade database backup is the full data rollback. As with any source rollback, review later edits before restoring an older database.

## Verification

Automated coverage includes baseline schema migration, idempotent restart, memberships, parent cycles, source-linked correction history, manual unlinking, deletion cleanup, literal filters, confirmed/suggested/low-confidence/contradictory links, one-hop limits, context bounds, tool routing and real offscreen Qt selection/create/link/export actions. The real UI was rendered and inspected on Linux. CI runs the new tests on Linux and Windows; the Windows job exercises Qt with the installed dependencies.

This update does not claim live Ollama answer quality, XTTS audio quality, performance on the creator's PC, or successful Windows checks before CI reports them. Merging and production installation remain owner-approved steps.
