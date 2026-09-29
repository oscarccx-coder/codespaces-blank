Apollo 7.5.12 — Internal Roadmap + Certified Activation

Install over Apollo 7.5.11.2 with Apollo completely closed.

ROADMAP
-------
Apollo Roadmap is now an installed UI app.

Open:
Settings -> Apps -> Apollo Roadmap

Then use Hub management to pin it to Home if you want the roadmap visible there.

Persistent roadmap data:
storage/roadmap/roadmap.json

CERTIFIED INSTANT ACCESS
------------------------
New module:
candidate -> isolated validation PASS -> user approval -> install -> live immediately

Approved upgrade:
candidate -> isolated validation PASS -> user approval -> backup old module ->
replace -> reload -> live immediately

If an approved module upgrade fails to load, Apollo restores the previous module.

IMPORTANT
---------
"Certified" does not mean silent self-installation.
Validation PASS + explicit approval is still required.

Module-based self-features can be activated immediately.
Core Python process files still require restart when replaced; later OS work will
move more of Apollo behind hot-reloadable module boundaries.

Patch excludes storage/, workspace/, pending_modules/, config.json,
ui_state.json and modules_state.json.
