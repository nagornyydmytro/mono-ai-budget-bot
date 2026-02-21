from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


@dataclass(frozen=True)
class UserConfig:
    telegram_user_id: int
    mono_token: str
    selected_account_ids: list[str]
    chat_id: int | None
    autojobs_enabled: bool
    updated_at: float  # unix timestamp


class UserStore:
    """
    Local disk store for per-user config (mono token, selected accounts, chat_id, autojobs_enabled).
    Stored under .cache/users/<telegram_user_id>.json
    """

    def __init__(self, root_dir: Path | None = None):
        self.root_dir = root_dir or (Path(".cache") / "users")
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, telegram_user_id: int) -> Path:
        return self.root_dir / f"{telegram_user_id}.json"

    def save(
        self,
        telegram_user_id: int,
        mono_token: str | None = None,
        selected_account_ids: list[str] | None = None,
        chat_id: int | None = None,
        autojobs_enabled: bool | None = None,
    ) -> Path:
        """
        Upsert behavior:
        - If file exists, keeps old values unless overridden by passed args.
        - mono_token can be None to keep existing token.
        """
        existing = self.load_raw(telegram_user_id)

        payload: dict[str, Any] = {
            "telegram_user_id": telegram_user_id,
            "mono_token": (mono_token if mono_token is not None else existing.get("mono_token", "")),
            "selected_account_ids": (
                selected_account_ids
                if selected_account_ids is not None
                else list(existing.get("selected_account_ids", []))
            ),
            "chat_id": (chat_id if chat_id is not None else existing.get("chat_id")),
            "autojobs_enabled": (
                bool(autojobs_enabled)
                if autojobs_enabled is not None
                else bool(existing.get("autojobs_enabled", True))
            ),
            "updated_at": time.time(),
        }

        path = self._path(telegram_user_id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return path

    def load_raw(self, telegram_user_id: int) -> dict[str, Any]:
        path = self._path(telegram_user_id)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def load(self, telegram_user_id: int) -> UserConfig | None:
        path = self._path(telegram_user_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return UserConfig(
                telegram_user_id=int(data["telegram_user_id"]),
                mono_token=str(data.get("mono_token", "")),
                selected_account_ids=list(data.get("selected_account_ids", [])),
                chat_id=(int(data["chat_id"]) if data.get("chat_id") is not None else None),
                autojobs_enabled=bool(data.get("autojobs_enabled", True)),
                updated_at=float(data.get("updated_at", 0.0)),
            )
        except Exception:
            return None

    def iter_all(self) -> Iterator[UserConfig]:
        """
        Iterate all users in .cache/users directory.
        """
        for p in self.root_dir.glob("*.json"):
            try:
                telegram_user_id = int(p.stem)
            except Exception:
                continue
            cfg = self.load(telegram_user_id)
            if cfg is not None:
                yield cfg