from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
installer = (ROOT / "install_xtts_v2.bat").read_text(encoding="utf-8")
voice = (ROOT / "modules" / "voice_imprint_trainer" / "module.py").read_text(encoding="utf-8")

for needle in [
    'set "TORCHCODEC_VERSION=0.16.0"',
    "Gyan.FFmpeg.Shared",
    "os.add_dll_directory",
    'set "XTTS_ROOT=%LOCALAPPDATA%\\Apollo\\models\\voice"',
    'set "XTTS_TARGET=%XTTS_ROOT%\\xtts_v2"',
    "settings.json",
]:
    assert needle in installer, needle

for needle in [
    '"torchcodec_required": torchcodec_required',
    '"torchcodec_ready": torchcodec_ok',
    '"coqui_tts_import_error": tts_error',
    'Path(os.environ["LOCALAPPDATA"]) / "Apollo" / "models" / "voice"',
    'backend_settings.migrated.json',
    'self._prepare_xtts_runtime(settings)',
]:
    assert needle in voice, needle

print("XTTS TorchCodec/C-drive regression passed.")
