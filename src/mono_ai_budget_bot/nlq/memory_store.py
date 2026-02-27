from __future__ import annotations

import json
from pathlib import Path
from typing import Any


BASE_DIR = Path(".cache") / "memory"


def _default_memory() -> dict[str, Any]:
    return {
        "merchant_aliases": {},
        "recipient_aliases": {},
        "pending_intent": None,
    }


def load_memory(telegram_user_id: int) -> dict[str, Any]:
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    path = BASE_DIR / f"{int(telegram_user_id)}.json"
    if not path.exists():
        data = _default_memory()
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return data

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = _default_memory()
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return data

    if not isinstance(data, dict):
        data = _default_memory()

    if "merchant_aliases" not in data or not isinstance(data.get("merchant_aliases"), dict):
        data["merchant_aliases"] = {}
    if "recipient_aliases" not in data or not isinstance(data.get("recipient_aliases"), dict):
        data["recipient_aliases"] = {}
    if "pending_intent" not in data:
        data["pending_intent"] = None

    return data


def save_memory(telegram_user_id: int, data: dict[str, Any]) -> None:
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    path = BASE_DIR / f"{int(telegram_user_id)}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_merchant_alias(telegram_user_id: int, merchant_contains: str | None) -> str | None:
    if not merchant_contains:
        return None
    mem = load_memory(telegram_user_id)
    aliases = mem.get("merchant_aliases") or {}
    if not isinstance(aliases, dict):
        return merchant_contains

    key = merchant_contains.strip().lower()
    v = aliases.get(key)
    if isinstance(v, str) and v.strip():
        return v.strip().lower()
    return key