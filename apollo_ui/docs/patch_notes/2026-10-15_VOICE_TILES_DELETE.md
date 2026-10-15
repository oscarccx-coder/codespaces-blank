# Voice Center: readable saved voice tiles and per-voice deletion

## Fixed
- The Voice Profiles list no longer relies on theme-dependent flat button text in tiny default-height QListWidget rows. Each row now has a 58-pixel item height before attaching the custom tile, an explicitly legible voice name, and a readable readiness status.
- Every saved voice has its own **Delete** button beside the **⋮** menu. The menu retains Select, Use as Apollo voice, Retrain, Rename, Delete, Move up and Move down.
- Delete selects the exact clicked profile ID, prompts for confirmation, and moves only that voice folder into the local `storage/media/voice_imprint/deleted_profiles` archive. Deleting an active voice deactivates its routing. Shared XTTS models are never deleted.
- Settings → Apps descriptions now display actual newlines rather than literal `\\n` characters.

## Validation
- Added Qt smoke coverage checking two distinct saved voices, row sizes, names, training status and targeted deletion with recovery archive.
- Added headless structural checks for visible row labels, direct Delete wiring and correct Settings Apps newline.
- Training/generation-in-progress protections and explicit confirmation remain enforced.

## Update
`git pull origin main`, then restart Apollo and open Settings → Apps → Voice Center.
