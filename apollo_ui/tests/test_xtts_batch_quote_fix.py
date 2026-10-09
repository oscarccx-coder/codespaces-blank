from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
installer = (ROOT / "install_xtts_v2.bat").read_text(encoding="utf-8")

# The original bug came from running a quoted python.exe inside FOR /F command
# substitution. The current clean installer must never reintroduce that pattern.
bad_patterns = [
    'for /f "usebackq delims=" %%V in (`"%PYTHON_EXE%" -c "import torch;',
    "for /f %%",
]
for bad in bad_patterns[:1]:
    assert bad not in installer, bad

assert '"%PYTHON_EXE%" -c "import torch,torchvision,torchaudio;' in installer
assert 'torch==%TORCH_VERSION%' in installer
assert 'torchcodec==%TORCHCODEC_VERSION%' in installer

print("XTTS Windows batch quote regression passed.")
