from pathlib import Path
import sys
import tempfile
import shutil
import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "modules" / "voice_imprint_trainer"))
from module import Module

# Numeric trainer callback regression: must report bounded live epoch/loss state.
matrix = np.random.default_rng(42).normal(size=(8, 64)).astype(np.float32)
updates = []
result = Module._train_autoencoder(
    matrix,
    epochs=40,
    progress_callback=lambda epoch, total, loss: updates.append((epoch, total, loss)),
)
assert updates
assert updates[0][0] >= 1
assert updates[-1][0] == 40
assert updates[-1][1] == 40
assert isinstance(updates[-1][2], float)
assert result["embedding"].shape == (16,)

source = (ROOT / "modules" / "voice_imprint_trainer" / "module.py").read_text(encoding="utf-8")
for needle in [
    '"name": "training_status"',
    'QProgressBar',
    'threading.Thread(',
    'training_signals.progress.connect(apply_training_state)',
    'Training epoch {epoch}/{total}',
    '"phase": "complete"',
    '"phase": "error"',
]:
    assert needle in source, needle

print("Voice training progress regression passed.")
