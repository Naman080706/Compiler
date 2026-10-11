"""On-disk explanation cache (plan 010; PRD: "cache explanations by error signature to save quota").

One JSON file, by default ``<repo root>/.cea_cache/explanations.json``
(git-ignored). The key is the sha256 of the error signature plus the mode, so
the file holds no source text in its keys. Values are small JSON objects chosen
by the caller (plan 011's agent). A missing or corrupt file counts as empty;
the cache never raises on read.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CACHE_PATH = REPO_ROOT / ".cea_cache" / "explanations.json"


class ExplanationCache:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path is not None else DEFAULT_CACHE_PATH
        self._data: dict[str, dict] | None = None

    @staticmethod
    def key(signature: object, mode: str) -> str:
        """sha256 hex of the canonical JSON of (signature, mode)."""
        text = json.dumps({"signature": signature, "mode": mode}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _load(self) -> dict[str, dict]:
        if self._data is None:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self._data = data if isinstance(data, dict) else {}
            except (OSError, ValueError):
                self._data = {}
        return self._data

    def get(self, signature: object, mode: str) -> dict | None:
        value = self._load().get(self.key(signature, mode))
        return dict(value) if isinstance(value, dict) else None

    def put(self, signature: object, mode: str, value: dict) -> None:
        data = self._load()
        data[self.key(signature, mode)] = dict(value)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    def __len__(self) -> int:
        return len(self._load())
