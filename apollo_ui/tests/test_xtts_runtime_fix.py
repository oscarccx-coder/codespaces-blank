from pathlib import Path

ROOT = Path(__file__).resolve().parent

installer = (ROOT / "install_xtts_v2.bat").read_text(encoding="utf-8")
for needle in [
    'set "COQUI_VERSION=0.27.5"',
    'set "TRANSFORMERS_VERSION=4.57.6"',
    "isin_mps_friendly",
    "Coqui XTTS import: OK",
    "XTTS CLEAN INSTALL FAILED",
]:
    assert needle in installer, needle

base_installer = (ROOT / "install.bat").read_text(encoding="utf-8")
assert 'import sys,encodings' in base_installer
assert 'INSTALL FAILED' in base_installer
assert 'if errorlevel 1 goto :FAIL' in base_installer

launcher = (ROOT / "start_apollo_ui.bat").read_text(encoding="utf-8")
assert 'set "PYTHONHOME="' in launcher
assert 'set "PYTHONPATH="' in launcher
assert 'import sys,encodings' in launcher

voice = (ROOT / "modules" / "voice_imprint_trainer" / "module.py").read_text(encoding="utf-8")
for needle in [
    '"name": "launch_xtts_installer"',
    'Install / Repair XTTS Engine',
    '"recommended_transformers": "4.57.6"',
]:
    assert needle in voice, needle

print("XTTS runtime fix regression passed.")
