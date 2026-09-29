Apollo 7.5.12.3 — Update Service + Storage Layout

Install this patch over Apollo 7.5.12.2 with Apollo completely closed.

FIRST START
-----------
Apollo automatically migrates legacy persistent files into categorized storage folders before modules load. It does not overwrite conflicting files; conflicts are preserved under storage/legacy_conflicts/.

UPDATE HOST
-----------
On the machine that builds/releases Apollo:
1. Run publish_current_release.bat
2. Run start_update_server.bat
3. Share only storage/updates/server/release_public.pem with each Apollo device once.

CLIENT DEVICE
-------------
Open Apollo Update Manager, import the public key, configure the update host URL and channel, then use Check / Stage / Install + Restart.

The updater preserves user storage/workspace and automatically rolls back core file changes when the health check fails.
