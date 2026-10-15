# Sidebar App Picker (15 October 2026)

- Apollo's **Add / Remove Apps** sidebar control now lists all **installed, enabled modules with a working UI**, not only modules assigned to sidebar placement.
- Search for an app, tick to pin or untick to unpin, drag to reorder, and save. There are also **Add selected** and **Remove selected** shortcuts.
- Right-click any normal sidebar shortcut to **Remove from sidebar** or open the app picker.
- Unpinning never disables, uninstalls or deletes an app. Home and Settings stay pinned for recovery.
- New Settings Apps / hidden-placement modules begin *unpinned* and can be added manually. Previously pinned/renamed preferences survive module rebuilds and restarts. Modules explicitly configured for sidebar retain their initial placement.
- Reset restores the core sidebar and the currently loaded modules' declared placement defaults.
- Registry and persistence regression tests cover pin/unpin, restarts, reset, validation and Qt wiring. Windows GUI test checks the main application still starts correctly.

Note: apps without a usable loaded UI are not navigation targets until enabled and available.
