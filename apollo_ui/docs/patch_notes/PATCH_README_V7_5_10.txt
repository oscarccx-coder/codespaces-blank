Apollo 7.5.10 — Module Compiler Repair + Deterministic UI Fallback

Install over Apollo 7.5.09. Close Apollo, extract over the Apollo root, replace matching files, then restart.

This fixes the exact `SyntaxError ... line 125` conversion failure. Apollo now gives the model the broken source it is supposed to repair. If five repairs still fail, a deterministic Python-project UI adapter is generated around the real Workspace project.

Retest:
turn gravity lab into a modual with ui so i can use it within this program

The patch excludes storage/, workspace/, pending_modules/, config.json, ui_state.json and modules_state.json.
