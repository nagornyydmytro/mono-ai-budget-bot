from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ProfileStore:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, user_id: int) -> Path:
        return self.base_dir / f"{user_id}.json"

    def save(self, user_id: int, profile: dict[str, Any]) -> None:
        self._path(user_id).write_text(
            json.dumps(profile, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load(self, user_id: int) -> dict[str, Any] | None:
        p = self._path(user_id)
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))
