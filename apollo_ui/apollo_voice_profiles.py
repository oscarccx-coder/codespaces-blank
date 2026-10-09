"""Safe local Voice Imprint profile administration.

Profile deletion archives the whole folder inside local private storage. It
never erases source WAVs, model weights or audio outside the selected profile.
This service is intentionally UI-only, not an Apollo/LLM capability.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import uuid


ID = re.compile(r"^[a-z0-9_-]{1,64}$")


class VoiceProfileLibrary:
    def __init__(self, voice_storage):
        self.root = Path(voice_storage).resolve()
        self.profiles = self.root / "profiles"
        self.archives = self.root / "deleted_profiles"
        self.order_file = self.root / "profile_order.json"

    def _folder(self, profile_id):
        if not isinstance(profile_id, str) or not ID.fullmatch(profile_id):
            raise ValueError("Invalid voice profile ID")
        candidate = self.profiles / profile_id
        if candidate.is_symlink() or candidate.resolve().parent != self.profiles.resolve():
            raise ValueError("Unsafe voice profile directory")
        if not candidate.is_dir() or not (candidate / "profile.json").is_file():
            raise KeyError(f"Voice profile {profile_id!r} does not exist")
        return candidate

    def ids(self):
        if not self.profiles.exists():
            return []
        ids = []
        for folder in self.profiles.iterdir():
            if ID.fullmatch(folder.name) and not folder.is_symlink() and folder.is_dir():
                if (folder / "profile.json").is_file() and not (folder / "profile.json").is_symlink():
                    ids.append(folder.name)
        return sorted(ids)

    def _read_order(self):
        try:
            raw = json.loads(self.order_file.read_text(encoding="utf-8"))
            return raw if isinstance(raw, list) else []
        except (ValueError, OSError):
            return []

    def ordered_ids(self):
        actual = self.ids()
        saved = self._read_order()
        return [i for i in saved if i in actual] + [i for i in actual if i not in saved]

    def reorder(self, values):
        available = self.ordered_ids()
        if not isinstance(values, list) or len(values) != len(available):
            raise ValueError("Provide every existing profile ID exactly once")
        if len(set(values)) != len(values) or set(values) != set(available):
            raise ValueError("Profile order must contain each ID once")
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.order_file.with_suffix(".json.tmp")
        try:
            temporary.write_text(json.dumps(values, indent=2) + "\n", encoding="utf-8")
            os.replace(temporary, self.order_file)
        finally:
            temporary.unlink(missing_ok=True)
        return list(values)

    def rename(self, profile_id, name):
        folder = self._folder(profile_id)
        raw = str(name or "")
        if any(ord(c) < 32 for c in raw):
            raise ValueError("Voice name cannot contain control characters")
        name = " ".join(raw.split()).strip()
        if not (1 <= len(name) <= 80):
            raise ValueError("Voice name must have 1-80 printable characters")
        profile_path = folder / "profile.json"
        original = json.loads(profile_path.read_text(encoding="utf-8"))
        if not isinstance(original, dict):
            raise ValueError("Voice profile metadata is damaged")
        data = dict(original)
        data["name"] = name
        data["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        temp = profile_path.with_name("profile.json.tmp")
        try:
            temp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            os.replace(temp, profile_path)
        finally:
            temp.unlink(missing_ok=True)
        return {"profile_id": profile_id, "name": name}

    def archive(self, profile_id):
        """Move to private local archive; do not permanently erase any audio."""
        folder = self._folder(profile_id)
        self.archives.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        destination = self.archives / f"{profile_id}-{stamp}-{uuid.uuid4().hex[:8]}"
        folder.rename(destination)
        return {"profile_id": profile_id, "archived": True, "archive": str(destination)}
