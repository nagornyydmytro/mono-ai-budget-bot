from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from mono_ai_budget_bot.nlq.category_keywords import detect_category
from mono_ai_budget_bot.nlq.periods import parse_period_range
from mono_ai_budget_bot.nlq.text_norm import norm

_DAYS_RE = re.compile(r"(\d{1,3})\s*(?:дн|днів|дня|days)\b", re.IGNORECASE)
_THRESHOLD_RE = re.compile(
    r"\b(більше|более|more\s+than|over|понад|вище|дорожче|менше|меньше|less\s+than|under|дешевше|до)\s*(\d+(?:[.,]\d+)?)\s*(?:грн|uah|₴)?\b",
    re.IGNORECASE,
)
_RECIPIENT_ALIAS_RE = re.compile(
    r"\b(дівчин(і|е|у|а)|дівчат(ам|ами|ах)?|мам(і|е|у|а)|тат(ові|у|а)|оренд(а|і|у)|квартир(а|і|у))\b",
    re.IGNORECASE,
)
_PREVIOUS_PERIOD_RE = re.compile(
    r"\b(попередн\w*|прошл\w*|previous|prior|минул\w*|останн\w*\s+період)\b",
    re.IGNORECASE,
)
_BASELINE_RE = re.compile(
    r"\b(зазвич(ай|но)|звичайн(о|ий)|usual|baseline|типово|як\s+правило)\b",
    re.IGNORECASE,
)
_COUNT_RE = re.compile(
    r"\b(скільки\s+разів|кількість|count|how\s+many|скільки\s+було)\b",
    re.IGNORECASE,
)
_SHARE_RE = re.compile(
    r"\b(частка|доля|share|відсот(ок|ка|ки)|який\s+відсоток|скільки\s+відсотків)\b",
    re.IGNORECASE,
)
_LAST_TIME_RE = re.compile(
    r"\b(коли(?:\s+\w+){0,3}\s+останн(ій|є)|коли(?:\s+\w+){0,3}\s+востаннє|last\s+time|when\s+was\s+the\s+last)\b",
    re.IGNORECASE,
)
_RECURRENCE_RE = re.compile(
    r"\b(як\s+часто|наскільки\s+регулярно|regularly|recurr|регулярно|часто\s+чи\s+рідко)\b",
    re.IGNORECASE,
)
_TOP_RE = re.compile(
    r"\b(топ-?\s*\d*|найбільш\w*|найтяжч\w*|найбільш\w*\s+категор\w*)\b", re.IGNORECASE
)
_OR_SPLIT_RE = re.compile(r"\s+(?:або|чи|or|й|та|and|і|плюс)\s+", re.IGNORECASE)
_COMPARE_BETWEEN_RE = re.compile(
    r"\b(що\s+більше|що\s+менше|хто\s+більше|хто\s+менше|на\s+скільки|різниц\w*|відрізня\w*|порівняй|порівняти|compare)\b",
    re.IGNORECASE,
)
_COMBINE_RE = re.compile(
    r"\b(разом|сумарно|сукупно|всього\s+разом|у\s+сумі|разом\s+пішло)\b", re.IGNORECASE
)
_AVG_TICKET_RE = re.compile(
    r"\b(середн(ій|я|є)?\s*(чек|сума\s+покупки|сума\s+транзакції)?|average\s+ticket|avg(\s+ticket)?)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SlotExtractionResult:
    slots: dict[str, Any]


_EXPLICIT_MERCHANT_WORDS = {
    "мак",
    "маку",
    "макдональдс",
    "mcdonalds",
    "mcdonald",
    "kfc",
    "bolt",
    "болт",
    "bolt food",
    "болт фуд",
    "glovo",
    "глово",
    "wolt",
    "волт",
    "loko",
    "novus",
    "новус",
    "сільпо",
    "silpo",
    "фора",
    "атб",
    "atb",
    "rozetka",
    "розетка",
    "prom",
    "пром",
    "olx",
    "олх",
    "uber",
    "убер",
    "uklon",
    "уклон",
    "lifecell",
    "лайфсел",
    "лайфселл",
    "київстар",
    "kyivstar",
    "vodafone",
    "водафон",
    "ютуб",
    "ютюб",
    "youtube",
    "spotify",
    "спотіфай",
    "спотик",
    "телеграм преміум",
    "tg premium",
}


def _strip_period_tail(value: str) -> str:
    s = (value or "").strip()
    if not s:
        return ""
    s = re.sub(
        (
            r"\s+(?:"
            r"за\s+останні\s+\d{1,3}\s*(?:дн|днів|дня|days)|"
            r"за\s+\d{1,3}\s*(?:дн|днів|дня|days)|"
            r"за\s+тиждень|за\s+неделю|за\s+місяць|"
            r"за\s+минулий\s+місяць|за\s+прошлый\s+месяц|"
            r"цього\s+місяця|этого\s+месяца|this\s+month|"
            r"місяць|тиждень|30\s+днів|7\s+днів|сьогодні|today"
            r")\s*$"
        ),
        "",
        s,
        flags=re.IGNORECASE,
    )
    return s.strip(" .,!?:;\"'()[]{}").strip()


def _strip_threshold_tail(value: str) -> str:
    s = (value or "").strip()
    if not s:
        return ""
    s = re.sub(
        r"\s+(?:більше|более|more\s+than|over|понад|вище|дорожче|менше|меньше|less\s+than|under|дешевше|до)\s*\d+(?:[.,]\d+)?\s*(?:грн|uah|₴)?\s*$",
        "",
        s,
        flags=re.IGNORECASE,
    )
    return s.strip(" .,!?:;\"'()[]{}").strip()


def _looks_like_person_name(text: str) -> bool:
    s = (text or "").strip()
    if not s:
        return False
    if re.match(r"^[A-ZА-ЯІЇЄҐ][a-zа-яіїєґ'’`-]{2,}$", s) is not None:
        return True
    if (
        re.match(
            r"^[A-ZА-ЯІЇЄҐ][a-zа-яіїєґ'’`-]{2,}\s+[A-ZА-ЯІЇЄҐ][a-zа-яіїєґ'’`-]{2,}$",
            s,
        )
        is not None
    ):
        return True
    return False


def _extract_period_slots(text: str, now_ts: int) -> dict[str, Any]:
    t = (text or "").strip().lower()
    pr = parse_period_range(t, now_ts)
    start_ts = pr.start_ts if pr is not None else None
    end_ts = pr.end_ts if pr is not None else None
    period_label: str | None = None
    if re.search(r"\b(сьогодні|сегодня|today)\b", t):
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
        elif re.search(r"\b(цього\s+місяця|этого\s+месяца|this\s+month)\b", t):
            period_label = "цей місяць"
        elif re.search(r"\b(за\s+минулий\s+місяць|за\s+прошлый\s+месяц|last\s+month)\b", t):
            period_label = "минулий місяць"
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
        elif "сьогодні" in t or "сьодні" in t or "today" in t or "вчора" in t or "yesterday" in t:
            days = 1
    if pr is not None and days is None:
        span = max(1, int((pr.end_ts - pr.start_ts + 86399) // 86400))
        days = max(1, min(span, 31))
    if days is not None:
        days = max(1, min(days, 31))
    return {
        "days": days,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "period_label": period_label,
    }


def _parse_threshold_slots(text: str) -> dict[str, Any]:
    m = _THRESHOLD_RE.search(text or "")
    if m is None:
        return {"threshold_uah": None, "direction": None}
    raw_mode = str(m.group(1) or "").strip().lower()
    raw_value = str(m.group(2) or "").strip().replace(",", ".")
    try:
        value = float(raw_value)
    except Exception:
        return {"threshold_uah": None, "direction": None}
    if value <= 0:
        return {"threshold_uah": None, "direction": None}
    under_markers = {"менше", "меньше", "less than", "under", "дешевше", "до"}
    return {
        "threshold_uah": value,
        "direction": "less_than" if raw_mode in under_markers else "more_than",
    }


def _extract_after_trigger(text: str, patterns: list[str]) -> str | None:
    s = (text or "").strip()
    if not s:
        return None
    for pat in patterns:
        m = re.search(pat, s, flags=re.IGNORECASE)
        if m is None:
            continue
        raw = str(m.group(1) or "").strip()
        raw = re.split(
            r"\b(?:за\s+останні|за\s+\d{1,3}|цього|минулого|попереднього|last|today|вчора|yesterday|ніж|чем|than)\b",
            raw,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip()
        raw = _strip_period_tail(raw)
        raw = _strip_threshold_tail(raw)
        raw = raw.strip(" .,!?:;\"'()[]{}").strip()
        if raw:
            return raw
    return None


def _split_multi_target(raw: str) -> list[str]:
    s = (raw or "").strip()
    if not s:
        return []
    parts = [p.strip(" .,!?:;\"'()[]{}") for p in _OR_SPLIT_RE.split(s) if p.strip()]
    uniq: list[str] = []
    seen: set[str] = set()
    for part in parts:
        key = norm(part)
        if not key or key in seen:
            continue
        seen.add(key)
        uniq.append(part)
    return uniq


def _looks_like_explicit_merchant(prep: str, item: str) -> bool:
    p = (prep or "").strip().lower()
    s = (item or "").strip()
    if not s:
        return False

    ns = norm(s)
    latin = re.search(r"[a-z]", s, flags=re.IGNORECASE) is not None
    has_quote = any(ch in s for ch in ('"', "«", "»"))
    title_like = re.match(r"^[A-ZА-ЯІЇЄҐ][\w'’`-]+$", s) is not None
    brand_like = ns in _EXPLICIT_MERCHANT_WORDS

    if p in {"у", "в"}:
        return latin or has_quote or title_like or brand_like

    return p == "на" and (latin or has_quote or title_like or brand_like)


def _extract_merchant_targets(text: str) -> tuple[list[str], bool, str | None]:
    t = (text or "").strip()
    lower = t.lower()
    parts: list[tuple[str, str]] = []
    for m in re.finditer(r"\b(на|у|в)\s+([^\?\.,!]+)", lower, flags=re.IGNORECASE):
        prep = str(m.group(1) or "").strip().lower()
        cand = str(m.group(2) or "").strip()
        if cand:
            parts.append((prep, cand))
    if not parts:
        return [], False, None
    prep, cand = parts[-1]
    cand = re.split(r"\b(ніж|чем|than)\b", cand, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    if re.match(r"^(скільки|сколько|how\s+much|how\s+many)\b", cand, flags=re.IGNORECASE):
        if " на " in cand:
            cand = cand.split(" на ")[-1].strip()
    cand = _strip_period_tail(cand)
    cand = _strip_threshold_tail(cand)
    cand = cand.strip(" .,!?:;\"'()[]{}").strip()
    if not cand or re.search(r"\b(\d+%|\d+)\b", cand):
        return [], False, None
    if cand.startswith("яку категорію"):
        return [], False, None
    if re.fullmatch(r"(попередн\w*|прошл\w*|previous|prior)", cand, flags=re.IGNORECASE):
        return [], False, None
    if detect_category(cand) is not None and not _looks_like_explicit_merchant(prep, cand):
        return [], False, None
    candidates = _split_multi_target(cand)
    merchant_targets: list[str] = []
    display_targets: list[str] = []
    explicit_single = False
    for item in candidates:
        if prep in {"у", "в"} and re.match(r"^(мене|меня|me)\b", item, flags=re.IGNORECASE):
            continue
        explicit_merchant = _looks_like_explicit_merchant(prep, item)
        cat = detect_category(item)
        if cat is not None and not explicit_merchant:
            continue
        merchant_targets.append(norm(item))
        display_targets.append(item.lower())
        if explicit_merchant:
            explicit_single = True
    exact = len(merchant_targets) == 1 and explicit_single
    display = None
    if display_targets:
        display = " або ".join(display_targets) if len(display_targets) > 1 else display_targets[0]
    return merchant_targets, exact, display


def _extract_category_targets(text: str) -> list[str]:
    s = (text or "").strip()
    raw_candidates: list[str] = []

    matches = re.findall(r"\b(?:на|у|в)\s+([^\?\.,!]+)", s, flags=re.IGNORECASE)
    if matches:
        raw_candidates.append(str(matches[-1] or "").strip())

    if ":" in s:
        raw_candidates.append(str(s.split(":", 1)[1] or "").strip())

    merchant_targets, merchant_exact, _ = _extract_merchant_targets(s)
    if merchant_targets and merchant_exact:
        raw_candidates.append(s)
    else:
        raw_candidates.append(s)

    out: list[str] = []
    seen: set[str] = set()

    for raw in raw_candidates:
        candidate = re.split(r"\b(ніж|чем|than)\b", raw, maxsplit=1, flags=re.IGNORECASE)[0].strip()
        candidate = _strip_period_tail(candidate)
        candidate = _strip_threshold_tail(candidate)
        candidate = candidate.strip(" .,!?:;\"'()[]{}").strip()
        if not candidate:
            continue

        items = _split_multi_target(candidate)
        if not items:
            items = [candidate]

        for item in items:
            cat = detect_category(item)
            if cat is not None and cat not in seen:
                seen.add(cat)
                out.append(cat)

        if len(out) >= 2:
            return out

    return out


def _extract_recipient_slots(text: str) -> dict[str, Any]:
    original = (text or "").strip()
    if not original:
        return {
            "recipient_alias": None,
            "recipient_target": None,
            "recipient_targets": [],
            "recipient_mode": None,
            "recipient_explicit_name": False,
        }
    lower = original.lower()
    m = _RECIPIENT_ALIAS_RE.search(lower)
    if m is not None:
        alias = str(m.group(1) or "").strip().lower() or None
        return {
            "recipient_alias": alias,
            "recipient_target": alias,
            "recipient_targets": [alias] if alias else [],
            "recipient_mode": "generic",
            "recipient_explicit_name": False,
        }
    recipient_target = _extract_after_trigger(
        original,
        patterns=[
            r"\b(?:переказ(?:ав|ала|ував|увала|увати|ати)?|перев(?:ів|ела|ести)?|відправ(?:ив|ила|ити)?)\s+(.+?)(?:[?.!,]|$)",
        ],
    )
    if not recipient_target:
        return {
            "recipient_alias": None,
            "recipient_target": None,
            "recipient_targets": [],
            "recipient_mode": None,
            "recipient_explicit_name": False,
        }
    recipient_targets = [part.lower() for part in _split_multi_target(recipient_target)]
    explicit = _looks_like_person_name(recipient_target) or all(
        not _RECIPIENT_ALIAS_RE.search(item) for item in recipient_targets
    )
    return {
        "recipient_alias": recipient_target.lower(),
        "recipient_target": recipient_target,
        "recipient_targets": recipient_targets,
        "recipient_mode": "explicit" if explicit else "generic",
        "recipient_explicit_name": explicit,
    }


def _detect_comparison_mode(text: str) -> str | None:
    t = (text or "").lower()
    if _BASELINE_RE.search(t) is not None:
        return "baseline"
    if _PREVIOUS_PERIOD_RE.search(t) is not None and re.search(
        r"\b(порівняй|порівняти|compare|різниц\w*|відрізня\w*|біл\w*|мен\w*)\b",
        t,
        flags=re.IGNORECASE,
    ):
        return "previous_period"
    if re.search(r"\b(?:між|between)\b", t) and _OR_SPLIT_RE.search(t):
        return "between_entities"
    if _COMPARE_BETWEEN_RE.search(t) is not None and _OR_SPLIT_RE.search(t):
        return "between_entities"
    return None


def _detect_aggregation(text: str) -> str | None:
    t = (text or "").lower()
    if _LAST_TIME_RE.search(t) is not None:
        return "last_time"
    if _RECURRENCE_RE.search(t) is not None:
        return "recurrence"
    if _AVG_TICKET_RE.search(t) is not None:
        return "avg_ticket"
    if _TOP_RE.search(t) is not None:
        return "top"
    if _COMBINE_RE.search(t) is not None:
        return "sum_entities"
    if _SHARE_RE.search(t) is not None:
        return "share"
    if _COUNT_RE.search(t) is not None:
        return "count"
    if re.search(r"\b(скільки|сколько|how\s+much|сума|sum|amount)\b", t):
        return "sum"
    return None


def extract_slots(text: str, now_ts: int) -> SlotExtractionResult:
    period_slots = _extract_period_slots(text, now_ts)
    threshold_slots = _parse_threshold_slots(text)
    merchant_targets, merchant_exact, merchant_contains = _extract_merchant_targets(text)
    category_targets = _extract_category_targets(text)
    recipient_slots = _extract_recipient_slots(text)
    comparison_mode = _detect_comparison_mode(text)
    aggregation = _detect_aggregation(text)

    if merchant_targets and merchant_exact and category_targets:
        category_targets = []

    target_type = None
    if recipient_slots["recipient_target"]:
        target_type = "recipient"
    elif merchant_targets:
        target_type = "merchant"
    elif category_targets:
        target_type = "category"
    slots = {
        **period_slots,
        **threshold_slots,
        **recipient_slots,
        "merchant_contains": merchant_contains,
        "merchant_targets": merchant_targets,
        "merchant_exact": merchant_exact,
        "category": category_targets[0] if category_targets else None,
        "category_targets": category_targets,
        "comparison_mode": comparison_mode,
        "aggregation": aggregation,
        "target_type": target_type,
        "currency_pair": None,
    }
    return SlotExtractionResult(slots=slots)
