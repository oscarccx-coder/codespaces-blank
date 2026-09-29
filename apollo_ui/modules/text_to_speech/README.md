# Apollo Speech I/O + Voice Studio v1.3

Offline Windows speech input/output for Apollo using `System.Speech`.

## Voice Studio

Apollo's default spoken-reply profile is stored in:

`storage/speech_voice_profile.json`

Controls:

- Installed Windows voice
- Gender preference: Any / Male / Female
- Accent / culture from voices actually installed on the PC
- Emotion preset
- Depth
- Pitch
- Speed
- Volume
- Preview / Stop / Save / Reset

## Accent behavior

Accent is now a real Windows voice-culture selection rather than a fake pitch preset.

Examples include `en-GB`, `en-US`, `en-AU`, `en-IE`, etc., but only cultures
provided by installed Windows voices appear in Voice Studio.

Selection priority is:

1. Exact installed voice, if one is selected
2. Requested installed accent/culture, with gender preference when possible
3. Gender preference
4. Windows default voice

If you choose an accent that conflicts with a manually selected exact voice,
Voice Studio switches the exact voice to Automatic so the requested accent can
actually take effect.

Emotion/depth/pitch/speed remain SSML prosody modulation; they are not neural
voice conversion.

## Existing features retained

- Apollo reads its own completed replies when Voice is enabled
- Mute / stop speech
- Offline one-shot speech-to-text dictation
- WAV export
- Installed voice and recognizer listing


## v1.3 Natural Speech + Voice Dataset

- Voice delivery modes: Precise, Natural, Expressive.
- Natural speech strips Markdown decoration, skips code/URLs when enabled, uses conversational contractions and inserts sentence/paragraph pauses.
- Dictate can record 16 kHz mono WAV audio first, then transcribe that exact WAV with Windows System.Speech.
- When enabled, audio/transcript pairs are stored under `storage/voice_dataset/` for future TinyVoice training.
- Samples begin unapproved. Use the dataset tools to mark good/bad and approve only clean clips for training.
- Microphone recording requires `sounddevice` and `numpy`; speech recognition remains offline through Windows System.Speech.
