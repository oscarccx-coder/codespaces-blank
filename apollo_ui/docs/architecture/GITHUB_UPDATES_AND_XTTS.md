# Apollo 7.5.13: shared XTTS and GitHub in-app updates

## Shared XTTS v2 model

Apollo uses ONE copy of the voice model, rather than copying gigabytes with each update.

Option A: copy all files from your existing XTTS v2 installation into:
\`apollo_ui/models/voice/xtts_v2/\`

Option B (recommended for upgrades): keep the model in:
\`%LOCALAPPDATA%\Apollo\models\voice\xtts_v2\`

Option C: use a separate disk such as \`F:\Apollo\models\voice\xtts_v2\`.
In Apollo open Voice Imprint Lab, choose the model folder, and Save Backend.
Apollo records the folder in \`storage/state/xtts_model_path.json\`, not Git-tracked \`config.json\`.
The model folder must contain \`config.json\`, \`model.pth\` and \`vocab.json\`.
No XTTS weights or private voice recordings are shipped in program updates.

Apollo looks for a saved explicit choice, a complete bundled drop-in folder,
an existing valid older voice path, and finally the normal shared default.
Nothing is deleted, moved or downloaded automatically.

## One-click updating via GitHub

Inside Apollo: **Settings → Updates → Open Update Centre**.
Select **GitHub Releases**, then **Stable** unless you explicitly want prereleases.

- **Check GitHub**: lists a newer published Apollo Release.
- **Download & Verify**: downloads an update package, verifies the pinned
  Ed25519 signature and every signed file's SHA-256 digest, and stages it.
- **Install & Restart**: installs a previously staged update after explicit confirmation.
- **Update & Restart**: checks, downloads, verifies, launches the external installer,
  closes Apollo, backs up replaced files, runs health checks and relaunches Apollo.
- **Trust GitHub Signing Key (one-time)**: from a GitHub Release, displays the
  public key SHA-256 fingerprint for explicit approval. Verify the fingerprint
  through a separate channel before accepting it. Once imported, the key is
  pinned under \`storage/updates/trust/release_public.pem\`. Never trust a
  replacement key silently.

The signed core release package is distributed via:
\`https://github.com/oscarccx-coder/codespaces-blank/releases\`

The updater does NOT install arbitrary commits, unsigned ZIP files or changed
source directly from a pull request. GitHub is an update **transport**, not
an authorisation system.

### Publishing the first update (developer task)

At present **there are no published GitHub Releases** in this repository.
The in-app updater will correctly report that no update is available until
a real, tested, signed release exists.

After the Windows UI/XTTS smoke test and merge of the verified code into \`main\`:

1. Make sure the app version in \`config.json\` has been increased over the
   user's installed version. The candidate version in this branch is
   \`7.5.13.0\`.
2. Install/authenticate GitHub CLI: \`gh auth login\`.
3. From \`apollo_ui\`, run
   \`python tools/publish_github_release.py --channel stable\`
   to prepare a signed ZIP and see its paths without publishing.
4. Inspect the release files. The signing **private** key stays only in
   ignored \`storage/updates/keys/release_private.pem\`; secure its backup.
   Never include it in a Git commit, release asset or support bundle.
5. Publish after approval using:
   \`python tools/publish_github_release.py --channel stable --publish\`
6. A public GitHub Release now has two assets: \`apollo-7.5.13.0.zip\` and
   \`release_public.pem\`. The user can trust the public key once and then
   install future updates directly inside Apollo.

Development/beta builds can be published as prereleases using their respective
channel; they will not be offered on Stable.

### Updates that fail

The external installer waits for Apollo to exit, keeps a file backup, verifies
the signed manifest, refuses traversal and protected storage/model paths, and
runs \`apollo_health_check.py\` before relaunching. Failed health checks roll
back modified code. The Update Centre can show the last installation result;
full logs are in \`storage/updates/logs/\`.

No updater can guarantee recovery from power loss, full disks or a corrupted
filesystem. Keep a separate system backup. Test updater changes on a copy
before enabling them on your main Apollo installation.

### First installation

Old Apollo installations need the new updater code **once** before they can
use the new Update Centre. If you currently use a Git checkout, obtain this
verified update through the code-only updater after merge to \`main\`.
Do not overwrite locally modified code or config; migrate/commit/stash it first.
