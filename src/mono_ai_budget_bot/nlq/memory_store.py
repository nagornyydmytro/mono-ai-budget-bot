from __future__ import annotations

import json
import re
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
        "learned_mappings": {"merchant": {}, "recipient": {}, "category": {}},
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
    if "learned_mappings" not in data or not isinstance(data.get("learned_mappings"), dict):
        data["learned_mappings"] = {"merchant": {}, "recipient": {}, "category": {}}
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


def _get_learned_bucket(mem: dict[str, Any], bucket: str) -> dict[str, list[str]]:
    lm = mem.get("learned_mappings")
    if not isinstance(lm, dict):
        lm = {"merchant": {}, "recipient": {}, "category": {}}
        mem["learned_mappings"] = lm

    b = lm.get(bucket)
    if not isinstance(b, dict):
        b = {}
        lm[bucket] = b

    out: dict[str, list[str]] = {}
    for k, v in b.items():
        if not isinstance(k, str):
            continue

        key = norm(k)
        if not key:
            continue

        values: list[str] = []
        seen: set[str] = set()

        src_items: list[str]
        if isinstance(v, list):
            src_items = [x for x in v if isinstance(x, str)]
        elif isinstance(v, str):
            src_items = [v]
        else:
            src_items = []

        for item in src_items:
            if bucket == "recipient":
                original = item.strip().lower()
                dedupe_key = norm(item)
                if not original or not dedupe_key or dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                values.append(original)
            else:
                normalized = norm(item)
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                values.append(normalized)

        if values:
            out[key] = values

    lm[bucket] = out
    mem["learned_mappings"] = lm
    return out


def get_learned_mapping(telegram_user_id: int, *, bucket: str, alias: str) -> list[str] | None:
    a = norm(alias)
    if not a:
        return None
    mem = load_memory(telegram_user_id)
    b = _get_learned_bucket(mem, bucket)
    vals = b.get(a)
    if not vals:
        return None
    _touch_alias(mem, bucket, a)
    _prune_aliases(mem)
    save_memory(telegram_user_id, mem)
    return list(vals)


def add_learned_mapping(telegram_user_id: int, *, bucket: str, alias: str, value: str) -> None:
    a = norm(alias)
    if bucket == "recipient":
        stored_value = str(value or "").strip().lower()
        dedupe_value = norm(value)
    else:
        stored_value = norm(value)
        dedupe_value = stored_value

    if not a or not stored_value or not dedupe_value:
        return

    mem = load_memory(telegram_user_id)
    b = _get_learned_bucket(mem, bucket)
    cur = b.get(a) or []

    exists = False
    for item in cur:
        if bucket == "recipient":
            if norm(item) == dedupe_value:
                exists = True
                break
        elif item == stored_value:
            exists = True
            break

    if not exists:
        cur.append(stored_value)

    b[a] = cur
    mem["learned_mappings"] = mem.get("learned_mappings")
    _touch_alias(mem, bucket, a)
    _prune_aliases(mem)
    save_memory(telegram_user_id, mem)


def set_learned_mapping(
    telegram_user_id: int, *, bucket: str, alias: str, values: list[str]
) -> None:
    a = norm(alias)
    if not a:
        return

    vv: list[str] = []
    seen: set[str] = set()
    for item in values:
        if not isinstance(item, str):
            continue
        if bucket == "recipient":
            stored_value = item.strip().lower()
            dedupe_value = norm(item)
        else:
            stored_value = norm(item)
            dedupe_value = stored_value

        if not stored_value or not dedupe_value or dedupe_value in seen:
            continue
        seen.add(dedupe_value)
        vv.append(stored_value)

    if not vv:
        return

    mem = load_memory(telegram_user_id)
    b = _get_learned_bucket(mem, bucket)
    b[a] = vv
    mem["learned_mappings"] = mem.get("learned_mappings")
    _touch_alias(mem, bucket, a)
    _prune_aliases(mem)
    save_memory(telegram_user_id, mem)


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
    a = norm(alias)
    stored_value = str(match_value or "").strip().lower()
    if not a or not stored_value:
        return

    mem = load_memory(telegram_user_id)
    ra = mem.get("recipient_aliases") or {}
    if not isinstance(ra, dict):
        ra = {}

    ra[a] = stored_value
    mem["recipient_aliases"] = ra
    save_memory(telegram_user_id, mem)

    add_learned_mapping(telegram_user_id, bucket="recipient", alias=a, value=stored_value)


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


def _resolve_merchant_filters_single(
    telegram_user_id: int,
    raw: str,
) -> list[str] | None:
    if not raw:
        return None

    mem = load_memory(telegram_user_id)
    lm_m = get_learned_mapping(telegram_user_id, bucket="merchant", alias=raw)
    if lm_m:
        return lm_m

    lm_c = get_learned_mapping(telegram_user_id, bucket="category", alias=raw)
    if lm_c:
        return lm_c

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


def resolve_merchant_filters(
    telegram_user_id: int,
    merchant_contains: str | None,
) -> list[str] | None:
    if not merchant_contains:
        return None

    raw = norm(merchant_contains)
    if not raw:
        return None

    parts = [
        norm(x)
        for x in re.split(r"\b(?:або|or|чи)\b", raw, flags=re.IGNORECASE)
        if isinstance(x, str) and norm(x)
    ]
    parts = list(dict.fromkeys(parts))
    if not parts:
        return None

    out: list[str] = []
    seen: set[str] = set()

    for part in parts:
        resolved = _resolve_merchant_filters_single(telegram_user_id, part) or []
        for item in resolved:
            vv = norm(item)
            if vv and vv not in seen:
                seen.add(vv)
                out.append(vv)

    return out or None


def resolve_merchant_alias(telegram_user_id: int, merchant_contains: str | None) -> str | None:
    terms = resolve_merchant_filters(telegram_user_id, merchant_contains)
    if not terms:
        return None
    return terms[0]


def resolve_recipient_candidates(
    telegram_user_id: int,
    recipient_alias: str | None,
) -> list[str] | None:
    raw = norm(recipient_alias)
    if not raw:
        return None

    learned = get_learned_mapping(telegram_user_id, bucket="recipient", alias=raw)
    if learned:
        out: list[str] = []
        seen: set[str] = set()
        for item in learned:
            if not isinstance(item, str):
                continue
            original = item.strip().lower()
            key = norm(item)
            if not original or not key or key in seen:
                continue
            seen.add(key)
            out.append(original)
        return out or None

    mem = load_memory(telegram_user_id)
    ra = mem.get("recipient_aliases")
    if not isinstance(ra, dict):
        return None

    direct = ra.get(raw)
    if isinstance(direct, str):
        original = direct.strip().lower()
        if original:
            return [original]

    return None


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
    set_learned_mapping(telegram_user_id, bucket="category", alias=a, values=terms)


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
