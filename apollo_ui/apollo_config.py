"""Apollo settings overrides, stored outside Git-tracked application code.

config.json remains the versioned baseline for packaging/update metadata.
User-facing model and personality preferences go to storage/state/user_config.json
with an atomic write; future git pulls do not see these as source modifications.
"""
import json
import os
from pathlib import Path

USER_KEYS = (
    "ollama_url", "model", "temperature", "num_ctx",
    "auto_model_routing", "sarcasm_level", "memory_profile",
    "num_batch", "keep_alive",
)


class ApolloConfigStore:
    def __init__(self, base_dir):
        self.base_dir = Path(base_dir).resolve()
        self.defaults_path = self.base_dir / "config.json"
        self.user_path = self.base_dir / "storage" / "state" / "user_config.json"

    def load(self):
        data = json.loads(self.defaults_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Apollo config.json must contain an object")
        try:
            overrides = json.loads(self.user_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            overrides = {}
        if isinstance(overrides, dict):
            # Never allow local overrides to replace app/release versions,
            # storage paths or unexpected settings keys.
            for key in USER_KEYS:
                if key in overrides:
                    data[key] = overrides[key]
        return data

    def save_user(self, settings):
        if not isinstance(settings, dict):
            raise ValueError("Settings must be an object")
        self.user_path.parent.mkdir(parents=True, exist_ok=True)
        data = {key: settings[key] for key in USER_KEYS if key in settings}
        target = self.user_path
        temp = target.with_name(target.name + ".tmp")
        try:
            temp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            os.replace(temp, target)
        finally:
            if temp.exists():
                temp.unlink()
        return str(target)
