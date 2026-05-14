"""
ArtifactCache — single-read, in-memory artifact store.

Each artifact file is read from disk exactly once per pipeline execution.
Skills and parsers receive the already-parsed dict directly instead of
independently re-reading and re-parsing the same file.

Token impact: scenarios.json was previously read 5 times per execute();
with the cache it is read once and the reference is reused.
"""
from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


class ArtifactCache:
    """
    In-memory cache of parsed pipeline artifacts for one execution run.

    Keyed by resolved absolute path.  Modification-time tracking ensures
    a file is refreshed if a skill writes a new version during the same run.
    """

    def __init__(self) -> None:
        self._data:   dict[str, Any]   = {}
        self._mtimes: dict[str, float] = {}

    # ── Public read interface ─────────────────────────────────────────────────

    def get_json(self, path: str | Path) -> Any:
        """Return parsed JSON; None if file is missing or unparseable."""
        return self._get(path, self._read_json)

    def get_xml(self, path: str | Path) -> ET.Element | None:
        """Return parsed XML root element; None if file is missing or unparseable."""
        return self._get(path, self._read_xml)

    def get_text(self, path: str | Path) -> str | None:
        """Return raw text content; None if file is missing."""
        return self._get(path, self._read_text)

    # ── Write interface (call after a skill updates a file) ───────────────────

    def put(self, path: str | Path, data: Any) -> None:
        """Store pre-parsed data; avoids next read for this path."""
        key = self._key(path)
        self._data[key]   = data
        self._mtimes[key] = self._mtime(key)

    def invalidate(self, path: str | Path) -> None:
        """Force re-read on next access (e.g. after a skill overwrites the file)."""
        key = self._key(path)
        self._data.pop(key, None)
        self._mtimes.pop(key, None)

    def clear(self) -> None:
        self._data.clear()
        self._mtimes.clear()

    # ── Convenience finders (rglob-once, cached) ─────────────────────────────

    def find_json(self, root: str | Path, filename: str) -> Any:
        """
        Find *filename* under *root* (recursive) and return parsed JSON.
        Returns None if not found.  The resolved path is cached.
        """
        candidates = sorted(Path(root).rglob(filename))
        if not candidates:
            return None
        return self.get_json(candidates[0])

    def find_xml(self, root: str | Path, filename: str) -> ET.Element | None:
        candidates = sorted(Path(root).rglob(filename))
        if not candidates:
            return None
        return self.get_xml(candidates[0])

    # ── Internal ──────────────────────────────────────────────────────────────

    def _get(self, path: str | Path, reader):
        key   = self._key(path)
        mtime = self._mtime(key)

        if key in self._data and self._mtimes.get(key) == mtime:
            return self._data[key]

        val = reader(key)
        if val is not None:
            self._data[key]   = val
            self._mtimes[key] = mtime
        return val

    @staticmethod
    def _key(path: str | Path) -> str:
        return str(Path(path).resolve())

    @staticmethod
    def _mtime(path: str) -> float:
        try:
            return os.path.getmtime(path)
        except OSError:
            return 0.0

    @staticmethod
    def _read_json(path: str) -> Any:
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            return None

    @staticmethod
    def _read_xml(path: str) -> ET.Element | None:
        try:
            return ET.parse(path).getroot()
        except Exception:
            return None

    @staticmethod
    def _read_text(path: str) -> str | None:
        try:
            return Path(path).read_text(encoding="utf-8")
        except Exception:
            return None
