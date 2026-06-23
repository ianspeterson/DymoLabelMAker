"""
link_store.py — persistent universe -> link-string mapping.

The link value on each label (e.g. "11111111A", "DMX Hardline") is not in the
MA patch. It's a lookup keyed on the fixture's universe, maintained by you once
during setup and reused on every print.

Stored as a simple JSON file on the laptop so it survives restarts. No database.

Keys are stored as strings (JSON object keys are strings anyway) but the public
API accepts ints or strings for convenience and normalizes internally.
"""

import json
import os
import threading

_LOCK = threading.Lock()


class LinkStore:
    def __init__(self, path: str):
        self.path = path
        self._map: dict[str, str] = {}
        self._load()

    # ---- persistence ------------------------------------------------
    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # normalize keys to strings, values to strings
                self._map = {str(k): str(v) for k, v in data.items()}
            except (json.JSONDecodeError, OSError):
                # Corrupt or unreadable — start empty rather than crash.
                self._map = {}
        else:
            self._map = {}

    def _save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        # Write atomically: temp file then replace, so a crash mid-write
        # never leaves a half-written mapping.
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._map, f, indent=2, sort_keys=True)
        os.replace(tmp, self.path)

    # ---- public API -------------------------------------------------
    def get(self, universe) -> str | None:
        """Return the link string for a universe, or None if unmapped."""
        return self._map.get(str(universe))

    def set(self, universe, link: str):
        """Add or update a mapping. Empty link removes the mapping."""
        with _LOCK:
            key = str(universe)
            if link is None or str(link).strip() == "":
                self._map.pop(key, None)
            else:
                self._map[key] = str(link).strip()
            self._save()

    def delete(self, universe):
        with _LOCK:
            self._map.pop(str(universe), None)
            self._save()

    def clear(self):
        """Remove every universe->link mapping and persist an empty map."""
        with _LOCK:
            self._map.clear()
            self._save()

    def all(self) -> dict[str, str]:
        """Return a copy of the full mapping, sorted by numeric universe."""
        def sort_key(item):
            k = item[0]
            return (0, int(k)) if k.isdigit() else (1, k)
        return dict(sorted(self._map.items(), key=sort_key))

    def resolve_many(self, universes) -> dict[int, str | None]:
        """
        Given a list of universes, return {universe: link-or-None}.
        Useful for the print flow: detect which universes are unmapped.
        """
        return {u: self.get(u) for u in universes}

    def unmapped(self, universes) -> list:
        """Return the subset of universes with no link mapping."""
        seen = []
        for u in universes:
            if self.get(u) is None and u not in seen:
                seen.append(u)
        return seen


# Quick self-test
if __name__ == "__main__":
    import tempfile

    d = tempfile.mkdtemp()
    p = os.path.join(d, "link_map.json")
    store = LinkStore(p)

    store.set(1, "11111111A")
    store.set(2, "11111111B")
    store.set(21, "72872821")
    store.set(30, "DMX Hardline")
    print("  all:", store.all())

    print("  get(1):", store.get(1))
    print("  get(2):", store.get("2"))     # string key works too
    print("  get(99):", store.get(99))     # unmapped -> None

    print("  resolve_many([1,2,99]):", store.resolve_many([1, 2, 99]))
    print("  unmapped([1,2,99,100]):", store.unmapped([1, 2, 99, 100]))

    # persistence check: new instance reads same file
    store2 = LinkStore(p)
    print("  reload get(30):", store2.get(30))

    # delete / clear via empty
    store2.set(1, "")   # empty removes
    print("  after empty-set get(1):", store2.get(1))
    store2.delete(2)
    print("  after delete get(2):", store2.get(2))
    print("  final all:", store2.all())
