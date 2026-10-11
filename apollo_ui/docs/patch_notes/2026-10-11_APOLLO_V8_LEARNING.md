# Apollo 8.0.0.0 — Learning & Self-Research Integration (development candidate)

## User-facing changes

- Learning screen: add a research topic, press **Research This Topic** to investigate its next due question, or **Ask Apollo in Chat** to prepare a natural-language question.
- Saved research is now associated with a specific question, given a review date, and indexed into named Memory Bank excerpts with source URLs and local file references. **Fetched does not mean verified.** If zero pages were fetched, the question stays due and an error is shown.
- Chat strips question phrasing such as "What is XTTS?" or "What can XTTS do for me?" down to the actual topic before searching compiled Pile knowledge, saved research, named memories, and Knowledge Graph. The normal LLM then composes a reply with evidence/uncertainty labels. No source-backed answer can be promised if the local model or knowledge stores are unavailable.
- Chat includes a visible Learning shortcut. Learning's **Follow-ups & upgrades** tab has a simpler preference set: **Manual only** (default), **Remind me**, or **Research automatically**. Configure 1–720 hours between checks and 1–365 days between later reviews.
- Automatic research is user-enabled only, researches **at most one due question per interval**, runs off the Qt UI thread, saves unverified evidence, and does not install upgrades. Reminders use the main window status bar. Requires Apollo's GUI and the Research & Training module to remain running and enabled. This is not an OS background service.
- Deterministic improvement suggestions cite actual overdue learning work, current reminder preferences and measured practice scores. **Create proposal** is the only write option, producing an approval-gated Developer Lab proposal. No code apply, model retraining, customer contact, purchases, or money handling.

## How to use and verify

1. Update your checkout to this **development branch** or install a future **signed stable/beta release** when it exists. Back up local storage first.
2. Launch Apollo. Open **Learning & Reasoning** under the Memory & Learning group.
3. Enter e.g. "Casimir effect", press **Queue Topic**. Four deterministic follow-up questions appear.
4. Press **Research This Topic**. Apollo tries public search and source fetch. If sources are available, the selected question is recorded with an unverified evidence note, and excerpts are indexed for Chat; failure leaves the question open. Network access is required for this step.
5. Press **Ask Apollo in Chat**, then Send. Try "What is the Casimir effect and what could it do for me?" Inspect the citations/source labels rather than assuming source text is true.
6. Under **Follow-ups & upgrades**, select Remind me and set an interval, or explicitly confirm automatic browsing. Leave on Manual to disable unattended follow-ups. Automatic operation requires Apollo to remain open.
7. Select a suggestion and **Create proposal**. Review staged proposals in **Developer Lab**; neither the learning scheduler nor a proposal modifies Apollo's core code.

## Build gates and limitations

Code-path and pure-Python regression tests are included in tests/test_learning_v8.py; GitHub Actions adds these to the standard regression suite. The test suite is not a substitute for Windows GUI interaction, local Ollama quality tests, blocked/offline network tests, or sign-and-update recovery on the owner's machine. Do not announce a stable Apollo 8 release until CI passes, UI is smoke-tested, and a trusted signed package is published. This branch does not contain any private release key.

An authenticated research source is not guaranteed to be correct or independent; saved web pages are untrusted context. Apollo does not learn model weights from stored notes. The v8 scheduler currently runs only while the desktop app is open, and does not cancel an already-running network request if its settings are changed during that request. The long-term autonomous coding team, broader held-out benchmark suite, and Pi service scheduler remain separate future milestones rather than silently claiming they are finished.
