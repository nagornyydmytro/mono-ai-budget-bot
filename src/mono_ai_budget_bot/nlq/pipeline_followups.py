from __future__ import annotations

from mono_ai_budget_bot.analytics.categories import category_from_mcc
from mono_ai_budget_bot.analytics.classify import classify_kind
from mono_ai_budget_bot.nlq.text_norm import norm
from mono_ai_budget_bot.storage.tx_store import TxRecord


def resolve_followup_value(user_text: str, options: list[str] | None) -> str:
    s = (user_text or "").strip()
    if not s:
        return ""

    if options and s.isdigit():
        idx = int(s)
        if 1 <= idx <= len(options):
            return options[idx - 1].strip()

    return s


def extract_recipient_alias(pending: dict) -> str:
    for k in ("recipient_alias", "recipient_contains", "recipient", "alias"):
        v = pending.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip().lower()
    return ""


def is_paging_continue(user_text: str) -> bool:
    s = (user_text or "").strip().lower()
    if not s:
        return False
    if s.isdigit():
        return int(s) == 1
    return s in {"далі", "ще", "дальше", "next", "more", ">", ">>"}


def parse_multi_select(user_text: str, options: list[str]) -> list[str]:
    s = (user_text or "").strip().lower()
    if not s:
        return []

    if s in {"0", "ні", "нет", "cancel", "скасувати"}:
        return []

    normalized_options = [o.strip() for o in options if isinstance(o, str) and o.strip()]
    if not normalized_options:
        return []

    if s in {"всі", "усі", "all"}:
        return list(normalized_options)

    if s.startswith("всі крім") or s.startswith("усі крім"):
        tail = s.split("крім", 1)[1].strip()
        excluded = parse_multi_select(tail, options)
        return [o for o in normalized_options if o not in excluded]

    tokens = []
    for part in s.replace(";", ",").split(","):
        part = part.strip()
        if part:
            tokens.append(part)

    picked: set[str] = set()

    for t in tokens:
        if "-" in t:
            a, b = t.split("-", 1)
            if a.strip().isdigit() and b.strip().isdigit():
                x, y = int(a), int(b)
                if x > y:
                    x, y = y, x
                for i in range(x, y + 1):
                    if 1 <= i <= len(normalized_options):
                        picked.add(normalized_options[i - 1])
            continue

        if t.isdigit():
            i = int(t)
            if 1 <= i <= len(normalized_options):
                picked.add(normalized_options[i - 1])
            continue

    for t in tokens:
        if t.isdigit() or "-" in t:
            continue
        for o in normalized_options:
            if t in o.lower():
                picked.add(o)

    return list(picked)


def top_merchants(rows: list[TxRecord], query: str, limit: int = 8) -> list[str]:
    q = norm(query)
    if not q:
        return []
    qk = q.replace(" ", "")
    scores: dict[str, int] = {}

    for r in rows:
        kind = classify_kind(r.amount, r.mcc, r.description)
        if kind != "spend":
            continue
        desc = (r.description or "").strip()
        if not desc:
            continue
        dk = norm(desc).replace(" ", "")
        if qk not in dk:
            continue
        scores[desc] = scores.get(desc, 0) + abs(int(r.amount))

    items = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [k for k, _ in items[: max(1, min(int(limit), 15))]]


def top_recipients(
    rows: list[TxRecord], query: str, *, kind_prefix: str | None, limit: int = 8
) -> list[str]:
    q = norm(query)
    if not q:
        return []
    qk = q.replace(" ", "")
    scores: dict[str, int] = {}

    for r in rows:
        kind = classify_kind(r.amount, r.mcc, r.description)
        if kind_prefix == "transfer_out" and kind != "transfer_out":
            continue
        if kind_prefix == "transfer_in" and kind != "transfer_in":
            continue
        if kind_prefix is None and kind not in {"transfer_out", "transfer_in"}:
            continue

        desc = (r.description or "").strip()
        if not desc:
            continue
        dk = norm(desc).replace(" ", "")
        if qk not in dk:
            continue
        scores[desc] = scores.get(desc, 0) + abs(int(r.amount))

    items = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [k for k, _ in items[: max(1, min(int(limit), 15))]]


def seen_categories(rows: list[TxRecord]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for r in rows:
        if r.mcc is None:
            continue
        c = category_from_mcc(r.mcc)
        if not c:
            continue
        key = c.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def recipient_has_ledger_evidence(
    rows: list[TxRecord],
    *,
    value: str,
    pending_intent: dict | None,
) -> bool:
    s = norm(value)
    if not s:
        return False

    kind_prefix: str | None = None
    if isinstance(pending_intent, dict):
        intent_name = str(pending_intent.get("intent") or "")
        if intent_name.startswith("transfer_out"):
            kind_prefix = "transfer_out"
        elif intent_name.startswith("transfer_in"):
            kind_prefix = "transfer_in"

    for cand in top_recipients(rows, value, kind_prefix=kind_prefix, limit=50):
        cand_norm = norm(cand)
        if cand_norm == s or s in cand_norm:
            return True
    return False


def manual_entry_try_resolve(
    *,
    expected: str,
    user_text: str,
    pending_intent: dict | None,
    pending_options: list[str] | None,
    rows: list[TxRecord],
) -> tuple[str | None, list[str] | None, str | None]:
    s = (user_text or "").strip()
    if not s:
        return None, None, "Порожнє значення."

    if pending_options and s.isdigit():
        idx = int(s)
        if 1 <= idx <= len(pending_options):
            return pending_options[idx - 1].strip(), None, None

    expected = (expected or "").strip()

    if expected == "category":
        cats = seen_categories(rows)
        low = s.lower()
        for c in cats:
            if c.lower() == low:
                return c, None, None
        sugg = [c for c in cats if norm(low) and norm(low) in norm(c)]
        sugg = sugg[:8]
        return None, (sugg or None), "Не знайшов таку категорію в твоїх транзакціях."

    kind_prefix: str | None = None
    if isinstance(pending_intent, dict):
        intent_name = str(pending_intent.get("intent") or "")
        if intent_name.startswith("transfer_out"):
            kind_prefix = "transfer_out"
        elif intent_name.startswith("transfer_in"):
            kind_prefix = "transfer_in"

    if expected == "recipient":
        for cand in top_recipients(rows, s, kind_prefix=kind_prefix, limit=15):
            if cand.lower() == s.lower():
                return cand, None, None
        sugg = top_recipients(rows, s, kind_prefix=kind_prefix, limit=8)
        return None, (sugg or None), "Не знайшов такого отримувача в виписці."

    for cand in top_merchants(rows, s, limit=15):
        if cand.lower() == s.lower():
            return cand, None, None

    sugg = top_merchants(rows, s, limit=8)
    if not sugg and kind_prefix is not None:
        sugg = top_recipients(rows, s, kind_prefix=kind_prefix, limit=8)

    return None, (sugg or None), "Не знайшов таку назву в твоїх транзакціях."
