from __future__ import annotations

import re
import time
from typing import Any

from mono_ai_budget_bot.nlq.category_keywords import detect_category
from mono_ai_budget_bot.nlq.periods import parse_period_range
from mono_ai_budget_bot.nlq.types import NLQIntent, NLQRequest

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
    (
        r"\b("
        r"вхідн\w*\s+переказ\w*|"
        r"входящ\w*\s+перевод\w*|"
        r"incoming\s+transfer(s)?|"
        r"inbound\s+transfer(s)?|"
        r"отрим(ав|ала|ати)?|"
        r"прийшл(и|о)|"
        r"надійшл(и|о)|"
        r"received|got"
        r")\b"
    ),
    re.IGNORECASE,
)
_COUNT_RE = re.compile(r"\b(скільки\s+разів|кількість|count|how\s+many)\b", re.IGNORECASE)
_RECIPIENT_ALIAS_RE = re.compile(
    r"\b(дівчин(і|е|у|а)|мам(і|е|у|а)|тат(ові|у|а)|оренд(а|і|у)|квартир(а|і|у))\b", re.IGNORECASE
)
_COMPARE_RE = re.compile(
    r"\b(на\s+скільки|скільки\s+більше|скільки\s+менше|порівнян|compare)\b", re.IGNORECASE
)
_BASELINE_RE = re.compile(r"\b(зазвич(ай|но)|звичайн(о|ий)|usual|baseline)\b", re.IGNORECASE)
_COUNT_PHRASING_RE = re.compile(
    r"\b(скільки\s+було|сколько\s+было|how\s+many)\b",
    re.IGNORECASE,
)
_INCOME_COUNT_PHRASING_RE = re.compile(
    r"\b(скільки|сколько|how\s+many)\b.*\bбуло\b.*\bпоповнен",
    re.IGNORECASE,
)
_INCOME_COUNT_OVERRIDE_RE = re.compile(
    r"\b(скільки|сколько|how\s+many)\b.*\bбуло\b.*\bпоповнен",
    re.IGNORECASE,
)
_TRANSFER_COUNT_OVERRIDE_RE = re.compile(
    r"\b(скільки|сколько|how\s+many)\b.*\bбуло\b.*\b(переказ|транзакц)",
    re.IGNORECASE,
)
_MERCHANT_AFTER_NA_RE = re.compile(
    r"\bна\s+([^\?\.,!]+?)(?:\s+(ніж|чем)\s+зазвичай|\s+than\s+usual|\s+usual|\s+звичайно|$)",
    re.IGNORECASE,
)
_MERCHANT_TAIL_RE = re.compile(
    r"\b(?:на|в|у)\s+([^\?\.,!]+)$",
    re.IGNORECASE,
)

_MERCHANT_NA_SEGMENT_RE = re.compile(
    r"\bна\s+([^\?\.,!]+)",
    re.IGNORECASE,
)


