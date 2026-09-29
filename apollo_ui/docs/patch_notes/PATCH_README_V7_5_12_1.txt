Apollo 7.5.12.1 — UI Form Stability

Install over Apollo 7.5.12 with Apollo completely closed.

WHAT THIS FIXES
---------------
Module app text boxes were allowed to shrink below a readable height when their
embedded UI had more vertical content than Settings -> Apps could display.

The host now scrolls oversized module apps instead of crushing their controls.

Standard minimums:
- Line edits / combo boxes / spin boxes: readable single-line height
- Multi-line editors: readable minimum area

Voice Imprint Lab also has explicit sizing fixes for the fields visible in the
reported screenshot.

PLAY TEST
---------
Open Settings -> Apps -> Voice Imprint Lab.

Check:
1. Profile name and Audio track fields have readable full-height text.
2. Model folder, Device and Language are readable.
3. Test Apollo Voice text box remains tall enough to read.
4. Output area remains usable.
5. If the window is made shorter, a vertical scrollbar appears instead of the
   controls collapsing into horizontal lines.

Also open at least two other module apps and resize the Apollo window smaller
to verify the generic app-host protection.

This patch does not overwrite storage/, workspace/, pending_modules/,
config.json, ui_state.json or modules_state.json.
