# Runtime data cleanup — owner review required

This forward-only change removes private runtime files from Git's index.
It does not erase history, revoke deployed credentials, or certify no secrets.
No production token or replacement credential belongs in this PR.

The guard rejects nested storage, databases, logs, audio, runtime workspaces,
models, environment files and key files, including forced additions. Its separate
secret-pattern scan checks indexed blobs and reports paths/rules only. It is a
limited detector, not a comprehensive credential audit or history purge.

## Before updating an existing installation

STOP: a later Git pull/check-out of tracked-file removals can delete those files
from an existing workstation. `git rm --cached` preserves files only in the
checkout where that command is run. A GitHub merge does not migrate the PC.

Oscar must first stop Apollo/device-agent processes and make a verified private
backup of all runtime directories (including module-local storage), audio,
settings and keys. Review the incoming removal list against the backup. Use a
separately reviewed data-preserving adoption procedure; do not use reset/clean,
discard local changes, or bypass an updater that refuses incoming data changes.
Restore/reconcile the current local data from the backup after adoption; never
substitute the old public database for newer private data.

## Immediate device credential action

On every installation sharing the exposed token, stop the Device Agent, use
Apps > Device Agent > Rotate Token, and update/re-enrol trusted Fleet authorities
before restarting. Do not copy the replacement token into chat, commits or logs.
Rotation in a development checkout does not revoke the token in other copies.
Review exposed Runtime action logs and Fleet configurations for other copies.

## Phase 1 prerequisite

Only Oscar merges this PR. Phase 1 remains blocked until that merge and review.
Phase 1 must test that `apollo_ui/storage/databases/apollo_missions.db` is ignored
by Git; the new guard must also reject a forced addition of that path.
Include review-stage dependencies and approval-without-passing-tests in Phase 3
acceptance planning. No other open PR is changed by this cleanup.
