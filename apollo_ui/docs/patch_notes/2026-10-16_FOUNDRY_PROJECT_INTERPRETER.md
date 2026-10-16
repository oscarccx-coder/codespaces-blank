# Apollo Foundry Project Interpreter (natural-language debriefs)

## Purpose
Provide the owner one truthful, understandable explanation of an entire Foundry app-development project. Workers already discuss actual project requirements in local Ollama meetings. The Interpreter separates this conversation from verifiable code and test evidence.

## What it does
- Reads existing project tasks, reviews, blocking issues, actual worker meeting transcripts and audit history.
- Inspects the current project's Python syntax and UI/backend wiring *without executing application code*.
- Compares only Docker test results matched to the current source fingerprint. Reports three distinct checks: unit tests, Qt UI signal-to-backend interactions, and GUI startup smoke.
- Includes an inventory of Python files actually inspected, pending drafts, blockers and specific owner decisions.
- Produces a short plain-English debrief plus supporting sections. A requested briefing works offline and does not need Ollama.
- Saves a dated snapshot on explicit UI request and when **Stop** or **I'm Happy / Review** concludes a continuous development session.
- Opens the **Interpreter** tab after stopping; in-flight jobs are flagged so the user can refresh once they finish.
- Offers a read-only Apollo chat tool, `app_project_brief(project_id)`, so the creator can ask Apollo to explain the selected project's recorded progress.
- Worker meeting prompts encourage direct, natural conversation and escalation of real uncertainties without inventing test results.

## How to use
1. Open **Apollo Foundry**, select your project and choose the **Interpreter** tab.
2. Press **Assess Project & Brief Me** at any time. The report is saved, with a timestamp.
3. Or run a continuous session and press **Stop** or **I'm Happy / Review**. Interpreter automatically saves a review summary.
4. In Apollo chat, ask for the briefing of a known project ID. This reads current facts without starting work or saving a report.

## Limits
- This is a deterministic natural-language interpreter, not an independent, omniscient AI evaluator. It does not run an additional specialist Ollama model.
- Meeting quotes are labelled as **AI opinions**, never trusted as evidence of completion.
- Passing Docker checks does not establish appearance, full correctness or usability. Owner approval remains separate.
- A briefing generated while an operation is ending is provisional. Refresh it after completion.
- This version produces **textual natural-language summaries**, not spoken XTTS narration. Voice integration will require a separately tested, opt-in UI/voice connection.
- This does not create a permanent autonomous background agent and does not give workers additional core or filesystem permissions.

## Tests
Offline regression tests cover fake worker success claims, stale test results, source-matched passes, open issues, active tasks, independent chat reporting, saved briefing recovery and static-only inspection. Actual Windows UI and Docker CI must pass before merge.
