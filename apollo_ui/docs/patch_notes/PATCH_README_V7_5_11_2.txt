Apollo 7.5.11.2 — Hub Edit Mode Activation Fix

Install over Apollo 7.5.11.1 with Apollo fully closed.

ROOT CAUSE
----------
The Edit Layout button did exist in 7.5.11.1, but it was not checkable.
PySide6 QPushButton.clicked emits a boolean. That False value was passed into
toggle_hub_edit_mode(force=None), so Apollo interpreted every click as
"force edit mode off".

FIX
---
Edit Layout is now checkable:
- Checked = edit mode ON
- Unchecked = edit mode OFF

You also now have:
Hub -> Manage Hub -> Edit Hub Directly

PLAY TEST
---------
1. Open Hub.
2. Click Edit Layout.
3. The button should become Done Editing.
4. The edit banner and glowing corner handles should appear immediately.
5. Drag a tile BODY to move it.
6. Drag a glowing CORNER to resize it.
7. Click Done Editing.
8. Restart Apollo and verify layout persists.

This patch does not overwrite storage/, workspace/, config.json,
ui_state.json, modules_state.json or pending_modules/.
