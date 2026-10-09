# Apollo Learning, Reasoning & Growth Director

Version 7.5.13.6: core integration of curiosity questions, periodic research review, measurable local-model reasoning exercises and hardware/work priorities.

## What is actually available

- Learning & Reasoning app in Settings → Apps → Memory & Learning; Growth Director tab also reachable from Growth Lab.
- On creating a topic, Apollo automatically creates four research questions about primary evidence, falsification, practical experiments and outdated knowledge. It does not pretend to know their answers.
- Apollo can generate 1–3 **additional** topic questions using its selected local Ollama model only after the user explicitly presses Generate AI Questions. It does not browse or execute tools as part of this operation.
- The research ledger saves a short claim/observation, citation or experiment reference, manual confidence label, and 1–365 day revision interval. Overdue questions appear whenever the app or its action bus is opened.
- A fixed collection of 12 objective practice tasks includes electronic calculations, logical entailment, evidence independence, business maths, Python pitfalls and model-performance concepts. The app can run 3 tasks at a time with either one local-model answer or a second explicit self-review pass.
- Practice exercises rotate through the least-attempted questions per mode. First direct and self-review batches have matched initial questions. Apollo records deterministic correct/incorrect results, model identity, elapsed time, output tokens per second (when Ollama returns metrics), and outcomes by skill.
- The Growth Director assembles read-only priorities from manual Growth Lab work approvals and fund goals, queued learning, practice accuracy, and optional hardware scans. It cannot accept work, change bank balances, contact customers, buy components or automatically modify its own weights.

## The internal loop

1. **Curiosity:** a user, AI tool or project adds a named goal. Apollo immediately drafts bounded follow-up questions.
2. **Research:** the human selects a question, investigates the existing knowledge or a source through separately permissioned research tools, and records source references. Nothing is automatically asserted to be true.
3. **Scepticism:** evidence can be marked supported, disputed or unverified. A URL or model assertion is never proof. The user records its own assessment.
4. **Revision:** the next-review date is persisted in private SQLite. Review questions remain queued across restarts, and reappear when due. No background web scraping is enabled.
5. **Reasoning practise:** Apollo tries an objective question, optionally checks its own solution, and the deterministic rubric scores the answer. It sees the expected short explanation afterwards for feedback.
6. **Resource planning:** if repeated practise on one skill performs poorly, Growth Director recommends more reasoning practice before expensive GPU purchases. Actual tokens/s and successful project benchmarks are needed before recommending hardware.

## Safety and practical limits

**Knowledge retrieval is not model training.** This iteration improves learning workflow, feedback and task prioritisation but does not modify the GGUF/OLLAMA model's weights. A short fixed evaluation can be memorised. Its scores are indicators for debugging, not an IQ score or scientific evidence of improved general intelligence. More sophisticated evaluation needs hidden, independently generated held-out tasks and external checks.

Research citations are manually captured and explicitly tagged; the code does not validate external claims or run web searches without permission. Research notes are not automatically inserted into the assistant's permanent trusted memory or model system instructions. This blocks prompt-injection through fetched documents from silently changing system behaviour.

Research topic storage and practice logs live in **storage/databases/apollo_reasoning.db**; existing Growth Lab data lives in **storage/databases/apollo_growth.db**. Both are protected by Git ignore and excluded from signed source update ZIPs. Old Memory Bank and knowledge graph data are left intact; no automatic migrations or deletions.

Practice is **opt-in and bounded** to 3 questions per button press, or up to 6 model responses when self-review is enabled. It runs in a separate thread so the Qt window should remain responsive, but full GUI and model throughput still need to be tested on the actual Windows workstation.

Medical dosing, motors, ECU writes, financial transactions, customer outreach, code execution and purchases are outside this subsystem. Human approvals stay in the existing app-specific gates.

## Next iteration, not in this version

- Separate research worker with user-configurable web-access, source and time budgets; explicit start/stop/cancel; safe rate limiting and cached sources.
- Model-independent evidence evaluation using source cross-checks and appropriately labelled uncertainty.
- Larger, automatically curated **held-out** reasoning benchmark sets and measured real-project task success; robust comparison of prompting variants, model/context/batch profiles and regression tests.
- Integration of confirmed work into the staged Coding Team's isolated workspaces, with real tests and user-approved deliverables.
- Task-specific LoRA fine-tuning only on verified datasets, after holdout tests demonstrate benefit, and only if the local hardware and storage budget allow it.
- User-controlled review notifications on the desktop and Pi, avoiding repeated alert spam; offline-first by default.

## Opening it

Update to the new Apollo code in your own installation (a public signed Release is not published automatically). Open **Settings → Apps → Memory & Learning → Learning & Reasoning**. Add a topic and see its four questions. Record evidence to schedule later review. Run the direct benchmark, then run the self-reviewed benchmark to compare fixed-set performance. Open the Growth Director tab, or **Coding → Growth Lab → Growth Director**, to view recommendations.

Documented behaviour is covered by test_reasoning_director.py. Linux ARM64 and standard GitHub CI tests are not a substitute for a physical Pi or Windows/XTTS/GUI smoke test.
