# Apollo Voice Imprint Lab v1.0

Voice Imprint Lab converts a rights-authorised single-speaker audio track into an
Apollo voice profile.

## What it actually learns

The module includes a small local 64→48→16→48→64 acoustic autoencoder written
with NumPy. It trains on spectral/prosody features from the imported speaker and
creates a 16-dimensional voice/style signature plus a consistency score. This is
a real neural network, but it is deliberately **not** claimed to be a complete
text-to-speech system.

For high-quality speech generation, Voice Imprint uses an optional already-installed
**local XTTS** neural model and supplies the selected voice profile's representative
reference clip. This is much more practical than attempting to train an entire
text-to-waveform model from a single audiobook.

## Rights gate

Import is blocked until the user confirms they own/have permission to use the
recording and speaker's voice for synthesis. A commercial audiobook should only be
used when the necessary speaker/rightsholder permission or licence exists.

## Audio pipeline

1. Audio source (WAV/MP3/M4A/M4B/FLAC/etc.)
2. ffmpeg → 24 kHz mono PCM WAV
3. speech/silence detection
4. 3–15 second quality-scored clips
5. acoustic feature extraction
6. local neural voice-signature training
7. representative reference selection
8. optional XTTS local synthesis

## External requirements

- `ffmpeg.exe` on PATH is required for importing normal audiobook formats.
- NumPy is already part of Apollo 7.x.
- XTTS synthesis is optional and requires compatible local installations of
  PyTorch + Coqui TTS and an XTTS model folder containing `config.json` and
  `model.pth`. Apollo does **not** download these automatically.
- `faster-whisper` is optional for generating text-aligned training manifests.

## Storage

Profiles are saved under:

`storage/voice_imprint/profiles/<profile_id>/`

The active voice pointer is:

`storage/voice_imprint/active_profile.json`

Generated speech is saved under:

`storage/voice_imprint/output/`
