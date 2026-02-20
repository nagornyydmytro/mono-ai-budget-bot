from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class UserConfig:
    telegram_user_id: int
    mono_token: str
    selected_account_ids: list[str]
    updated_at: float  # unix timestamp


class UserStore:
    """
    Local disk store for per-user config (mono token, selected accounts).
    Stored under .cache/users/<telegram_user_id>.json
    """

    def __init__(self, root_dir: Path | None = None):
        self.root_dir = root_dir or (Path(".cache") / "users")
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, telegram_user_id: int) -> Path:
        return self.root_dir / f"{telegram_user_id}.json"

    def save(self, telegram_user_id: int, mono_token: str, selected_account_ids: list[str] | None = None) -> Path:
        payload: dict[str, Any] = {
            "telegram_user_id": telegram_user_id,
            "mono_token": mono_token,
            "selected_account_ids": selected_account_ids or [],
            "updated_at": time.time(),
        }
        path = self._path(telegram_user_id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return path

    def load(self, telegram_user_id: int) -> UserConfig | None:
        path = self._path(telegram_user_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return UserConfig(
                telegram_user_id=int(data["telegram_user_id"]),
                mono_token=str(data["mono_token"]),
                selected_account_ids=list(data.get("selected_account_ids", [])),
                updated_at=float(data.get("updated_at", 0.0)),
            )
        except Exception:
            return None