def parse_nlq_intent(user_text: str, now_ts: int | None = None) -> dict[str, Any]:
    text = (user_text or "").strip()
    if now_ts is None:
        now_ts = int(time.time())
    now_ts = int(now_ts)
    if not text:
        return {
            "intent": "unsupported",
            "days": None,
            "start_ts": None,
            "end_ts": None,
            "merchant_contains": None,
            "recipient_alias": None,
            "period_label": None,
            "category": None,
        }

    t = text.lower()
    category = detect_category(t)

    pr = parse_period_range(t, now_ts)
    start_ts = pr.start_ts if pr is not None else None
    end_ts = pr.end_ts if pr is not None else None

    period_label: str | None = None
    if re.search(r"\b(сьогодні|'сегодня|today)\b", t):
        period_label = "сьогодні"
    elif re.search(r"\b(вчора|вчера|yesterday)\b", t):
        period_label = "вчора"
    else:
        m_lbl = re.search(
            r"\b(за\s+останні\s+|за\s+последние\s+|last\s+)(\d{1,3})\s*(дн(і|ів)?|дней|days)\b",
            t,
        )
        if m_lbl:
            period_label = f"останні {int(m_lbl.group(2))} днів"
        elif re.search(r"\b(за\s+тиждень|за\s+неделю|last\s+week)\b", t):
            period_label = "останній тиждень"
        elif re.search(r"\b(за\s+минулий\s+місяць|за\s+прошлый\s+месяц|last\s+month)\b", t):
            period_label = "минулий місяць"
        else:
            months = [
                "січень",
                "сiчень",
                "январь",
                "january",
                "лютий",
                "февраль",
                "february",
                "березень",
                "март",
                "march",
                "квітень",
                "апрель",
                "april",
                "травень",
                "май",
                "may",
                "червень",
                "июнь",
                "june",
                "липень",
                "июль",
                "july",
                "серпень",
                "август",
                "august",
                "вересень",
                "сентябрь",
                "september",
                "жовтень",
                "октябрь",
                "october",
                "листопад",
                "ноябрь",
                "november",
                "грудень",
                "декабрь",
                "december",
            ]
            for mn in months:
                if re.search(rf"\bза\s+{re.escape(mn)}\b", t):
                    m_year = re.search(rf"\bза\s+{re.escape(mn)}\s+(\d{{4}})\b", t)
                    period_label = f"{mn} {m_year.group(1)}" if m_year else mn
                    break

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

    if pr is not None and days is None:
        span = max(1, int((pr.end_ts - pr.start_ts + 86399) // 86400))
        days = max(1, min(span, 31))

    if days is not None:
        days = max(1, min(days, 31))

    is_count = _COUNT_RE.search(t) is not None
    want_compare = _COMPARE_RE.search(t) is not None and _BASELINE_RE.search(t) is not None

    intent: str | None = None
    want_sum = bool(
        re.search(
            r"\b(скільки|сколько|how\s+much|на\s+суму|сума|сумма|amount|sum)\b",
            t,
            re.IGNORECASE,
        )
    )
    if _INCOME_RE.search(t):
        if _INCOME_COUNT_PHRASING_RE.search(t):
            intent = "income_count"
        elif want_sum:
            intent = "income_sum"
        else:
            intent = "income_count"
    if _TRANSFER_OUT_RE.search(t):
        if _COUNT_PHRASING_RE.search(t) and re.search(r"\b(переказ(ів)?|транзакц(ій|ии))\b", t):
            intent = "transfer_out_count"
        elif want_sum:
            intent = "transfer_out_sum"
        else:
            intent = "transfer_out_count"
    if _TRANSFER_IN_RE.search(t):
        if _COUNT_PHRASING_RE.search(t) and re.search(r"\b(переказ(ів)?|транзакц(ій|ии))\b", t):
            intent = "transfer_in_count"
        elif want_sum:
            intent = "transfer_in_sum"
        else:
            intent = "transfer_in_count"

    if intent is None:
        count_markers = [
            "транзакц",
            "операц",
            "покуп",
            "скільки було витрат",
            "кількість витрат",
            "скільки витрат було",
        ]
        if want_compare:
            intent = "compare_to_baseline"
        elif any(mk in t for mk in count_markers) or is_count:
            intent = "spend_count"
        elif "скільки" in t or "витратив" in t or "витрати" in t or "spent" in t:
            intent = "spend_sum"
        else:
            intent = "unsupported"

    merchant: str | None = None

    parts: list[str] = []
    for m in re.finditer(r"\bна\s+([^\?\.,!]+)", t, flags=re.IGNORECASE):
        cand = m.group(1).strip()
        if cand:
            parts.append(cand)

    if parts:
        cand = parts[-1]
        cand = re.split(r"\b(ніж|чем|than)\b", cand, maxsplit=1, flags=re.IGNORECASE)[0].strip()

        if re.match(r"^(скільки|сколько|how\s+much|how\s+many)\b", cand, flags=re.IGNORECASE):
            if " на " in cand:
                cand = cand.split(" на ")[-1].strip()

        cand = cand.strip(" .,!?:;\"'()[]{}").strip()
        if cand and not re.search(r"\b(\d+%|\d+)\b", cand):
            merchant = cand

    recipient_alias = None
    m3 = _RECIPIENT_ALIAS_RE.search(t)
    if m3:
        recipient_alias = m3.group(1).lower()

    if _INCOME_COUNT_OVERRIDE_RE.search(t):
        if intent in ("income_sum", "income_count"):
            intent = "income_count"

    if _TRANSFER_COUNT_OVERRIDE_RE.search(t):
        if intent in ("transfer_in_sum", "transfer_in_count"):
            intent = "transfer_in_count"
        elif intent in ("transfer_out_sum", "transfer_out_count"):
            intent = "transfer_out_count"

    return {
        "intent": intent,
        "days": days,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "merchant_contains": merchant,
        "recipient_alias": recipient_alias,
        "period_label": period_label,
        "category": category,
    }


def route(req: NLQRequest) -> NLQIntent | None:
    parsed = parse_nlq_intent(req.text, req.now_ts)
    if not parsed or parsed.get("intent") in (None, "unsupported"):
        return None
    return NLQIntent(name=parsed["intent"], slots=parsed)
