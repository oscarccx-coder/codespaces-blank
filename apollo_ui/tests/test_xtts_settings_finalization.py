"""Verify step 10 XTTS configuration without touching real models or audio."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tools" / "configure_xtts_settings.py"
spec = importlib.util.spec_from_file_location("configure_xtts_settings", HELPER)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

PINS = {
    "torch": "2.11.0", "torchvision": "0.26.0", "torchaudio": "2.11.0",
    "torchcodec": "0.16.0", "coqui_tts": "0.27.5", "transformers": "4.57.6",
}


class XTTSFinalizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.model = self.root / "existing model"
        self.model.mkdir()
        for name in mod.REQUIRED_MODEL_FILES:
            (self.model / name).write_text("test only", encoding="utf-8")
        self.ffmpeg = self.root / "shared ffmpeg"
        self.ffmpeg.mkdir()
        self.settings = self.root / "data" / "voice_imprint" / "settings.json"

    def test_preserves_user_preferences_and_creates_a_backup(self):
        self.settings.parent.mkdir(parents=True)
        previous = {"profiles": ["my voice"], "language": "fr", "volume": 0.6}
        self.settings.write_text(json.dumps(previous), encoding="utf-8")
        changed = mod.configure(self.settings, self.model, self.ffmpeg, PINS)
        self.assertEqual(changed["profiles"], ["my voice"])
        self.assertEqual(changed["language"], "fr")
        self.assertEqual(changed["volume"], 0.6)
        self.assertEqual(changed["model_dir"], str(self.model))
        self.assertEqual(changed["runtime_pins"], PINS)
        backup = self.settings.with_name("settings.json.bak")
        self.assertEqual(json.loads(backup.read_text(encoding="utf-8")), previous)
        self.assertFalse(self.settings.with_name("settings.json.tmp").exists())
        self.assertTrue(all((self.model / x).exists() for x in mod.REQUIRED_MODEL_FILES))

    def test_first_configuration_makes_directory_without_backup(self):
        mod.configure(self.settings, self.model, self.ffmpeg, PINS)
        self.assertTrue(self.settings.exists())
        self.assertFalse(self.settings.with_name("settings.json.bak").exists())

    def test_corrupted_existing_json_is_never_overwritten(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text("{damaged", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Preserving"):
            mod.configure(self.settings, self.model, self.ffmpeg, PINS)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), "{damaged")

    def test_missing_model_does_not_modify_settings(self):
        (self.model / "vocab.json").unlink()
        with self.assertRaisesRegex(ValueError, "vocab.json"):
            mod.configure(self.settings, self.model, self.ffmpeg, PINS)
        self.assertFalse(self.settings.exists())

    def test_cli_handles_paths_containing_spaces(self):
        cmd = [sys.executable, str(HELPER), "--settings", str(self.settings),
               "--model-dir", str(self.model), "--ffmpeg-bin", str(self.ffmpeg)]
        for key, value in PINS.items():
            cmd += ["--" + key.replace("_", "-"), value]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(self.settings.read_text())["backend"], "xtts_local")

    def test_windows_batch_uses_safe_helper_and_fast_recovery(self):
        bat = (ROOT / "install_xtts_v2.bat").read_text(encoding="utf-8")
        self.assertIn('if /I "%~1"=="--configure-only"', bat)
        self.assertIn('tools\\configure_xtts_settings.py', bat)
        self.assertNotIn('exec(\\\"try:', bat)
        self.assertLess(bat.index('if /I "%~1"=="--configure-only"'),
                        bat.index('1/10 - Update packaging tools'))
        shortcut = (ROOT / "Setup" / "11_FINISH_XTTS_SETUP.bat").read_text()
        self.assertIn('--configure-only', shortcut)
        self.assertNotIn("pip install", shortcut)


if __name__ == "__main__":
    unittest.main()
