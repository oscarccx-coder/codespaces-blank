# Apollo Update System — 7.5.12.3 Foundation

## Goal
Apollo devices can receive signed releases from one update host without manually copying patch files to every device.

## Development host
1. Run `publish_current_release.bat` to create a signed development release under `storage/updates/server/`.
2. The first publish creates a private/public Ed25519 key pair under `storage/updates/keys/`.
3. Keep `release_private.pem` only on the release-authority machine.
4. Run `start_update_server.bat` to serve the release directory on port 8765.

## Client device (one-time trust setup)
1. Open **Apollo Update Manager**.
2. Import the release host's `release_public.pem` once.
3. Set the server URL, for example `http://192.168.1.20:8765`.
4. Select Development/Beta/Stable/Pinned channel.

After that: **Check → Stage Update → Install + Restart**. No patch dragging is needed for normal releases.

## Safety
- Release manifests are signed with Ed25519.
- Every payload file is SHA-256 checked against the signed manifest.
- `storage/`, `workspace/`, `pending_modules/` and user `config.json` are protected from package replacement.
- The external updater backs up replaced files and preserves config before changing core files.
- Static health checks run after installation. Failure triggers automatic rollback.
- Only the config `version` field is changed; user model/settings remain intact.

## Multi-device direction
This release provides the distribution backbone. The later Fleet Manager will add centralized device status, staged rollout and remote rollout policy on top of the same signed package format.
