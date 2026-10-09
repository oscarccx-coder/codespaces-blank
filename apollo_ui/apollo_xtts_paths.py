"""Single-source XTTS v2 model location shared across Apollo modules.

Model weights remain local, outside update packages and Git history. A valid
XTTS directory contains config.json, model.pth and vocab.json.
"""
import json
import os
from pathlib import Path

XTTS_FILES = ("config.json", "model.pth", "vocab.json")
POINTER_NAME = "xtts_model_path.json"


def shared_xtts_folder(base_dir):
    """Persistent shared model cache (default), not inside replaceable code."""
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "Apollo" / "models" / "voice" / "xtts_v2"
    return Path(base_dir).resolve() / "storage" / "models" / "voice" / "xtts_v2"


def bundled_xtts_folder(base_dir):
    """User-visible drop-in folder; excluded from Git releases/updates."""
    return Path(base_dir).resolve() / "models" / "voice" / "xtts_v2"


def pointer_path(base_dir):
    return Path(base_dir).resolve() / "storage" / "state" / POINTER_NAME


def valid_xtts_folder(path):
    try:
        root = Path(path).expanduser().resolve()
        return root.is_dir() and all((root / filename).is_file() for filename in XTTS_FILES)
    except (OSError, TypeError, ValueError):
        return False


def chosen_xtts_folder(base_dir, legacy=None):
    """Prefer saved explicit choice; otherwise valid drop-in / legacy / shared."""
    pointer = pointer_path(base_dir)
    try:
        data = json.loads(pointer.read_text(encoding="utf-8"))
        selected = data.get("model_dir") if isinstance(data, dict) else None
        # An old saved path must not mask a complete model in a new local
        # folder after drive migrations or Apollo reinstalls.
        if selected and valid_xtts_folder(selected):
            return Path(selected).expanduser().resolve()
    except (OSError, TypeError, ValueError):
        pass

    drop_in = bundled_xtts_folder(base_dir)
    if valid_xtts_folder(drop_in):
        return drop_in
    if legacy and valid_xtts_folder(legacy):
        return Path(legacy).expanduser().resolve()
    return shared_xtts_folder(base_dir)


def save_xtts_folder(base_dir, directory):
    """Save a user-selected location, without copying GBs of model weights."""
    selected = Path(directory).expanduser().resolve()
    if not valid_xtts_folder(selected):
        missing = ", ".join(XTTS_FILES)
        raise ValueError(f"XTTS model folder must contain: {missing}")
    pointer = pointer_path(base_dir)
    pointer.parent.mkdir(parents=True, exist_ok=True)
    tmp = pointer.with_name(pointer.name + ".tmp")
    try:
        tmp.write_text(json.dumps({"model_dir": str(selected)}, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, pointer)
    finally:
        if tmp.exists():
            tmp.unlink()
    return str(selected)
