Apollo 7.5.12.6 — One-Click Voice Build + XTTS Readiness

Install over Apollo 7.5.12.5 with Apollo completely closed.

NEW WORKFLOW
------------
Voice Imprint Lab -> Choose Audio + Build Voice

1. Browse to the audio recording you want to use.
2. Give the voice a profile name.
3. Click "Use This Audio -> Build Voice".
4. Apollo will:
   - copy the source locally
   - convert it to 24 kHz mono WAV
   - split/score speech clips
   - train the acoustic voice signature
   - create an XTTS-ready speaker reference pack
   - activate the completed profile
5. Click "Play Extracted Reference" to hear what Apollo selected.

IMPORTANT XTTS DISTINCTION
--------------------------
Your audio creates the SPEAKER VOICE files.

XTTS config.json and model.pth are the PRETRAINED SPEECH ENGINE used to turn
new text into audio. They cannot be recreated from one speaker recording.

Use "Find Installed XTTS" to locate an existing local installation, or browse
to a local XTTS v2 folder containing config.json + model.pth.

Once both are true:
  speaker_voice_ready = true
  xtts_engine_ready = true

Apollo can Generate New Speech / Speak New Text in the learned voice.

No personal storage/workspace files are included in this patch.
