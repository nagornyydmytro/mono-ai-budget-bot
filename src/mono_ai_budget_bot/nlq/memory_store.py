from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BASE_DIR = Path(".cache") / "memory"
DEFAULT_MERCHANT_ALIASES = {
    "мак": "mcdonalds",
    "макдак": "mcdonalds",
    "макдональдс": "mcdonalds",
    "макд": "mcdonalds",
    "mcd": "mcdonalds",
    "mc": "mcdonalds",
}


def _default_memory() -> dict[str, Any]:
    return {
        "merchant_aliases": dict(DEFAULT_MERCHANT_ALIASES),
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

    raw = merchant_contains.strip().lower()
    if not raw:
        return None

    mem = load_memory(telegram_user_id)
    aliases = mem.get("merchant_aliases") or {}
    if not isinstance(aliases, dict):
        return raw

    if raw in aliases and isinstance(aliases[raw], str) and aliases[raw].strip():
        return aliases[raw].strip().lower()

    for k, v in aliases.items():
        if not isinstance(k, str) or not isinstance(v, str):
            continue
        kk = k.strip().lower()
        vv = v.strip().lower()
        if not kk or not vv:
            continue
        if raw == kk or raw in kk or kk in raw:
            aliases[raw] = vv
            mem["merchant_aliases"] = aliases
            save_memory(telegram_user_id, mem)
            return vv

    return raw


def set_pending_intent(telegram_user_id: int, payload: dict[str, Any]) -> None:
    mem = load_memory(telegram_user_id)
    mem["pending_intent"] = payload
    save_memory(telegram_user_id, mem)


def pop_pending_intent(telegram_user_id: int) -> dict[str, Any] | None:
    mem = load_memory(telegram_user_id)
    p = mem.get("pending_intent")
    mem["pending_intent"] = None
    save_memory(telegram_user_id, mem)
    return p if isinstance(p, dict) else None


def save_recipient_alias(telegram_user_id: int, alias: str, match_value: str) -> None:
    mem = load_memory(telegram_user_id)
    ra = mem.get("recipient_aliases") or {}
    if not isinstance(ra, dict):
        ra = {}
    ra[alias.strip().lower()] = match_value.strip().lower()
    mem["recipient_aliases"] = ra
    save_memory(telegram_user_id, mem)
