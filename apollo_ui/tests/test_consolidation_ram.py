"""Qt-free tests for app consolidation, lazy UI and Ollama context profiles."""
import ast
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from apollo_module_catalog import GROUPS, group_for, is_visible, main_app_for
from apollo_model_memory import PROFILES, resolved_options, memory_advice, normalize_profile
from apollo_config import ApolloConfigStore
from ollama_client import OllamaClient


ROOT = Path(__file__).resolve().parents[1]


class ConsolidationTests(unittest.TestCase):
    def test_related_modules_preserve_hidden_backend_and_share_primary(self):
        self.assertEqual(main_app_for("voice_imprint_trainer"), "voice_center")
        self.assertEqual(main_app_for("text_to_speech"), "voice_center")
        self.assertEqual(main_app_for("memory_intelligence"), "memory_bank")
        self.assertEqual(main_app_for("activity_trace"), "core_services")
        self.assertEqual(group_for("voice_center"), "Everyday")
        self.assertFalse(is_visible("neural_visualizer", "Everyday"))
        self.assertTrue(is_visible("neural_visualizer", "Advanced"))
        self.assertTrue(is_visible("neural_visualizer", "All"))
        self.assertIn("Coding", GROUPS)

    def test_lazy_ui_no_eager_page_for_apps(self):
        text = (ROOT / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(text)
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ApolloWindow")
        methods = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}
        rebuild = ast.get_source_segment(text, methods["rebuild_module_ui"])
        opener = ast.get_source_segment(text, methods["open_module_app"])
        self.assertIn('if placement == "apps":', rebuild)
        self.assertIn("continue", rebuild)
        self.assertNotIn("self.apps_host.addWidget(page)", rebuild)
        self.assertIn("self._build_module_page_widget(module_info)", opener)
        self.assertNotIn("self.rebuild_module_ui()", opener)
        self.assertIn("def _filter_module_apps", text)
        self.assertIn("module_id = main_app_for(str(module_id or \"\").strip())", opener)

    def test_existing_backend_modules_are_not_deleted(self):
        for mid in ("voice_center", "voice_imprint_trainer", "text_to_speech", "core_services",
                    "gpu_monitor", "notification_center", "activity_trace",
                    "memory_bank", "memory_intelligence", "knowledge_graph"):
            self.assertTrue((ROOT / "modules" / mid / "manifest.json").exists())

    def test_primary_apps_reuse_secondary_panels(self):
        core = (ROOT / "modules" / "core_services" / "module.py").read_text(encoding="utf-8")
        memory = (ROOT / "modules" / "memory_bank" / "module.py").read_text(encoding="utf-8")
        for name in ("gpu_monitor", "activity_trace", "notification_center"):
            self.assertIn(f'("{name}",', core)
        for name in ("memory_intelligence", "knowledge_graph"):
            self.assertIn(f"related_instance('{name}')", memory)
        development = (ROOT / "modules" / "self_improvement_lab" / "module.py").read_text(encoding="utf-8")
        for name in ("verification_engine", "benchmark_suite", "upgrade_history"):
            self.assertIn(f"('{name}',", development)


class OllamaRAMTests(unittest.TestCase):
    def test_profiles_have_bounded_values(self):
        self.assertEqual(PROFILES["expanded"].num_ctx, 16384)
        for preset in PROFILES.values():
            self.assertGreaterEqual(preset.num_ctx, 8192)
            self.assertLessEqual(preset.num_ctx, 32768)
            self.assertGreaterEqual(preset.num_batch, 16)

    def test_bad_options_are_safely_clamped(self):
        self.assertEqual(resolved_options({"num_ctx": 1000000, "num_batch": 9999, "keep_alive": "-1"}),
                         {"num_ctx": 32768, "num_batch": 512, "keep_alive": "5m"})
        self.assertEqual(resolved_options({"num_ctx": 0, "num_batch": 0})["num_ctx"], 1024)
        self.assertEqual(normalize_profile("not-a-profile"), "balanced")
        self.assertIn("Low free RAM", memory_advice(2, 32, "large"))

    def test_context_batch_and_residency_sent_to_ollama(self):
        client = OllamaClient("http://127.0.0.1:11434", "test-model",
                              num_ctx=16384, num_batch=128, keep_alive="10m")
        with patch.object(client, "best_model", return_value="test-model"):
            payload = client._chat_payload([{"role": "user", "content": "hello"}], False)
        self.assertEqual(payload["keep_alive"], "10m")
        self.assertEqual(payload["options"]["num_ctx"], 16384)
        self.assertEqual(payload["options"]["num_batch"], 128)
        self.assertNotIn("num_gpu", payload["options"])

    def test_ollama_loaded_model_ram_estimate_never_negative(self):
        client = OllamaClient("http://127.0.0.1:11434", "m")
        with patch.object(client, "_request_json", return_value={"models": [
            {"name": "a", "size": 9000, "size_vram": 6000},
            {"name": "b", "size": 6000, "size_vram": 9000},
        ]}):
            models = client.loaded_models()
        self.assertEqual(models[0]["ram_estimate_bytes"], 3000)
        self.assertEqual(models[1]["ram_estimate_bytes"], 0)

    def test_user_memory_profile_settings_survive_reload(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "config.json").write_text(json.dumps({
                "version": "7.5.13.1", "model": "qwen", "num_ctx": 8192,
            }), encoding="utf-8")
            store = ApolloConfigStore(root)
            settings = store.load()
            settings.update(memory_profile="expanded", num_ctx=16384,
                            num_batch=128, keep_alive="10m")
            store.save_user(settings)
            restored = store.load()
            self.assertEqual(restored["num_ctx"], 16384)
            self.assertEqual(restored["num_batch"], 128)
            self.assertEqual(restored["keep_alive"], "10m")
            self.assertEqual(restored["version"], "7.5.13.1")


if __name__ == "__main__":
    unittest.main()
