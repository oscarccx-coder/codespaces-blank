Apollo 7.5.09 — Project-to-Module Compiler + UI Authoring

Install over Apollo 7.5.08. Close Apollo, extract over the Apollo root, replace matching files, then restart.

RETEST
------
After working on GravityLab, say:

turn it into a modual with ui so i can use it within this program

Apollo should inspect the real workspace/GravityLab files and create a REAL pending Apollo UI module, normally `gravitylab_app`. It must not give a generic tutorial and must not print an invented `turn_into_module` call.

If you then say only `do it`, Apollo recovers the previous meaningful request and takes the same real route.

The module remains pending until validation and user approval. The patch excludes storage/, workspace/, pending_modules/, config.json, ui_state.json and modules_state.json.
