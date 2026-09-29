Apollo 7.5.12.10 — Clean XTTS Runtime Stack

The existing machine had PyTorch 2.14, which was outside the old version-specific
TorchCodec mapping in Apollo's installer.

Rather than continuing to chase whatever newest packages pip resolves, this release
uses one known runtime contract and installs it from a clean state.

Runtime:
  torch 2.11.0 + CUDA 12.8
  torchvision 0.26.0
  torchaudio 2.11.0
  torchcodec 0.16.0
  coqui-tts 0.27.5
  transformers 4.57.6

To install:
  1. Extract safe cumulative update over Apollo.
  2. Run apply_update_7_5_12_10.bat.
  3. Run clean_reinstall_xtts_runtime.bat.
  4. Restart Apollo.

The clean installer does NOT delete user voice profiles or a completed XTTS model.
