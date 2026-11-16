# VoiceStudio as Apollo's local voice engine

Apollo uses VoiceStudio as a **separately installed, isolated local backend**, not a dependency inside Apollo's Python venv. The integration adds a first-class **Voice Centre → VoiceStudio** tab to manage its voice/engine selection, cloned profiles, speech preview, connection and backend controls. It also lets the **Open-source Backends** page switch speech and microphone transcription independently.

## Scope
- Text-to-speech routes to \`http://127.0.0.1:3900/v1/audio/speech\`, generates a bounded WAV and plays it via the existing asynchronous speech queue.
- Transcription routes locally to \`/v1/audio/transcriptions\`, preserving existing microphone capture/dictation.
- \`/v1/audio/voices\` populates installed engine IDs and saved profile IDs. User choices persist under \`storage/state/capability_backends.json\` and survive restart.
- Owner-approved clone creation uses \`POST /profiles\`, the user's own reference recording, and an explicit voice-consent checkbox. Nothing is uploaded to a cloud service by Apollo.
- The **Install / repair VoiceStudio** button asks approval before running the checkout's locked Bun dependency install and Python setup. These may download several gigabytes and execute upstream scripts. The **Start backend** button then runs \`bun run dev:api\` from an existing prepared \`debpalash/VoiceStudio\` checkout (its own \`.venv\`). Apollo does **not** install dependencies or download a model, and launches it only after the user clicks. **Stop backend** only stops the process Apollo launched; it never kills an independent VoiceStudio desktop instance.
- Windows System.Speech provides a fallback for failed VoiceStudio reply generation. XTTS remains installed and separately selectable, but does not need to load when VoiceStudio is the speech backend.

## First-use steps on Windows

1. Check which VoiceStudio repository you downloaded. The implementation is written for [debpalash/VoiceStudio](https://github.com/debpalash/VoiceStudio) and its compatible forks. Other projects sharing the same name may have different APIs.
2. Install Bun and uv, then either follow VoiceStudio's upstream instructions or use Apollo's **Prepare VoiceStudio runtime** button with explicit consent to run the upstream installation in that source folder. Verify the engine, its model license, available RAM and memory needs before downloading large weights. Keep Apollo running on Ollama separately.
3. Put the downloaded/extracted source folder beside Apollo, preferably `F:\\Apollo\\VoiceStudio` (or `F:\\Apollo\\VoiceStudio-main`). Apollo auto-detects these locations and one nested archive wrapper. **No duplicate clone or copy of the Git files is required.** Open **Apps → Voice Centre → VoiceStudio**; use **Find downloaded files** or **Browse** if needed. Click **Start VoiceStudio backend (prepared source)**, or launch VoiceStudio yourself; use **Test connection**. The default local API is \`http://127.0.0.1:3900\`.
4. Click **Load VoiceStudio voices & engines**, select an installed engine or the active/default engine, and choose your own saved voice profile. Click **Use selected voice for Apollo replies**.
5. Click **Speak a test sentence**. To use VoiceStudio dictation too, tick **Also use VoiceStudio for Apollo microphone transcription** before saving.
6. Optional: use **Choose reference audio**, check the authorization box, provide a profile name and click **Create VoiceStudio voice profile**. Refresh to select it.

## Guided Windows installation (new)

Open **Apps → Voice Centre → VoiceStudio**, select your previously downloaded
`debpalash/VoiceStudio` source folder (or click **Find downloaded files**),
then click **Check prerequisites**. The check does not install anything.

Click **Install / repair VoiceStudio** to request one explicit approval for:

1. If Bun or uv are missing, install exactly `Oven-sh.Bun` and/or
   `astral-sh.uv` through WinGet. If WinGet is unavailable, setup stops rather
   than running a downloaded PowerShell script without review.
2. Run `bun install --frozen-lockfile` and `bun run setup:api` from the
   selected source checkout. These are third-party scripts that may download
   substantial dependencies, and they install into VoiceStudio's own
   directory/virtualenv, not Apollo's Python environment.
3. Optionally start the localhost backend and perform a bounded health check.
   This step can be disabled using the checkbox. Voice models are still
   separately selected/installed by their owner.

The installer retains local logs under Apollo's `storage/logs/` and returns
diagnostics when prerequisites or upstream setup fail. A long-running Apollo
process may not see a newly installed Bun/uv until restarted. A signed desktop
package is **not** silently installed or launched; this feature prepares the
previously downloaded *source backend* used by Apollo.

The alternative Windows launcher is `Setup/22_SETUP_VOICESTUDIO.bat`.
Double-clicking it only diagnoses. From Command Prompt, use:

```bat
call "Setup\22_SETUP_VOICESTUDIO.bat" --path "F:\Apollo\VoiceStudio" --install --with-prerequisites
```

It demands the owner type `INSTALL` before executing anything and never
deletes or replaces the existing installation.

## Operating and security limits

- Apollo only connects to loopback HTTP and rejects redirects, external URLs, extra URL paths, and oversized inputs/results. Only its owner UI can manage VoiceStudio or create voice clones.
- Engine/model availability is discovered from the running service, not asserted from a package being present. VoiceStudio's local backend may itself download new weights only when deliberately configured in VoiceStudio.
- Models are not copied into Apollo's Git repository or \`.venv\`; keep their license and AGPL obligations separate.
- Starting VoiceStudio from Git source requires preinstalled Bun, uv, a prepared \`.venv\` and a locally verified checkout. Apollo uses only the selected existing source checkout; WinGet package installation and upstream script execution require explicit owner approval.
- Real hardware acceleration, sound output, first-use weights and live dictation require Windows validation on the owner's machine. The offline regression suite covers integration contracts using a fake local server, not real voice quality.
- The full VoiceStudio production UI (dubbing, audiobook editor, model management, voice design and video rendering) remains upstream. Apollo's **speech/dictation/voice-clone** workflow is integrated, but embedding every feature of the third-party product would require separate design and testing.

**Local-folder access:** This pull request changes Apollo's behaviour once installed on the owner's PC. It does not grant ChatGPT access to the owner's `F:` drive, install VoiceStudio automatically, or claim that the owner has already placed the files there. A different project named VoiceStudio will be rejected unless its source layout matches the reviewed repository.
