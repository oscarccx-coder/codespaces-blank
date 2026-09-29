Apollo 7.5.01 — Patch Notes View

INSTALL
-------
1. Close Apollo.
2. Extract this patch over the Apollo root.
3. Replace main.py and version_info.txt when prompted.
4. Keep PATCH_NOTES.md in the Apollo root next to main.py.
5. Start Apollo.
6. Open Settings -> Patch Notes.

The small patch does NOT contain:
- config.json
- storage/
- workspace/
- pending_modules/
- ui_state.json
- modules_state.json

HOW IT WORKS
------------
Settings -> Patch Notes reads:

PATCH_NOTES.md

directly from Apollo's installation folder.

Use "Reload Notes" after manually editing the file.
Use "Open Notes File" to open that exact file in Windows.

Future Apollo patches only need to append their release notes to PATCH_NOTES.md;
the viewer itself does not need another rewrite.
