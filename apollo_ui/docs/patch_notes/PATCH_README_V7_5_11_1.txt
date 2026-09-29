Apollo 7.5.11.1 — Direct-Manipulation Hub Edit Mode

INSTALL
-------
Install over Apollo 7.5.11. Close Apollo first, extract this patch into the Apollo root, replace matching files, then restart.

PLAY TEST
---------
Open Hub and click Edit Layout.

- Drag the body of a tile to move it.
- Drag any glowing corner to resize it.
- The translucent outline shows the grid rectangle that will be saved.
- Drop a tile inside a different existing Hub section to move it there.
- Click Done Editing when finished.
- Restart Apollo and confirm the exact positions and custom dimensions survive.

Hub Manager remains available for pin/unpin, section creation/renaming and preset-size fallback controls.

The patch does not overwrite storage/, workspace/, config.json, modules_state.json or ui_state.json. Existing 7.5.11 hub layouts are migrated automatically.
