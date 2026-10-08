"""Ensure changing local preferences does not modify Git-tracked config.json."""
import json
import tempfile
import unittest
from pathlib import Path
from apollo_config import ApolloConfigStore


class LocalSettingsTests(unittest.TestCase):
    def test_overrides_are_local_and_preserve_release_version(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            baseline = {"version": "7.5.0", "model": "qwen", "ollama_url": "http://localhost:11434",
                        "database": "apollo_memory.db"}
            config_file = root / "config.json"
            config_file.write_text(json.dumps(baseline))
            store = ApolloConfigStore(root)
            local = store.load()
            local["model"] = "other-model"
            local["sarcasm_level"] = 3
            local["version"] = "9999"
            local["database"] = "should-not-change.db"
            stored = store.save_user(local)
            self.assertTrue(Path(stored).is_file())
            self.assertEqual(json.loads(config_file.read_text()), baseline)
            combined = store.load()
            self.assertEqual(combined["model"], "other-model")
            self.assertEqual(combined["sarcasm_level"], 3)
            self.assertEqual(combined["version"], "7.5.0")
            self.assertEqual(combined["database"], "apollo_memory.db")

    def test_malformed_override_reverts_to_default(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "config.json").write_text('{"model": "baseline"}')
            store = ApolloConfigStore(root)
            store.user_path.parent.mkdir(parents=True)
            store.user_path.write_text("{corrupt")
            self.assertEqual(store.load()["model"], "baseline")


if __name__ == "__main__":
    unittest.main()
