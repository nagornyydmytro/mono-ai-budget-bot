from __future__ import annotations

import re
from typing import Any

_DAYS_RE = re.compile(r"(\d{1,2})\s*(?:дн|днів|дня|days)\b", re.IGNORECASE)


def parse_nlq_intent(user_text: str) -> dict[str, Any]:
    """
    Local (no-LLM) NLQ parser.
    Supported:
      - spend_sum: "скільки я витратив ...", "витрати за N днів ..."
      - spend_count: "скільки транзакцій/витрат було ..."

    Output schema:
      {"intent": "spend_sum"|"spend_count"|"unsupported", "days": int|None, "merchant_contains": str|None}
    """
    text = (user_text or "").strip()
    if not text:
        return {"intent": "unsupported", "days": None, "merchant_contains": None}

    t = text.lower()

    count_markers = [
        "транзакц",
        "операц",
        "покуп",
        "скільки було витрат",
        "кількість витрат",
        "скільки витрат було",
    ]
    if any(m in t for m in count_markers):
        intent = "spend_count"
    elif "скільки" in t or "витратив" in t or "витрати" in t or "spent" in t:
        intent = "spend_sum"
    else:
        intent = "unsupported"

    days = None
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

    merchant = None
    m2 = re.search(r"\bна\s+(.+?)(?:\s+за\s+|\s+за\s+останні\s+|$)", t)
    if m2:
        candidate = m2.group(1).strip(" .,!?:;\"'()[]{}").strip()
        if candidate:
            merchant = candidate

    return {"intent": intent, "days": days, "merchant_contains": merchant}
