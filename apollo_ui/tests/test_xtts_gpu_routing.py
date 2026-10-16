"""XTTS CUDA routing regression tests. No GPU, real Torch or TTS model is loaded."""
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import tempfile
import unittest

from modules.voice_imprint_trainer.xtts_worker import XTTSEngine
from modules.voice_imprint_trainer.module import Module


class FakeCuda:
    def __init__(self, available=True):
        self.available = available
        self.sync_calls = 0

    def is_available(self):
        return self.available

    def get_device_name(self, index):
        return "NVIDIA RTX 3060"

    def synchronize(self):
        self.sync_calls += 1


class FakeTorch:
    __version__ = "fake-cu128"
    __file__ = "fake-torch"
    version = SimpleNamespace(cuda="12.8")

    def __init__(self, available=True):
        self.cuda = FakeCuda(available)

    def inference_mode(self):
        return nullcontext()


class FakeModel:
    def __init__(self):
        self.requests = []

    def inference(self, **kwargs):
        self.requests.append(kwargs)
        return {"wav": [0.01, 0.02]}


class XTTSGpuWorkerTests(unittest.TestCase):
    def setUp(self):
        self.engine = XTTSEngine()
        self.engine.torch = FakeTorch()

    def test_auto_uses_cuda_and_explicit_cuda_refuses_cpu_fallback(self):
        self.assertEqual(self.engine._choose_device("auto"), "cuda")
        self.assertEqual(self.engine._choose_device("cuda"), "cuda")
        self.engine.torch.cuda.available = False
        self.assertEqual(self.engine._choose_device("auto"), "cpu")
        with self.assertRaisesRegex(RuntimeError, "Refusing to silently fall back"):
            self.engine._choose_device("cuda")
        self.assertEqual(self.engine._choose_device("cpu"), "cpu")

    def test_cuda_status_reports_worker_python_not_main_window(self):
        status = self.engine.cuda_status()
        self.assertTrue(status["cuda_available"])
        self.assertEqual(status["gpu_name"], "NVIDIA RTX 3060")
        self.assertEqual(status["cuda_build"], "12.8")
        self.assertTrue(status["python_executable"])
        self.engine.torch.cuda.available = False
        self.assertFalse(self.engine.cuda_status()["cuda_available"])

    def test_worker_inference_uses_tuning_and_reports_cuda_timings(self):
        with tempfile.TemporaryDirectory() as root:
            self.engine.model_dir = root
            self.engine.model = FakeModel()
            self.engine.device = "cuda"
            self.engine._conditioning = lambda _: ("latent", "embedding")
            self.engine._save_wav = lambda data, output: 1.0
            self.engine.load = lambda *a, **k: {"cached": True, "cuda_available": True, "cpu_fallback": False}
            result = self.engine.synthesize({
                "text": "Hello there", "reference": "fake-speaker.wav",
                "output_path": str(Path(root) / "out.wav"),
                "tuning": {"speed": 1.10, "temperature": .62,
                           "enable_text_splitting": False, "top_k": 30},
            })
            passed = self.engine.model.requests[0]
            self.assertEqual(passed["speed"], 1.1)
            self.assertEqual(passed["temperature"], .62)
            self.assertEqual(passed["top_k"], 30)
            self.assertFalse(passed["enable_text_splitting"])
            self.assertEqual(result["device"], "cuda")
            self.assertEqual(result["warning"], "")
            self.assertGreaterEqual(result["generation_seconds"], 0)
            self.assertEqual(self.engine.torch.cuda.sync_calls, 1)

    def test_auto_cpu_fallback_is_explicit_in_synthesis_report(self):
        self.engine.model_dir = "fake"
        self.engine.model = FakeModel()
        self.engine.device = "cpu"
        self.engine._conditioning = lambda _: ("latent", "embedding")
        self.engine._save_wav = lambda *a: 1
        self.engine.load = lambda *a, **kw: {
            "cached": False, "cuda_available": False, "cpu_fallback": True,
        }
        with tempfile.TemporaryDirectory() as tmp:
            result = self.engine.synthesize({
                "text": "hello", "reference": "fake.wav",
                "output_path": str(Path(tmp) / "fake.wav"),
            })
        self.assertTrue(result["cpu_fallback"])
        self.assertIn("running on CPU", result["warning"])
        self.assertEqual(self.engine.torch.cuda.sync_calls, 0)


class XTTSWorkerInterpreterTests(unittest.TestCase):
    def test_windows_requires_correct_apollo_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = object.__new__(Module)
            module.base = Path(tmp)
            with patch("modules.voice_imprint_trainer.module.sys.platform", "win32"):
                with self.assertRaisesRegex(RuntimeError, "private"):
                    module._xtts_python_executable()
                target = Path(tmp) / ".venv" / "Scripts" / "python.exe"
                target.parent.mkdir(parents=True)
                target.write_bytes(b"test fixture")
                self.assertEqual(Path(module._xtts_python_executable()), target.resolve())

    def test_worker_diagnostics_dont_require_running_audio(self):
        import inspect
        code = inspect.getsource(Module._start_xtts_worker)
        self.assertIn("self._xtts_python_executable()", code)
        self.assertIn('env.pop("PYTHONHOME", None)', code)
        self.assertIn('env.pop("PYTHONPATH", None)', code)


if __name__ == "__main__":
    unittest.main()
