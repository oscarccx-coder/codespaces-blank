Apollo 7.5.04 — Module Authoring Compiler + Conversation Flow

INSTALL
-------
1. Close Apollo.
2. Extract this patch over Apollo 7.5.03.
3. Replace matching source/module files.
4. Start Apollo.

WHAT THIS FIXES
---------------
A local 7B model can understand how to write a module while still being bad at
serialising a large Python program into one nested tool-call JSON argument.
Apollo now falls back to a deterministic compiler: metadata and raw Python are
generated separately, Apollo parses the Python itself, then Apollo constructs the
real Module Factory call.

"try again" also reuses the previous explicit module request.

CONVERSATION FLOW
-----------------
The new Conversation Flow module automatically gives normal Chat a compact packet
for visible-history follow-ups/retries. It uses no additional LLM call.

USER DATA
---------
This patch excludes config.json, storage/, workspace/, pending_modules/,
ui_state.json and modules_state.json.
