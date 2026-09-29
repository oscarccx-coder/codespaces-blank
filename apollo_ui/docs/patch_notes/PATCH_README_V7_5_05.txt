Apollo 7.5.05 — Real File Builds in Chat + Stable Responses

Install over 7.5.04. Close Apollo, extract over the Apollo root, replace matching files, then restart.

This fixes the GravityLab failure where Apollo printed a `file_builder.write_files` JSON object in Chat but created no file. Normal Chat now routes concrete coding-project requests through the real File Builder.

Generated code/tool JSON stays internal. Chat keeps a stable Working... card until the final response is ready instead of repeatedly rebuilding/flashing the transcript.

The patch excludes config.json, storage/, workspace/, pending_modules/, ui_state.json and modules_state.json.
