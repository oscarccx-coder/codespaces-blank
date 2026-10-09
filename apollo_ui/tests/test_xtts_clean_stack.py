from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
installer = (ROOT / "install_xtts_v2.bat").read_text(encoding="utf-8")
voice = (ROOT / "modules" / "voice_imprint_trainer" / "module.py").read_text(encoding="utf-8")

for needle in [
    'set "TORCH_VERSION=2.11.0"',
    'set "TORCHVISION_VERSION=0.26.0"',
    'set "TORCHAUDIO_VERSION=2.11.0"',
    'set "TORCHCODEC_VERSION=0.16.0"',
    'set "COQUI_VERSION=0.27.5"',
    'set "TRANSFORMERS_VERSION=4.57.6"',
    'set "PYTORCH_INDEX=https://download.pytorch.org/whl/cu128"',
    'pip uninstall -y torch torchvision torchaudio torchcodec coqui-tts TTS transformers tokenizers',
    '--no-cache-dir --force-reinstall "torch==%TORCH_VERSION%"',
    '--no-cache-dir --force-reinstall "torchcodec==%TORCHCODEC_VERSION%"',
    'pip check',
]:
    assert needle in installer, needle

# The installer must no longer branch on arbitrary torch 2.9/2.10/2.11 mapping.
assert 'if "%TORCH_MM%"=="2.9"' not in installer
assert 'if "%TORCH_MM%"=="2.10"' not in installer
assert 'if "%TORCH_MM%"=="2.11"' not in installer

for needle in [
    '"expected_xtts_runtime": expected_runtime',
    '"xtts_runtime_mismatches": runtime_mismatches',
    '"xtts_runtime_pins_ok": not runtime_mismatches',
    'and not runtime_mismatches',
]:
    assert needle in voice, needle

print("XTTS clean runtime stack regression passed.")
