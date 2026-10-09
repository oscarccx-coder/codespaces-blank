from pathlib import Path
import importlib.util
import tempfile
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "modules" / "voice_imprint_trainer" / "module.py"

spec = importlib.util.spec_from_file_location("voice_tuning_module", MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

with tempfile.TemporaryDirectory() as td:
    base = Path(td)
    m = mod.Module({"base_dir": str(base), "validation": True})

    folder = m._profile_dir("test")
    folder.mkdir(parents=True, exist_ok=True)
    m._save_json(folder / "profile.json", {
        "id": "test",
        "name": "Test Voice",
        "signature_trained": True,
    })
    pack = folder / "voice_pack"
    pack.mkdir()
    m._write_wav(pack / "reference.wav", 24000, np.zeros(24000, dtype=np.float32))
    m._save_json(pack / "voice_pack.json", {"ready": True})

    saved = m.run("set_voice_tuning", {
        "profile_id": "test",
        "tuning": {
            "speed": 9,
            "pitch_semitones": -99,
            "temperature": 0.77,
            "bass_db": 3,
            "enable_text_splitting": True,
        },
    })
    assert saved["tuning"]["speed"] == 1.4
    assert saved["tuning"]["pitch_semitones"] == -6.0
    assert saved["tuning"]["temperature"] == 0.77
    assert saved["tuning"]["bass_db"] == 3.0

    got = m.run("get_voice_tuning", {"profile_id": "test"})
    assert got["tuning"] == saved["tuning"]
    assert "Apollo" in got["presets"]
    assert "Deep" in got["presets"]

    m._backend_status = lambda: {"ready_for_xtts": True}
    activated = m.run("activate_profile", {"profile_id": "test"})
    assert activated["activated"] is True
    assert activated["voice_tuning"]["temperature"] == 0.77
    assert m._active()["enabled"] is True

    captured = {}
    class Audio:
        sample_rate = 24000
    class Config:
        audio = Audio()
    class FakeModel:
        def synthesize(self, text, config, **kwargs):
            captured.update(kwargs)
            return {"wav": np.zeros(2400, dtype=np.float32)}

    fake_model_dir = base / "fake_xtts"
    fake_model_dir.mkdir()
    for filename in ("config.json", "model.pth", "vocab.json"):
        (fake_model_dir / filename).write_text("{}", encoding="utf-8")
    m._settings = lambda: {
        "backend": "xtts_local",
        "model_dir": str(fake_model_dir),
        "language": "en",
        "device": "cpu",
        "process_isolation": False,
    }
    m._load_xtts = lambda: ((FakeModel(), Config()), m._settings(), False)
    m._reference_wav = lambda pid: pack / "reference.wav"
    m._postprocess_voice_wav = lambda *a, **k: {"applied": [], "warning": ""}

    result = m.run("synthesize", {
        "text": "Apollo voice test",
        "profile_id": "test",
        "tuning": {
            "speed": 1.12,
            "temperature": 0.71,
            "repetition_penalty": 2.3,
            "top_k": 44,
            "top_p": 0.82,
            "gpt_cond_len": 8,
            "enable_text_splitting": True,
        },
    })
    assert captured["speed"] == 1.12
    assert captured["temperature"] == 0.71
    assert captured["repetition_penalty"] == 2.3
    assert captured["top_k"] == 44
    assert captured["top_p"] == 0.82
    assert captured["gpt_cond_len"] == 8
    assert captured["enable_text_splitting"] is False
    assert result["tuning"]["speed"] == 1.12

source = MODULE.read_text(encoding="utf-8")
for required in [
    "Shape + Save This Voice",
    "Set Selected as Apollo Default Voice",
    "Depth / pitch",
    "Expressiveness",
    "Bass / warmth",
    "Treble / brightness",
    "Save Tuning to Selected Voice",
    "VOICE_TUNING_PRESETS",
]:
    assert required in source, required

tts = (ROOT / "modules" / "text_to_speech" / "module.py").read_text(encoding="utf-8")
assert 'arguments.get("use_voice_imprint", True)' in tts
assert 'self._voice_imprint_call(' in tts

print("Voice Imprint tuning + global routing regression passed.")
