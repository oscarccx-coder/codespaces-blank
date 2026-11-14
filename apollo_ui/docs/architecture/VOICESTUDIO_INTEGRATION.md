# VoiceStudio as Apollo's local voice engine

Apollo uses VoiceStudio as a **separately installed, isolated local backend**, not a dependency inside Apollo's Python venv. The integration adds a first-class **Voice Centre → VoiceStudio** tab to manage its voice/engine selection, cloned profiles, speech preview, connection and backend controls. It also lets the **Open-source Backends** page switch speech and microphone transcription independently.

## Scope
- Text-to-speech routes to \`http://127.0.0.1:3900/v1/audio/speech\`, generates a bounded WAV and plays it via the existing asynchronous speech queue.
- Transcription routes locally to \`/v1/audio/transcriptions\`, preserving existing microphone capture/dictation.
- \`/v1/audio/voices\` populates installed engine IDs and saved profile IDs. User choices persist under \`storage/state/capability_backends.json\` and survive restart.
- Owner-approved clone creation uses \`POST /profiles\`, the user's own reference recording, and an explicit voice-consent checkbox. Nothing is uploaded to a cloud service by Apollo.
- The optional **Start backend** button runs \`bun run dev:api\` from an existing prepared \`debpalash/VoiceStudio\` checkout (its own \`.venv\`). Apollo does **not** install dependencies or download a model, and launches it only after the user clicks. **Stop backend** only stops the process Apollo launched; it never kills an independent VoiceStudio desktop instance.
- Windows System.Speech provides a fallback for failed VoiceStudio reply generation. XTTS remains installed and separately selectable, but does not need to load when VoiceStudio is the speech backend.

## First-use steps on Windows

1. Check which VoiceStudio repository you downloaded. The implementation is written for [debpalash/VoiceStudio](https://github.com/debpalash/VoiceStudio) and its compatible forks. Other projects sharing the same name may have different APIs.
2. Follow VoiceStudio's README to install its *own* runtime and a voice engine. From the source root, its current workflow uses Bun + uv and \`bun run setup:api\`. This changes only that checkout, with the user's consent. Verify the engine, its model license, available RAM and memory needs before downloading large weights. Keep Apollo running on Ollama separately.
3. Open **Apps → Voice Centre → VoiceStudio**. Enter the Git checkout path. Click **Start VoiceStudio backend (prepared source)**, or launch VoiceStudio yourself; use **Test connection**. The default local API is \`http://127.0.0.1:3900\`.
4. Click **Load VoiceStudio voices & engines**, select an installed engine or the active/default engine, and choose your own saved voice profile. Click **Use selected voice for Apollo replies**.
5. Click **Speak a test sentence**. To use VoiceStudio dictation too, tick **Also use VoiceStudio for Apollo microphone transcription** before saving.
6. Optional: use **Choose reference audio**, check the authorization box, provide a profile name and click **Create VoiceStudio voice profile**. Refresh to select it.

## Operating and security limits

- Apollo only connects to loopback HTTP and rejects redirects, external URLs, extra URL paths, and oversized inputs/results. Only its owner UI can manage VoiceStudio or create voice clones.
- Engine/model availability is discovered from the running service, not asserted from a package being present. VoiceStudio's local backend may itself download new weights only when deliberately configured in VoiceStudio.
- Models are not copied into Apollo's Git repository or \`.venv\`; keep their license and AGPL obligations separate.
- Starting VoiceStudio from Git source requires preinstalled Bun, uv, a prepared \`.venv\` and a locally verified checkout. Apollo never auto-installs its source or executes commands fetched from the internet.
- Real hardware acceleration, sound output, first-use weights and live dictation require Windows validation on the owner's machine. The offline regression suite covers integration contracts using a fake local server, not real voice quality.
- The full VoiceStudio production UI (dubbing, audiobook editor, model management, voice design and video rendering) remains upstream. Apollo's **speech/dictation/voice-clone** workflow is integrated, but embedding every feature of the third-party product would require separate design and testing.
