Apollo 7.5.12.13 — Voice Imprint Tuning Lab
24 September 2026

NEW VOICE CONTROLS
------------------
Each Voice Imprint profile can now save its own:
- Speed
- Depth / pitch (semitones)
- Expressiveness / XTTS temperature
- Repetition control
- top-p
- top-k
- Reference conditioning length
- Long-text sentence splitting
- Bass / warmth
- Treble / brightness
- Output gain

PRESETS
-------
Natural
Apollo
Deep
Cinematic
Fast
Stable
Bright

USABILITY
---------
- "Set Selected as Apollo Default Voice" clearly activates that profile.
- Apollo shows whether Voice Imprint routing is ON.
- Saved tuning follows the active profile when Apollo speaks elsewhere through its normal TTS path.
- Test speech uses the current controls immediately, even before saving them.
- "Save Tuning to Selected Voice" persists the settings into that profile.
- "Reset Selected Voice to Natural" restores defaults.

ENGINEERING
-----------
XTTS-native generation controls are sent directly into XTTS:
speed, temperature, repetition penalty, top-k, top-p, conditioning length and text splitting.

Depth/pitch, bass, treble and final gain are applied locally after XTTS with FFmpeg.
The pitch filter compensates tempo so making the voice deeper does not automatically make it slower.

This update does not overwrite storage/, voice profiles, the XTTS model, or existing settings.json.
