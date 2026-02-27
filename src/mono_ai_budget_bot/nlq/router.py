from __future__ import annotations

import re
import time
from typing import Any

from mono_ai_budget_bot.nlq.periods import parse_period_range

_DAYS_RE = re.compile(r"(\d{1,3})\s*(?:дн|днів|дня|days)\b", re.IGNORECASE)
_INCOME_RE = re.compile(
    r"\b(поповнен\w*|зачислен\w*|пополнен\w*|top\s*up|income|депозит)\b",
    re.IGNORECASE,
)
_TRANSFER_OUT_RE = re.compile(
    r"\b(скинув|скинула|скинути|переказ(ав|ала|ати)?|перев(ів|ела)|відправ(ив|ила|ити)?|send|sent)\b",
    re.IGNORECASE,
)
_TRANSFER_IN_RE = re.compile(
    r"\b(отрим(ав|ала|ати)?|прийшл(и|о)|надійшл(и|о)|received|got)\b",
    re.IGNORECASE,
)
_COUNT_RE = re.compile(r"\b(скільки\s+разів|кількість|count|how\s+many)\b", re.IGNORECASE)


def parse_nlq_intent(user_text: str) -> dict[str, Any]:
    text = (user_text or "").strip()
    if not text:
        return {
            "intent": "unsupported",
            "days": None,
            "start_ts": None,
            "end_ts": None,
            "merchant_contains": None,
            "recipient_alias": None,
        }

    t = text.lower()

    now_ts = int(time.time())
    pr = parse_period_range(t, now_ts)
    start_ts = pr.start_ts if pr is not None else None
    end_ts = pr.end_ts if pr is not None else None

    days: int | None = None
    m = _DAYS_RE.search(t)
    if m:
        try:
            days = int(m.group(1))
        except Exception:
            days = None
    else:
        if "тиж" in t or "week" in t:
            days = 7
        elif "місяц" in t or "month" in t:
            days = 30
        elif "сьогодні" in t or "сьодні" in t or "today" in t:
            days = 1

    if days is not None:
        days = max(1, min(days, 31))

    is_count = _COUNT_RE.search(t) is not None

    intent: str | None = None
    if _INCOME_RE.search(t) is not None:
        intent = "income_count" if is_count else "income_sum"
    elif _TRANSFER_OUT_RE.search(t) is not None:
        intent = "transfer_out_count" if is_count else "transfer_out_sum"
    elif _TRANSFER_IN_RE.search(t) is not None:
        intent = "transfer_in_count" if is_count else "transfer_in_sum"

    if intent is None:
        count_markers = [
            "транзакц",
            "операц",
            "покуп",
            "скільки було витрат",
            "кількість витрат",
            "скільки витрат було",
        ]
        if any(mk in t for mk in count_markers) or is_count:
            intent = "spend_count"
        elif "скільки" in t or "витратив" in t or "витрати" in t or "spent" in t:
            intent = "spend_sum"
        else:
            intent = "unsupported"

    merchant: str | None = None
    m2 = re.search(r"\bна\s+(.+?)(?:\s+за\s+|\s+за\s+останні\s+|$)", t)
    if m2:
        candidate = m2.group(1).strip(" .,!?:;\"'()[]{}").strip()
        if candidate:
            merchant = candidate

    return {
        "intent": intent,
        "days": days,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "merchant_contains": merchant,
        "recipient_alias": None,
    }