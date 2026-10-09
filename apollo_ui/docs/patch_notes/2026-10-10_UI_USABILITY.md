# Apollo 7.5.13.9: Usability and Repository Cleanup

Date: 10 October 2026

## Voice management
- Each voice profile now has its own three-dot menu: use, test, retrain,
  rename, reorder and recoverable delete.
- Removed the row of global management buttons that required users to move
  through the entire Voice Imprint page.
- Put XTTS backend configuration and acoustic tuning behind an expandable
  Advanced Voice Controls panel.
- Added scrolling inside the detailed Voice Imprint panel to work on
  smaller windows.

## Learning and reasoning
- Simplified the main learning view to adding a topic, generating questions
  and **Research These Topics**.
- Research reads public sources and saves notes in local storage through the
  existing training-module research backend.
- Research is deliberately user-triggered and capped at five topics per pass.
- Advanced memory search, question authoring and evidence entry remain available
  under More Options. Fetched text is source material, not automatically
  verified truth.

## Updates
- Primary update controls are now **Check for Updates** and **Update & Restart**.
- Signing-key trust, source/channel selection, staged installs and diagnostic
  JSON remain available under expandable Advanced and Technical Details.
- Code updates continue through verified, signed release packages with the
  existing backup and rollback safeguards. User models and storage stay outside
  release payloads; signing-key trust must be verified once.
- Release version metadata aligned to 7.5.13.9. A merged commit by itself
  does not publish a signed downloadable release.

## Repository
- Moved 46 developer test files from the `apollo_ui/` root into
  `apollo_ui/tests/` and updated CI/Pi/release commands accordingly.
- Removed developer tests from future signed update ZIP payloads.
- Patch notes are centralized in `docs/patch_notes/`, while launch,
  recovery and update entry points remain in the application root for
  compatibility.

## Validation still required
- Run Linux GitHub Actions regression and Pi checks.
- Smoke-test PySide6 Voice, Learning and Update Centre on Windows.
- Test XTTS with the installed local model, and update/rollback with a
  signed release on a non-production copy before promoting stable.
