# Apollo XTTS Runtime — 7.5.12.10

Apollo installs XTTS packages only inside `apollo_ui/.venv`, never globally. It treats the XTTS Python runtime as a controlled stack rather than
attempting to adapt to whichever newest PyTorch packages happen to be installed.

## Pinned Windows runtime

- torch 2.11.0
- torchvision 0.26.0
- torchaudio 2.11.0
- torchcodec 0.16.0
- coqui-tts 0.27.5
- transformers 4.57.6

PyTorch, torchvision and torchaudio are installed from the official CUDA 12.8
PyTorch wheel index. TorchCodec is installed after the matching PyTorch family.
Coqui is installed after the media stack, and Transformers is pinned last so a
dependency resolver cannot silently leave Apollo on an incompatible 5.x build.

## Prerequisite

Run `INSTALL_REQUIREMENTS.bat` to create Apollo's private environment first. Optionally use `INSTALL_REQUIREMENTS.bat --voice` to install both core and XTTS requirements. No system Python packages are removed. The GPU stack is large, and user-scoped FFmpeg Shared may be installed separately by WinGet.

## Clean-install order

1. upgrade pip/setuptools/wheel
2. uninstall conflicting Torch/Coqui/Transformers packages **within Apollo's private .venv only**
3. locate/install shared FFmpeg
4. install pinned PyTorch CUDA stack
5. install pinned TorchCodec
6. install Coqui-TTS
7. pin Transformers
8. import-test everything and run `pip check`
9. download XTTS only if model files are absent
10. configure Voice Imprint using the separate `tools/configure_xtts_settings.py` helper, preserving other settings and backing up existing JSON. If this last step fails, `Setup/11_FINISH_XTTS_SETUP.bat` rechecks the model/config and retries **without** repeating package installation. Malformed existing settings are preserved instead of silently discarded.

## Persistent data

The clean runtime reinstall does not delete:
- Voice Imprint profiles/reference audio
- a complete XTTS model
- Apollo user storage

The shared XTTS model remains under:
`%LOCALAPPDATA%\Apollo\models\voice\xtts_v2`

## GPU performance verification

On Windows, Apollo's isolated XTTS worker must launch via `apollo_ui/.venv/Scripts/python.exe`, matching the interpreter used by the pinned CUDA-enabled PyTorch installer. Previously using the GUI process's `sys.executable` could silently select a different Python version, or accidentally launch a bundled Apollo executable.

Before reinstalling packages, run `Setup/17_CHECK_XTTS_GPU.bat`. The read-only diagnostic shows the actual worker Python, torch and CUDA build, driver visibility, GPU name and a tiny CUDA operation. It does **not** modify installed models, voices or packages.

In Voice Imprint Lab > Advanced Settings, select **Device = cuda** and save. This prevents auto CPU fallback. The new **Check XTTS GPU / CUDA** button obtains diagnostic results from the isolated worker, in a separate thread from the UI. If CUDA cannot be used, synthesis fails with a useful message rather than pretending to be accelerated.

On a healthy installation, the worker keeps its model and per-speaker conditioning cached across requests. It wraps model inference in `torch.inference_mode()`, reports conditioning and generation duration separately, and forwards the selected synthesis tuning. High CPU use can still come from tokenisation, reference audio decoding and WAV preparation; GPU percentage in Windows Task Manager's default 3D chart does not measure CUDA compute reliably. Inspect the **CUDA / Compute** graph, GPU memory and `nvidia-smi` while generating.

If the GPU is not visible, check the installed driver and CUDA-enabled PyTorch in Apollo's own `.venv`. Only use `Setup/04_REPAIR_VOICE.bat` after examining the diagnostic; that installer replaces PyTorch/Coqui inside Apollo's private environment and may need substantial disk space. Do not reinstall global Python or move model weights just to enable CUDA.

**Verification caveat:** Program-level tests use mock Torch objects. Performance gains require repeated measurements on the actual RTX hardware with identical text, model and audio reference; neither a CUDA check nor a green CI build proves real-world speedup.
