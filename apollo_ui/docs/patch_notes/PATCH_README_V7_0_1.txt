Apollo V7.0.1 — Forced Module Build Routing Fix

WHAT THIS FIXES
---------------
Apollo could still narrate fake module-building steps from Workshop or normal Chat,
for example:

    module_factory__get_contract("MathPhysicsQuiz")
    module_factory__validate("MathPhysicsQuiz")

No pending files were created because that text was never executed.

V7.0.1 routes explicit module creation requests from ALL authoring surfaces through
the real Module Factory:

- normal Chat
- Coding Workspace
- Apollo Workshop
- Self-Improvement Workshop

Apollo now:
1. Calls module_factory__get_contract for real.
2. Gives the language model only module_factory__create_candidate.
3. Rejects narrated Step 1/Step 2 examples as success.
4. Rejects invented module_factory__validate calls.
5. Writes real pending_modules/<module_id>/ files.
6. Runs Apollo's actual validator automatically after creation.
7. Stops when validation passes and waits for user approval.

INSTALL
-------
Close Apollo and replace root workers.py with the patched workers.py.
The regression test is optional and may remain in the root folder.
No storage, config, memory or workspace files are included in the patch.
