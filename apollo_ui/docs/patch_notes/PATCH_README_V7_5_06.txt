Apollo 7.5.06 — Existing Project Follow-Ups

Install over Apollo 7.5.05. Close Apollo, extract this patch into the Apollo root, replace matching files, then restart.

Exact regression fixed:
1. Build GravityLab.
2. Say: add a second calculator for escape velocity and make it accept the planet mass and radius

Apollo now identifies GravityLab as the active real project, inspects its current files, updates it through File Builder, verifies the whole project, and gives a concise completion message.

Raw unexecuted tool JSON is also suppressed from Chat.

The patch excludes config.json, storage/, workspace/, pending_modules/, ui_state.json and modules_state.json.
