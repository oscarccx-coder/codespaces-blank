Apollo 7.5.11 — OS Shell Foundation + Custom Hub

INSTALL OVER 7.5.10
-------------------
1. Close Apollo completely.
2. Extract this patch over the Apollo 7.5.10 root.
3. Replace matching files.
4. Start Apollo normally.

The patch does NOT include your storage/, workspace/, pending_modules/, config.json, modules_state.json, or ui_state.json.

FIRST PLAY TEST
---------------
Open Hub -> Manage Hub.

Try all of these:
- Pin Voice Studio, To-Do List, Memory Bank or another module.
- Remove Chat from Hub (it remains installed and still exists in the sidebar).
- Set one tile Small, another Medium, another Wide, another Large.
- Move tiles Up/Down.
- Change one tile to a new section such as Projects or Tools.
- Close Apollo completely and reopen it. The layout should survive.
- Disable a pinned module from Modules. The Hub must not crash. Its tile should become unavailable.
- Re-enable it and verify it becomes launchable again.
- If you uninstall/remove a pinned module, the Home screen should hide the dead tile rather than display a broken shortcut. Hub Manager can still show the missing layout record.
- Press Reset Default Layout. It must change only the Hub layout; it must not uninstall anything.

KNOWN SCOPE FOR THIS PLAY TEST
------------------------------
This is the shell chassis, not the final Apollo OS visual redesign. Drag-and-drop tiles, live resizable widgets, wallpapers, a task strip, notification centre integration and floating/multi-window apps are deliberately deferred until this registry/layout backbone survives play testing.

If anything behaves strangely, send the exact action sequence and any traceback/message.
