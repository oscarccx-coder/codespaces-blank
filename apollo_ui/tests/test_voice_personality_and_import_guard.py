from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]

main_source = (ROOT / "main.py").read_text(encoding="utf-8")
worker_source = (ROOT / "modules" / "voice_imprint_trainer" / "xtts_worker.py").read_text(encoding="utf-8")

ast.parse(main_source)
ast.parse(worker_source)

for needle in [
    "dry, intelligent, mildly sarcastic personality",
    "Never let sarcasm obscure the answer",
    "When the situation is serious, drop the jokes and be direct",
]:
    assert needle in main_source, needle

for needle in [
    "if legacy is not None:",
    "same top-level TTS namespace",
    "Conflicting legacy TTS package detected",
    "Apollo Voice requires a clean maintained coqui-tts install",
]:
    assert needle in worker_source, needle

assert "if coqui is None and legacy is not None:" not in worker_source

print("Voice conflict guard and Apollo personality regression passed.")
