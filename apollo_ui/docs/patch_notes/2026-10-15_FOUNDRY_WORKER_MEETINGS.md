# Apollo Foundry: workflow and team meetings

## New visual workflow
- **Workflow & Meetings** tab in Foundry displays Manager, Architect, Implementer, Tester, Reviewer and Integrator as role nodes with project task status.
- Dashed connections represent expected dependencies, not completed interactions. Solid teal connections require a persisted group meeting with that speaker or a real handoff audit event.
- The History tab persists worker assignment/return handoffs with UTC timestamps.
- Saved meeting transcripts show each speaker and the timestamp when the local model actually responded.

## Actual team meetings
- Press **Hold Team Meeting** to choose the discussion topic.
- **Plan My Project** first holds a kickoff meeting and waits for a saved manager summary before starting the existing bounded auto-draft sequence.
- Reporting an issue or exhausting a worker's generation retries initiates a non-executing team discussion about the blocker.
- Each specialist (Architect, Implementer, Tester, Reviewer, Integrator) sees the latest owner requirements and earlier speakers' responses, then the Manager produces an actionable final summary. These are sequential Ollama model calls, not fabricated simultaneous workers.
- Only a successfully completed six-turn meeting is stored in the project SQLite database. Its decisions feed subsequent worker prompts and manager plan prompts; old project requirements never outrank the latest owner request.

## Safety and limitations
- Meetings do not execute project files, access Apollo's core or approve code.
- Model responses and meeting conclusions can be wrong and still require review. Meeting decisions are discussion context, **not a binding dependency engine** or proof that workers built the application.
- A group meeting is relatively slow on a local 7B model because the roles speak sequentially.
- Paused or failed meetings are not counted as completed; no false communication is displayed.
- Generated project code still requires explicit sandbox/runtime verification and human approval.
