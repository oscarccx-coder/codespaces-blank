Apollo 7.5.12.14 — Voice Performance Hotfix

- Automatically chunks long speech below XTTS' hard 400-token input limit using XTTS' own tokenizer.
- Native XTTS sentence splitting is always disabled; no spaCy install is required.
- Voice Imprint Lab synthesis runs in a background thread so the Qt UI stays responsive.
- Normal Apollo speak_text queues neural generation in a background worker.
- Multiple speech requests are coalesced so a backlog cannot progressively slow Apollo down.
- XTTS GPU inference is serialized.
- Speaker conditioning latents are cached for repeated speech with the same profile/reference.
- Long text is stitched back into one WAV with short pauses between chunks.

No user voice profiles, XTTS model files, settings, memory or workspace are overwritten.
