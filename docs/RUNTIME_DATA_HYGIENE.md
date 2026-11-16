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

## Verified owner-run backup before adopting the cleanup

The existing general Apollo backup excludes some module-local databases, audio and
private keys. It is **not sufficient by itself** to protect all previously tracked
runtime files that a normal Git pull might remove.

Before merging PR #66, run the dedicated
`tools/backup_runtime_before_merge.py` from a separately downloaded copy of this
reviewed security branch, on the **current old Git checkout**. The tool only
reads and copies private files. It never changes Git state or Apollo data.

1. Close Apollo and stop its Device Agent, voice worker and other processes
   writing Apollo storage.
2. Inventory with
   `py -3 backup_runtime_before_merge.py --root "F:\Apollo\Apollo-Git" --check`
   (adjust root to the actual Git checkout's top-level directory).
3. Choose a new, private backup directory **outside** the Git checkout, with
   sufficient disk space. For example, use:
   `py -3 backup_runtime_before_merge.py --root "F:\Apollo\Apollo-Git" --destination "E:\Private-Apollo-Backup-Nov2026" --confirm-stopped`
4. Require `verified: true`, check the file count and size, retain the
   `manifest.json` and make a separate trusted copy. An
   `INCOMPLETE-BACKUP.txt` file means **STOP**; the backup did not verify.
5. Keep this backup **private**. It is not encrypted and may include
   recordings, credentials and sensitive information. Do not upload it.

This only verifies copies of discoverable private files while the user
confirms all Apollo writers are stopped. It does not prove the backup covers
external Ollama installations, unrelated personal folders, historical Git
objects, or open SQLite transactions. The original checkout remains intact.

**Safer adoption:** After review/approval and merging the cleanup, create a
*separate* fresh Git clone and explicitly restore/reconcile needed private data
from the verified backup into the new installation. Do not force a Git pull
through the existing updater's incoming-data protection; do not delete the old
installation. This also avoids an automatic tracked-file deletion in the old
checkout. Test the restored instance on Windows before designating it primary.

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
