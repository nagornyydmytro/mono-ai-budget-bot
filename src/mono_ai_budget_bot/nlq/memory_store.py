from __future__ import annotations

import json
import secrets
import time
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

DEFAULT_CATEGORY_ALIASES: dict[str, list[str]] = {}


def _default_memory() -> dict[str, Any]:
    return {
        "merchant_aliases": dict(DEFAULT_MERCHANT_ALIASES),
        "category_aliases": dict(DEFAULT_CATEGORY_ALIASES),
        "recipient_aliases": {},
        "alias_stats": {"merchant": {}, "category": {}, "recipient": {}},
        "pending_intent": None,
        "pending_kind": None,
        "pending_options": None,
        "pending_id": None,
        "pending_created_ts": None,
        "pending_ttl_sec": None,
        "pending_snapshot": None,
        "pending_manual_mode": None,
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
    if "category_aliases" not in data or not isinstance(data.get("category_aliases"), dict):
        data["category_aliases"] = dict(DEFAULT_CATEGORY_ALIASES)
    if "recipient_aliases" not in data or not isinstance(data.get("recipient_aliases"), dict):
        data["recipient_aliases"] = {}
    if "alias_stats" not in data or not isinstance(data.get("alias_stats"), dict):
        data["alias_stats"] = {"merchant": {}, "category": {}, "recipient": {}}
    if "pending_intent" not in data:
        data["pending_intent"] = None
    if "pending_kind" not in data:
        data["pending_kind"] = None
    if "pending_options" not in data:
        data["pending_options"] = None
    for k in [
        "pending_id",
        "pending_created_ts",
        "pending_ttl_sec",
        "pending_snapshot",
        "pending_manual_mode",
    ]:
        if k not in data:
            data[k] = None

    return data


def save_memory(telegram_user_id: int, data: dict[str, Any]) -> None:
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    path = BASE_DIR / f"{int(telegram_user_id)}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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
    mem["pending_id"] = secrets.token_hex(8)
    mem["pending_created_ts"] = int(time.time())
    mem["pending_ttl_sec"] = 600
    mem["pending_snapshot"] = {"options": options, "kind": kind}
    mem["pending_manual_mode"] = None
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


def get_pending_id(telegram_user_id: int) -> str | None:
    mem = load_memory(telegram_user_id)
    pid = mem.get("pending_id")
    return pid if isinstance(pid, str) and pid.strip() else None


def validate_and_consume_pending(
    telegram_user_id: int,
    *,
    pending_id: str,
    now_ts: int,
) -> bool:
    pid = (pending_id or "").strip()
    if not pid:
        return False

    mem = load_memory(telegram_user_id)
    if not pending_is_alive(mem, now_ts=int(now_ts)):
        return False
    if mem.get("pending_id") != pid:
        return False

    mem["pending_id"] = secrets.token_hex(8)
    mem["pending_created_ts"] = int(now_ts)
    save_memory(telegram_user_id, mem)
    return True


def set_pending_manual_mode(
    telegram_user_id: int,
    *,
    expected: str,
    hint: str | None = None,
    source: str | None = None,
    ttl_sec: int = 600,
) -> str:
    mem = load_memory(telegram_user_id)
    pid = secrets.token_hex(8)

    mem["pending_manual_mode"] = {
        "expected": (expected or "").strip(),
        "hint": (hint or "").strip() if isinstance(hint, str) else None,
        "source": (source or "").strip() if isinstance(source, str) else None,
    }
    mem["pending_id"] = pid
    mem["pending_created_ts"] = int(time.time())
    mem["pending_ttl_sec"] = int(ttl_sec)
    save_memory(telegram_user_id, mem)
    return pid


def get_pending_manual_mode(
    telegram_user_id: int,
    *,
    now_ts: int,
) -> dict[str, Any] | None:
    mem = load_memory(telegram_user_id)
    mode = mem.get("pending_manual_mode")
    if not isinstance(mode, dict):
        return None
    if not pending_is_alive(mem, now_ts=int(now_ts)):
        return None
    return mode


def pop_pending_manual_mode(telegram_user_id: int) -> dict[str, Any] | None:
    mem = load_memory(telegram_user_id)
    mode = mem.get("pending_manual_mode")
    mem["pending_manual_mode"] = None
    save_memory(telegram_user_id, mem)
    return mode if isinstance(mode, dict) else None


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


def _touch_alias(mem: dict[str, Any], bucket: str, alias: str) -> None:
    a = (alias or "").strip().lower()
    if not a:
        return

    st = mem.get("alias_stats")
    if not isinstance(st, dict):
        st = {"merchant": {}, "category": {}, "recipient": {}}
        mem["alias_stats"] = st

    b = st.get(bucket)
    if not isinstance(b, dict):
        b = {}
        st[bucket] = b

    x = b.get(a)
    if not isinstance(x, dict):
        x = {"hits": 0, "last_used_ts": 0}
        b[a] = x

    x["hits"] = int(x.get("hits") or 0) + 1
    x["last_used_ts"] = int(time.time())


def _prune_aliases(mem: dict[str, Any]) -> None:
    merchant_aliases = mem.get("merchant_aliases")
    if not isinstance(merchant_aliases, dict):
        return

    category_aliases = mem.get("category_aliases")
    if not isinstance(category_aliases, dict):
        category_aliases = {}
        mem["category_aliases"] = category_aliases

    st = mem.get("alias_stats")
    if not isinstance(st, dict):
        st = {"merchant": {}, "category": {}, "recipient": {}}
        mem["alias_stats"] = st

    def prune_bucket(bucket: str, data: dict[str, Any], keep: set[str], max_items: int) -> None:
        if len(data) <= max_items:
            return

        stats = st.get(bucket)
        if not isinstance(stats, dict):
            stats = {}

        extra = [k for k in data.keys() if isinstance(k, str) and k not in keep]
        scored: list[tuple[int, int, str]] = []
        for k in extra:
            s = stats.get(k)
            hits = int(s.get("hits") or 0) if isinstance(s, dict) else 0
            last = int(s.get("last_used_ts") or 0) if isinstance(s, dict) else 0
            scored.append((hits, last, k))

        scored.sort(key=lambda t: (t[0], t[1]))

        while len(data) > max_items and scored:
            _, _, k = scored.pop(0)
            data.pop(k, None)
            if isinstance(stats, dict):
                stats.pop(k, None)

    prune_bucket(
        "merchant", merchant_aliases, keep=set(DEFAULT_MERCHANT_ALIASES.keys()), max_items=200
    )
    prune_bucket(
        "category", category_aliases, keep=set(DEFAULT_CATEGORY_ALIASES.keys()), max_items=100
    )


def resolve_merchant_filters(
    telegram_user_id: int, merchant_contains: str | None
) -> list[str] | None:
    if not merchant_contains:
        return None

    raw = norm(merchant_contains)
    if not raw:
        return None

    mem = load_memory(telegram_user_id)

    m_aliases = mem.get("merchant_aliases")
    if not isinstance(m_aliases, dict):
        return [raw]

    c_aliases = mem.get("category_aliases")
    if not isinstance(c_aliases, dict):
        c_aliases = {}
        mem["category_aliases"] = c_aliases

    direct = m_aliases.get(raw)
    if isinstance(direct, str):
        v = norm(direct)
        if v:
            _touch_alias(mem, "merchant", raw)
            _prune_aliases(mem)
            save_memory(telegram_user_id, mem)
            return [v]

    direct2 = c_aliases.get(raw)
    if isinstance(direct2, list):
        out = [norm(x) for x in direct2 if isinstance(x, str) and norm(x)]
        if out:
            _touch_alias(mem, "category", raw)
            _prune_aliases(mem)
            save_memory(telegram_user_id, mem)
            return out

    if len(raw) <= 3:
        return [raw]

    best_v: str | list[str] | None = None
    best_k_len = 0

    def consider(k: str, v: Any) -> None:
        nonlocal best_v, best_k_len
        kk = norm(k)
        if not kk:
            return
        if raw == kk or raw in kk or kk in raw:
            if len(kk) > best_k_len:
                best_k_len = len(kk)
                best_v = v

    for k, v in m_aliases.items():
        if isinstance(k, str) and isinstance(v, str):
            consider(k, v)

    for k, v in c_aliases.items():
        if isinstance(k, str) and isinstance(v, list):
            consider(k, v)

    if best_v is not None:
        if isinstance(best_v, str):
            vv = norm(best_v)
            if vv:
                m_aliases[raw] = vv
                mem["merchant_aliases"] = m_aliases
                _touch_alias(mem, "merchant", raw)
                _prune_aliases(mem)
                save_memory(telegram_user_id, mem)
                return [vv]
        if isinstance(best_v, list):
            out = [norm(x) for x in best_v if isinstance(x, str) and norm(x)]
            if out:
                c_aliases[raw] = out
                mem["category_aliases"] = c_aliases
                _touch_alias(mem, "category", raw)
                _prune_aliases(mem)
                save_memory(telegram_user_id, mem)
                return out

    return [raw]


def resolve_merchant_alias(telegram_user_id: int, merchant_contains: str | None) -> str | None:
    terms = resolve_merchant_filters(telegram_user_id, merchant_contains)
    if not terms:
        return None
    return terms[0]


def save_category_alias(telegram_user_id: int, alias: str, merchant_terms: list[str]) -> None:
    a = norm(alias)
    if not a:
        return

    terms = [norm(x) for x in merchant_terms if isinstance(x, str) and norm(x)]
    terms = list(dict.fromkeys(terms))
    if not terms:
        return

    mem = load_memory(telegram_user_id)
    ca = mem.get("category_aliases")
    if not isinstance(ca, dict):
        ca = {}

    ca[a] = terms
    mem["category_aliases"] = ca
    _touch_alias(mem, "category", a)
    _prune_aliases(mem)
    save_memory(telegram_user_id, mem)


def pop_pending_action(telegram_user_id: int) -> None:
    mem = load_memory(telegram_user_id)

    mem["pending_intent"] = None
    mem["pending_kind"] = None
    mem["pending_options"] = None
    mem["pending_id"] = None
    mem["pending_created_ts"] = None
    mem["pending_ttl_sec"] = None
    mem["pending_snapshot"] = None
    mem["pending_manual_mode"] = None

    save_memory(telegram_user_id, mem)


def pending_is_alive(mem: dict[str, Any], *, now_ts: int) -> bool:
    pid = mem.get("pending_id")
    if not isinstance(pid, str) or not pid:
        return False

    created = mem.get("pending_created_ts")
    ttl = mem.get("pending_ttl_sec")
    try:
        created_i = int(created)
        ttl_i = int(ttl)
    except Exception:
        return False

    ttl_i = max(10, min(ttl_i, 3600))
    return int(now_ts) - created_i <= ttl_i
