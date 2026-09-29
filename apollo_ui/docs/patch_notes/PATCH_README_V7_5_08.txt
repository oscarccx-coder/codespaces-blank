Apollo 7.5.08 — Conversation Recall + Real Retry

Install over Apollo 7.5.07. Close Apollo, extract the patch into the Apollo root, replace matching files, then restart.

Apollo now reads a bounded recent timeline from persistent Chat Memory when it starts and before each normal chat request. It also retrieves older exchanges relevant to the current message.

The important retry flow is now deterministic:

failed request -> "try again" -> recover previous meaningful user request -> rerun the real route

This works for project edits, File Builder project creation and Module Factory requests, including after a restart when persistent Chat Memory contains the previous conversation.

The patch excludes storage/, workspace/, config.json, ui_state.json and modules_state.json.
