from pathlib import Path
import sys
import tempfile
import shutil
import json
import wave
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules" / "voice_imprint_trainer"))
from module import Module, SAMPLE_RATE

# We can test pack/readiness deterministically without ffmpeg by creating a
# synthetic prepared profile containing three WAV clips.
tmp = Path(tempfile.mkdtemp(prefix="apollo_voice_pack_test_"))
try:
    module = Module({"base_dir": str(tmp), "validation": True})
    profile_id = "test_voice"
    folder = module._profile_dir(profile_id)
    clips = folder / "clips"
    clips.mkdir(parents=True, exist_ok=True)

    rows = []
    for i in range(3):
        path = clips / f"clip_{i+1:04d}.wav"
        t = np.arange(SAMPLE_RATE, dtype=np.float32) / SAMPLE_RATE
        audio = 0.15 * np.sin(2 * np.pi * (180 + i * 30) * t)
        module._write_wav(path, SAMPLE_RATE, audio)
        rows.append({
            "audio": f"clips/{path.name}",
            "duration": 1.0,
            "score": 0.9 - i * 0.05,
            "quality": "good",
            "approved_for_training": True,
        })

    module._save_records(profile_id, rows)
    module._save_profile({
        "id": profile_id,
        "name": "Test Voice",
        "created_at": "now",
        "reference_clip": rows[0]["audio"],
        "signature_trained": True,
        "signature": {},
    })
    (folder / "voice_signature.json").write_text("{}", encoding="utf-8")
    (folder / "voice_signature_net.npz").write_bytes(b"test")

    pack = module._prepare_voice_pack(profile_id)
    assert pack["ready"]
    assert (folder / "voice_pack" / "reference.wav").exists()
    manifest = json.loads((folder / "voice_pack" / "voice_pack.json").read_text(encoding="utf-8"))
    assert manifest["speaker_files_ready"] is True
    assert manifest["requires_shared_engine"]["files"] == ["config.json", "model.pth"]

    readiness = module._voice_readiness(profile_id)
    assert readiness["speaker_voice_ready"] is True
    assert readiness["xtts_engine_ready"] is False
    assert readiness["ready_to_generate_new_speech"] is False

    names = {tool["name"] for tool in module.tools()}
    for required in {"build_voice_from_audio", "voice_readiness", "find_xtts_model", "play_reference"}:
        assert required in names

    source = (ROOT / "modules" / "voice_imprint_trainer" / "module.py").read_text(encoding="utf-8")
    assert "Use This Audio → Build Voice" in source
    assert "Find Installed XTTS" in source
    assert "Play Extracted Reference" in source

    print("One-click voice build regression passed.")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
