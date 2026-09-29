Apollo 7.5.03 — Voice Imprint Lab

INSTALL
-------
1. Close Apollo.
2. Extract this patch over your Apollo 7.5.02 installation.
3. Do not delete storage/, workspace/, pending_modules/ or config.json.
4. Start Apollo and open Settings -> Apps -> Voice Imprint Lab.

IMPORT REQUIREMENT
------------------
ffmpeg.exe must be installed and available on PATH for audiobook/MP3/M4B/etc. import.

NEURAL VOICE SYNTHESIS
----------------------
The module itself trains a lightweight NumPy acoustic voice-signature autoencoder.
For actual high-quality neural speech it can use an OPTIONAL local XTTS installation.
Apollo does not download XTTS/PyTorch/Coqui models or packages automatically.

Point Voice Imprint Lab at an already-installed local XTTS model directory containing:
  config.json
  model.pth

If the neural backend is unavailable, normal Apollo speech automatically falls back to Windows System.Speech.

VOICE RIGHTS
------------
Only import a voice/recording that you own or have permission/licensing to use for synthesis.

USER DATA
---------
This patch excludes config.json, storage/, workspace/, pending_modules/, ui_state.json and modules_state.json.
