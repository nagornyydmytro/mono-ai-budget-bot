from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
from mono_ai_budget_bot.security.crypto import encrypt_token, decrypt_token

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
        existing = self.load_raw(telegram_user_id)

        # --- determine plain token ---
        if mono_token is not None:
            token_plain = mono_token
        else:
            token_plain = existing.get("mono_token", "")

        # --- encrypt before storing ---
        token_enc = encrypt_token(token_plain) if token_plain else ""

        payload: dict[str, Any] = {
            "telegram_user_id": telegram_user_id,
            "mono_token": token_enc,
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

            token_stored = str(data.get("mono_token", ""))

            # Migration: if token is plain, encrypt it
            if token_stored and not token_stored.startswith("gAAAAA"):
                token_enc = encrypt_token(token_stored)
                data["mono_token"] = token_enc
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                token_stored = token_enc

            token_plain = decrypt_token(token_stored) if token_stored else ""

            return UserConfig(
                telegram_user_id=int(data["telegram_user_id"]),
                mono_token=token_plain,
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