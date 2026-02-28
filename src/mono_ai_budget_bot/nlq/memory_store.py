from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mono_ai_budget_bot.nlq.text_norm import norm

BASE_DIR = Path(".cache") / "memory"

DEFAULT_MERCHANT_ALIASES = {
    "мак": "mcdonalds",
    "макдак": "mcdonalds",
    "макдональдс": "mcdonalds",
    "макд": "mcdonalds",
    "mcd": "mcdonalds",
    "mc": "mcdonalds",
    "сільпо": "silpo",
    "силпо": "silpo",
    "атб": "atb",
    "atb": "atb",
    "novus": "novus",
    "глово": "glovo",
    "glovo": "glovo",
    "bolt": "bolt",
    "uber": "uber",
    "uklon": "uklon",
    "уклон": "uklon",
    "wolt": "wolt",
    "rozetka": "rozetka",
    "розетка": "rozetka",
    "аптека": "apteka",
    "apteka": "apteka",
    "eva": "eva",
    "watsons": "watsons",
}


def _default_memory() -> dict[str, Any]:
    return {
        "merchant_aliases": dict(DEFAULT_MERCHANT_ALIASES),
        "recipient_aliases": {},
        "pending_intent": None,
        "pending_kind": None,
        "pending_options": None,
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
        data["merchant_aliases"] = dict(DEFAULT_MERCHANT_ALIASES)

    if "recipient_aliases" not in data or not isinstance(data.get("recipient_aliases"), dict):
        data["recipient_aliases"] = {}

    if "pending_intent" not in data:
        data["pending_intent"] = None
    if "pending_kind" not in data:
        data["pending_kind"] = None
    if "pending_options" not in data:
        data["pending_options"] = None

    return data


def save_memory(telegram_user_id: int, data: dict[str, Any]) -> None:
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    path = BASE_DIR / f"{int(telegram_user_id)}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_merchant_alias(telegram_user_id: int, merchant_contains: str | None) -> str | None:
    if not merchant_contains:
        return None

    raw = norm(merchant_contains)
    if not raw:
        return None

    mem = load_memory(telegram_user_id)
    aliases = mem.get("merchant_aliases") or {}
    if not isinstance(aliases, dict):
        return raw

    direct = aliases.get(raw)
    if isinstance(direct, str):
        direct_norm = norm(direct)
        if direct_norm:
            return direct_norm

    if len(raw) <= 3:
        return raw

    best_v: str | None = None
    best_k_len = 0

    for k, v in aliases.items():
        if not isinstance(k, str) or not isinstance(v, str):
            continue
        kk = norm(k)
        vv = norm(v)
        if not kk or not vv:
            continue

        if raw == kk or raw in kk or kk in raw:
            if len(kk) > best_k_len:
                best_k_len = len(kk)
                best_v = vv

    if best_v:
        aliases[raw] = best_v
        mem["merchant_aliases"] = aliases
        save_memory(telegram_user_id, mem)
        return best_v

    return raw


def set_pending_intent(
    telegram_user_id: int,
    payload: dict[str, Any],
    kind: str | None = None,
    options: list[str] | None = None,
) -> None:
    mem = load_memory(telegram_user_id)
    mem["pending_intent"] = payload
    mem["pending_kind"] = kind
    mem["pending_options"] = options
    save_memory(telegram_user_id, mem)


def pop_pending_intent(telegram_user_id: int) -> dict[str, Any] | None:
    mem = load_memory(telegram_user_id)
    p = mem.get("pending_intent")
    mem["pending_intent"] = None
    mem["pending_kind"] = None
    mem["pending_options"] = None
    save_memory(telegram_user_id, mem)
    return p if isinstance(p, dict) else None


def get_pending_options(telegram_user_id: int) -> list[str] | None:
    mem = load_memory(telegram_user_id)
    opts = mem.get("pending_options")
    if not isinstance(opts, list):
        return None
    out: list[str] = []
    for x in opts:
        if isinstance(x, str) and x.strip():
            out.append(x.strip())
    return out or None


def save_recipient_alias(telegram_user_id: int, alias: str, match_value: str) -> None:
    a = (alias or "").strip().lower()
    v = (match_value or "").strip().lower()
    if not a or not v:
        return

    mem = load_memory(telegram_user_id)
    ra = mem.get("recipient_aliases") or {}
    if not isinstance(ra, dict):
        ra = {}

    ra[a] = v
    mem["recipient_aliases"] = ra
    save_memory(telegram_user_id, mem)
