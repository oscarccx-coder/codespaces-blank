# 2026-10-14 Foundry code-worker handoff (experimental)

## New
- A "Plan My Project" request starts a bounded five-task sequence. An architect can provide draft context to a later implementer; the implementation stage proposes JSON source files instead of only narrative.
- File proposals are staged in the selected project's private workspace, limited to eight small UTF-8 files. Symlinks, path traversal, unsafe target directories and overwriting user-edited/unowned files are refused.
- Implementation files receive Apollo's non-executing syntax/UI-backend static checks before the worker advances.
- If an implementation cannot be staged or verified, Foundry retries up to three total attempts. After two failed attempts, an enabled "Research public docs" option searches approved documentation sources using *generic technical queries only*. Project text, code and raw errors are not transmitted as search terms.
- The activity feed records attempts, generated filenames, static results, and source links. Online information is untrusted context, never automatically executed instructions.
- Tester/reviewer/integrator drafts are delayed until an implementation provides files with passing static checks. These drafts remain unapproved.

## Scope and remaining work
- Source generation is experimental, especially with the local 7B model. Large projects should be broken into smaller independently verifiable components.
- Passed static checks **do not** prove runtime functionality, Casimir physics accuracy, or working GUI controls.
- The Docker sandbox remains an explicit, separate user-authorised runtime test; generated source never runs on the host.
- There is no automatic build/install/deploy, no background persistence of model jobs across Apollo restarts, and no permission to modify Apollo's own trusted source files.
- Users should keep backups, inspect staged files and test with the sandbox before approving generated application output.

## Verification
- Four repeated local safety-test passes for file ownership, traversal, invalid JSON and symlinks.
- GitHub Actions Python regression, Windows UI and isolated Docker smoke checks are the authoritative platform checks for this commit; inspect their run results before installing.
