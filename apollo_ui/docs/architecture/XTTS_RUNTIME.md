# Apollo XTTS Runtime — 7.5.12.10

Apollo now treats the XTTS Python runtime as a controlled stack rather than
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

## Clean-install order

1. upgrade pip/setuptools/wheel
2. uninstall the conflicting Torch/Coqui/Transformers runtime
3. locate/install shared FFmpeg
4. install pinned PyTorch CUDA stack
5. install pinned TorchCodec
6. install Coqui-TTS
7. pin Transformers
8. import-test everything and run `pip check`
9. download XTTS only if model files are absent
10. configure Voice Imprint

## Persistent data

The clean runtime reinstall does not delete:
- Voice Imprint profiles/reference audio
- a complete XTTS model
- Apollo user storage

The shared XTTS model remains under:
`%LOCALAPPDATA%\Apollo\models\voice\xtts_v2`
