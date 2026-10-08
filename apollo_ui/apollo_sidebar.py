"""Persistent, safe sidebar layout independent from the Qt application.

Home (Hub internally) and Settings remain permanently visible. Module buttons
are identified by stable module::id identifiers, not by display names.
"""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

CORE_ITEMS = ("Chat", "Medical", "Train", "Web", "Coding", "Modules", "System", "Memory")
FIXED_ITEMS = ("Hub", "Settings")
DEFAULT_WIDTH = 220
_MODULE_KEY = re.compile(r"^module::[a-zA-Z0-9_-]{1,80}$")


def _valid_key(key):
    return key in CORE_ITEMS or bool(_MODULE_KEY.fullmatch(str(key)))


def _unique_keys(values):
    seen = set()
    result = []
    if not isinstance(values, (list, tuple)):
        return result
    for value in values:
        if not isinstance(value, str) or not _valid_key(value) or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


class SidebarLayoutStore:
    """Own the sidebar layout without changing module enabled/disabled state."""

    def __init__(self, base_dir):
        self.path = Path(base_dir) / "storage" / "state" / "shell" / "sidebar_layout.json"
        self._state = self._read()

    @staticmethod
    def defaults():
        return {
            "version": 1,
            "order": list(CORE_ITEMS),
            "hidden": [],
            "labels": {},
            "width": DEFAULT_WIDTH,
            "collapsed": False,
        }

    @classmethod
    def _normalise(cls, raw):
        if not isinstance(raw, dict):
            raise ValueError("Sidebar layout must be an object")
        state = cls.defaults()
        existing = _unique_keys(raw.get("order"))
        state["order"] = existing + [key for key in CORE_ITEMS if key not in existing]
        state["hidden"] = _unique_keys(raw.get("hidden"))
        labels = raw.get("labels", {})
        if isinstance(labels, dict):
            for key, value in labels.items():
                if _valid_key(key) and isinstance(value, str):
                    cleaned = " ".join(value.strip().split())[:36]
                    if cleaned:
                        state["labels"][key] = cleaned
        try:
            state["width"] = max(180, min(360, int(raw.get("width", DEFAULT_WIDTH))))
        except (ValueError, TypeError, OverflowError):
            pass
        state["collapsed"] = bool(raw.get("collapsed", False))
        return state

    def _read(self):
        if not self.path.exists():
            return self.defaults()
        try:
            return self._normalise(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
            try:
                self.path.replace(self.path.with_name(f"sidebar_layout.corrupt-{stamp}.json"))
            except OSError:
                pass
            return self.defaults()

    def _commit(self, state):
        clean = self._normalise(state)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(self.path.name + ".tmp")
        try:
            temp.write_text(json.dumps(clean, indent=2) + "\n", encoding="utf-8")
            os.replace(temp, self.path)
        finally:
            if temp.exists():
                temp.unlink()
        self._state = clean

    def state(self):
        return json.loads(json.dumps(self._state))

    def ordered(self, available):
        """Append newly installed modules while retaining preferences for absent ones."""
        current = _unique_keys(list(available))
        return [key for key in self._state["order"] if key in current] + [
            key for key in current if key not in self._state["order"]
        ]

    def is_visible(self, key):
        return key in FIXED_ITEMS or key not in self._state["hidden"]

    def display_label(self, key, default):
        if key == "Hub":
            return "Home"
        if key in FIXED_ITEMS:
            return str(default)
        return self._state["labels"].get(key, str(default))

    def apply(self, order, hidden, labels=None, width=None, collapsed=None):
        """Persist one editor transaction and retain absent module preferences."""
        ordered = _unique_keys(order)
        old_order = self._state["order"]
        final_order = ordered + [key for key in old_order if key not in ordered]
        next_state = self.state()
        next_state["order"] = final_order
        absent = set(old_order) - set(ordered)
        next_state["hidden"] = _unique_keys(hidden) + [
            key for key in next_state["hidden"] if key in absent and key not in hidden
        ]
        if isinstance(labels, dict):
            merged = dict(next_state["labels"])
            for key, value in labels.items():
                if _valid_key(key):
                    if str(value).strip():
                        merged[key] = str(value)
                    else:
                        merged.pop(key, None)
            next_state["labels"] = merged
        if width is not None:
            next_state["width"] = width
        if collapsed is not None:
            next_state["collapsed"] = collapsed
        self._commit(next_state)

    def reset(self):
        self._commit(self.defaults())
