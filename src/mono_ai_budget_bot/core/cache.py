import hashlib
import json
import time
from pathlib import Path
from typing import Any


class JsonDiskCache:
    """
    Very small JSON disk cache with TTL.
    Stores each key as a separate JSON file:
      { "expires_at": float | null, "value": any }
    """

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _key_to_path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.root_dir / f"{digest}.json"

    def get(self, key: str) -> Any | None:
        path = self._key_to_path(key)
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            expires_at = data.get("expires_at", None)
            if expires_at is not None and time.time() >= float(expires_at):
                # expired
                try:
                    path.unlink(missing_ok=True)
                except Exception:
                    pass
                return None
            return data.get("value", None)
        except Exception:
            # corrupted cache entry
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
            return None

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        path = self._key_to_path(key)
        expires_at = None if ttl_seconds is None else (time.time() + ttl_seconds)
        payload = {"expires_at": expires_at, "value": value}
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def delete(self, key: str) -> None:
        path = self._key_to_path(key)
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
