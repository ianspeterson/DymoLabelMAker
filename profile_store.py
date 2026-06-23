"""
profile_store.py — persistent label overrides for fixture profile/mode text.

MA patch data stays the source of truth. This store only applies user overrides
when a fixture's raw MA profile/mode text is blank, ugly, or intentionally
corrected in the review screen.

Overrides are keyed by the matching MA data group:
    fixturetype | raw_profile | raw_description

That means Link stays universe-based, while Profile/Description overrides stay
fixture-profile/mode-based.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any

_LOCK = threading.Lock()


def _norm(value: Any) -> str:
    return str(value or "").strip()


def make_profile_key(fixturetype: Any, raw_profile: Any, raw_description: Any) -> str:
    # Use a delimiter that is extremely unlikely to appear in label text.
    return "\u241f".join((_norm(fixturetype), _norm(raw_profile), _norm(raw_description)))


class ProfileOverrideStore:
    def __init__(self, path: str):
        self.path = path
        self._map: dict[str, dict[str, str]] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                clean: dict[str, dict[str, str]] = {}
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, dict):
                            profile = _norm(v.get("profile"))
                            description = _norm(v.get("description"))
                            if profile or description:
                                clean[str(k)] = {
                                    "profile": profile,
                                    "description": description,
                                }
                self._map = clean
            except (json.JSONDecodeError, OSError):
                self._map = {}
        else:
            self._map = {}

    def _save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._map, f, indent=2, sort_keys=True)
        os.replace(tmp, self.path)

    def get_by_key(self, key: str) -> dict[str, str] | None:
        item = self._map.get(str(key))
        return dict(item) if item else None

    def get(self, fixturetype: Any, raw_profile: Any, raw_description: Any) -> dict[str, str] | None:
        return self.get_by_key(make_profile_key(fixturetype, raw_profile, raw_description))

    def set_by_key(self, key: str, profile: Any, description: Any):
        profile = _norm(profile)
        description = _norm(description)
        with _LOCK:
            if not profile and not description:
                self._map.pop(str(key), None)
            else:
                self._map[str(key)] = {
                    "profile": profile,
                    "description": description,
                }
            self._save()

    def set(self, fixturetype: Any, raw_profile: Any, raw_description: Any,
            profile: Any, description: Any):
        self.set_by_key(make_profile_key(fixturetype, raw_profile, raw_description),
                        profile, description)

    def delete_by_key(self, key: str):
        with _LOCK:
            self._map.pop(str(key), None)
            self._save()

    def all(self) -> dict[str, dict[str, str]]:
        return dict(sorted(self._map.items(), key=lambda item: item[0]))
