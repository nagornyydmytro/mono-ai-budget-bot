from __future__ import annotations

import re
import time
from typing import Any

from mono_ai_budget_bot.currency import parse_currency_conversion_query, parse_currency_rate_query
from mono_ai_budget_bot.nlq.models import QueryIntent, Slots, canonical_intent_family
from mono_ai_budget_bot.nlq.slot_extractor import extract_slots
from mono_ai_budget_bot.nlq.types import NLQIntent, NLQRequest

_DAYS_RE = re.compile(r"(\d{1,3})\s*(?:дн|днів|дня|days)\b", re.IGNORECASE)
_INCOME_RE = re.compile(
    (
        r"\b("
        r"дох(ід|оди|одів)|"
        r"зароб(ив|ила|ити|іток|ітки)?|"
        r"поповнен\w*|"
        r"зачислен\w*|"
        r"пополнен\w*|"
        r"top\s*up|income|депозит"
        r")\b"
    ),
    re.IGNORECASE,
)

_TRANSFER_IN_RE = re.compile(
    (
        r"\b("
        r"вхідн\w*\s+переказ\w*|"
        r"входящ\w*\s+перевод\w*|"
        r"incoming\s+transfer(s)?|"
        r"inbound\s+transfer(s)?|"
        r"переказ\w*\s+на\s+карт\w*|"
        r"перевод\w*\s+на\s+карт\w*|"
        r"отрим(ав|ала|ати)?|"
        r"прийшл(и|о)|"
        r"надійшл(и|о)|"
        r"received|got"
        r")\b"
    ),
    re.IGNORECASE,
)

_COUNT_RE = re.compile(r"\b(скільки\s+разів|кількість|count|how\s+many)\b", re.IGNORECASE)
_TRANSACTION_COUNT_RE = re.compile(
    r"\b(транзакц(ій|ии)|операц(ій|ии)|операції)\b",
    re.IGNORECASE,
)
_REAL_SPEND_RE = re.compile(
    r"\b(реальн\w*\s+витрат\w*|real\s+spend|без\s+переказ\w*)\b",
    re.IGNORECASE,
)

_COMPARE_RE = re.compile(
    r"\b(на\s+скільки|скільки\s+більше|скільки\s+менше|порівнян\w*|порівняй|порівняти|compare)\b",
    re.IGNORECASE,
)

_BASELINE_RE = re.compile(r"\b(зазвич(ай|но)|звичайн(о|ий)|usual|baseline)\b", re.IGNORECASE)
_COUNT_PHRASING_RE = re.compile(
    r"\b(скільки\s+разів|кількість|count|how\s+many)\b",
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
    (
        r"("
        r"\b(скільки\s+разів|кількість|count|how\s+many)\b.*\b(переказ|транзакц)|"
        r"\bскільки\b.*\bбуло\b.*\b(вхідн\w*\s+)?переказ(ів)?\b(?!\s+на\s+карт\w*)"
        r")"
    ),
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

_TRANSFER_OUT_RE = re.compile(
    r"\b(скинув|скинула|скинути|переказ(ав|ала|ати|ував|увала|увати)?|переказ(и|ів)?|перев(ів|ела)|відправ(ив|ила|ити)?|send|sent)\b",
    re.IGNORECASE,
)

_RECIPIENT_ALIAS_RE = re.compile(
    r"\b(дівчин(і|е|у|а)|дівчат(ам|ами|ах)?|мам(і|е|у|а)|тат(ові|у|а)|оренд(а|і|у)|квартир(а|і|у))\b",
    re.IGNORECASE,
)

_LAST_TIME_RE = re.compile(
    r"\b(коли(?:\s+\w+){0,3}\s+останн(ій|є)|коли(?:\s+\w+){0,3}\s+востаннє|last\s+time|when\s+was\s+the\s+last)\b",
    re.IGNORECASE,
)

_RECURRENCE_RE = re.compile(
    r"\b(як\s+часто|наскільки\s+регулярно|regularly|recurr|регулярно)\b",
    re.IGNORECASE,
)

_THRESHOLD_RE = re.compile(
    r"\b(більше|более|more\s+than|over|понад|вище|дорожче|менше|меньше|less\s+than|under|дешевше|до)\s*(\d+(?:[.,]\d+)?)\s*(?:грн|uah|₴)?\b",
    re.IGNORECASE,
)

_PREVIOUS_PERIOD_RE = re.compile(
    r"\b(поперед\w*|прошл\w*|previous|prior)\b",
    re.IGNORECASE,
)

_TOP_MERCHANTS_RE = re.compile(
    (
        r"\b("
        r"топ-?\s*\d*\s*мерчант\w*|"
        r"топ-?\s*\d*\s*merchant\w*|"
        r"де\s+я\s+витратив\s+найбільше|"
        r"у\s+якого\s+мерчант\w*.*найбільше|"
        r"хто\s+(?:перший|другий|третій).*\bмерчант"
        r")\b"
    ),
    re.IGNORECASE,
)

_TOP_GROWTH_RE = re.compile(
    r"\b(що\s+найбільше\s+виросло|що\s+виросло\s+найбільше|що\s+зараз\s+росте|що\s+росте)\b",
    re.IGNORECASE,
)

_TOP_DECLINE_RE = re.compile(
    r"\b(що\s+найбільше\s+просіло|що\s+впало|що\s+зменшилось)\b",
    re.IGNORECASE,
)

_SUMMARY_SHORT_RE = re.compile(
    r"\b(поясни.*витрат\w*.*коротко|коротко.*поясни.*витрат\w*|short\s+summary)\b",
    re.IGNORECASE,
)

_INSIGHTS_THREE_RE = re.compile(
    r"\b(дай\s+\d+\s+головн\w+\s+інсайт\w*|головн\w+\s+інсайт\w*|main\s+insights)\b",
    re.IGNORECASE,
)

_UNUSUAL_RE = re.compile(
    r"\b(що.*виглядає\s+незвичн\w*|що.*незвичн\w*|що.*аномальн\w*|unusual|anomal)\b",
    re.IGNORECASE,
)

_EXPLAIN_GROWTH_RE = re.compile(
    r"\b(чому.*витрат\w*.*зросл\w*|чому.*витрат\w*.*виросл\w*|чим.*пояснюєт\w*.*ріст.*витрат\w*|чим.*пояснюєт\w*.*зростан\w*.*витрат\w*|why.*spend.*up)\b",
    re.IGNORECASE,
)

_MERCHANT_AFTER_PLACE_RE = re.compile(
    r"\b(?:у|в|на)\s+([^\?\.,!]+?)(?:\s+(?:ніж|чем)\s+зазвичай|\s+than\s+usual|$)",
    re.IGNORECASE,
)

_TOP_CATEGORIES_RE = re.compile(
    (
        r"\b("
        r"на\s+що\s+я\s+найбільше|"
        r"на\s+яку\s+категорію\s+я\s+витратив\s+найбільше|"
        r"яка\s+категорія\s+найбільш\w*|"
        r"яка\s+(?:друга|третя)\s+найбільш\w*\s+категор\w*|"
        r"яка\s+(?:найбільш\w*|друга|третя)\s+категор\w*|"
        r"топ-?\s*\d*\s*категор"
        r")"
    ),
    re.IGNORECASE,
)

_SHARE_RE = re.compile(
    r"\b(частка|доля|share|відсот(ок|ка|ки))\b",
    re.IGNORECASE,
)

_AVG_TICKET_RE = re.compile(
    r"\b(середн(ій|ій\s+чек|ій\s+чеку)|average\s+ticket|avg)\b",
    re.IGNORECASE,
)

_COMBINE_RE = re.compile(
    r"\b(разом|сумарно|сукупно|всього\s+разом)\b",
    re.IGNORECASE,
)

_RANK_SECOND_RE = re.compile(r"\b(друг(а|ий)|second|2-?га|2-?й)\b", re.IGNORECASE)
_RANK_THIRD_RE = re.compile(r"\b(трет(я|ій)|third|3-?тя|3-?й)\b", re.IGNORECASE)

_SPEND_BASE_COMPARE_RE = re.compile(
    r"\b(total\s+spend|all\s+spend|усіх\s+витрат|загальн\w+\s+витрат\w*)\b",
    re.IGNORECASE,
)


def _parse_threshold_uah(text: str) -> tuple[str | None, float | None]:
    m = _THRESHOLD_RE.search(text or "")
    if m is None:
        return None, None

    raw_mode = str(m.group(1) or "").strip().lower()
    raw_value = str(m.group(2) or "").strip().replace(",", ".")
    try:
        value = float(raw_value)
    except Exception:
        return None, None

    if value <= 0:
        return None, None

    under_markers = {"менше", "меньше", "less than", "under", "дешевше", "до"}
    mode = "under" if raw_mode in under_markers else "over"
    return mode, value


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


def _extract_recipient_target(text: str) -> tuple[str | None, bool]:
    original = (text or "").strip()
    if not original:
        return None, False

    lower = original.lower()

    m = _RECIPIENT_ALIAS_RE.search(lower)
    if m is not None:
        return str(m.group(1) or "").strip().lower() or None, False

    m2 = re.search(
        (
            r"\b(?:"
            r"переказ(?:ав|ала|ував|увала|увати|ати)?|"
            r"перев(?:ів|ела|ести)?|"
            r"відправ(?:ив|ила|ити)?"
            r")\s+(.+?)(?:"
            r"\s+\b(?:за\s+останні|за\s+\d{1,3}|цього|минулого|попереднього|last|today|вчора|yesterday)\b|"
            r"[?.!,]|$)"
        ),
        original,
        flags=re.IGNORECASE,
    )
    if m2 is None:
        return None, False

    raw = str(m2.group(1) or "").strip()
    raw = re.split(r"\b(?:ніж|чем|than)\b", raw, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    raw = _strip_period_tail(raw)
    raw = _strip_threshold_tail(raw)
    raw = raw.strip(" .,!?:;\"'()[]{}").strip()

    if not raw:
        return None, False

    raw_lower = raw.lower()
    if raw_lower in {"на", "до", "в", "у", "комусь", "комусь із", "комусь з"}:
        return None, False

    explicit_name = re.match(r"^[A-ZА-ЯІЇЄҐ]", raw) is not None
    return raw_lower, explicit_name


def _extract_top_n(text: str) -> int:
    m = re.search(r"\bтоп-?\s*(\d{1,2})\b", text or "", flags=re.IGNORECASE)
    if m:
        try:
            return max(1, min(int(m.group(1)), 10))
        except Exception:
            return 5
    if _RANK_THIRD_RE.search(text or ""):
        return 3
    if _RANK_SECOND_RE.search(text or ""):
        return 2
    if re.search(r"\bяка\s+категорія\s+найбільш\w*\b", text or "", flags=re.IGNORECASE):
        return 1
    if re.search(
        r"\bна\s+яку\s+категорію\s+я\s+витратив\s+найбільше\b",
        text or "",
        flags=re.IGNORECASE,
    ):
        return 1
    if re.search(r"\bде\s+я\s+витратив\s+найбільше\b", text or "", flags=re.IGNORECASE):
        return 1
    if re.search(r"\bу\s+якого\s+мерчант\w*.*найбільше\b", text or "", flags=re.IGNORECASE):
        return 1
    return 5


def _extract_rank_position(text: str) -> int | None:
    if _RANK_THIRD_RE.search(text or ""):
        return 3
    if _RANK_SECOND_RE.search(text or ""):
        return 2
    if _extract_top_n(text) == 1:
        return 1
    return None


def _is_non_merchant_prepositional_phrase(prep: str, cand: str) -> bool:
    p = (prep or "").strip().lower()
    s = (cand or "").strip().lower()
    if not s:
        return False

    if p in {"у", "в"} and re.match(r"^(мене|меня|me)\b", s, flags=re.IGNORECASE):
        return True

    if re.fullmatch(r"(поперед\w*|прошл\w*|previous|prior)", s, flags=re.IGNORECASE):
        return True

    return False


def _looks_like_explicit_merchant(prep: str, cand: str) -> bool:
    p = (prep or "").strip().lower()
    s = (cand or "").strip()
    if not s:
        return False

    if p in {"у", "в"}:
        return True

    latin = re.search(r"[a-z]", s, flags=re.IGNORECASE) is not None
    has_quote = any(ch in s for ch in ("'", "’", "`"))

    return p == "на" and (latin or has_quote)


def _extract_after_trigger(
    text: str,
    patterns: list[str],
) -> str | None:
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


def _looks_like_person_name(text: str) -> bool:
    s = (text or "").strip()
    if not s:
        return False
    if re.match(r"^[A-ZА-ЯІЇЄҐ][a-zа-яіїєґ'’`-]{2,}$", s) is not None:
        return True
    if (
        re.match(r"^[A-ZА-ЯІЇЄҐ][a-zа-яіїєґ'’`-]{2,}\s+[A-ZА-ЯІЇЄҐ][a-zа-яіїєґ'’`-]{2,}$", s)
        is not None
    ):
        return True
    return False


def _is_open_ended_finance_question(text: str) -> bool:
    s = (text or "").strip().lower()
    if not s:
        return False

    open_markers = [
        "поясни",
        "проаналізуй",
        "що це говорить",
        "який висновок",
        "чи це нормально",
        "чому так",
        "регулярні повсякденні витрати",
        "разові великі покупки",
        "на що це схоже",
        "що з цього найважливіше",
        "що мене насторожує",
    ]
    return any(marker in s for marker in open_markers)


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
            "entity_kind": "spend",
            "threshold_uah": None,
        }

    t = text.lower()
    conv = parse_currency_conversion_query(text)
    if conv is not None:
        return {
            "intent": "currency_convert",
            "amount": conv.amount,
            "from": conv.from_alpha,
            "to": conv.to_alpha,
        }

    rate_q = parse_currency_rate_query(text)
    if rate_q is not None:
        return {
            "intent": "currency_rate",
            "from": rate_q.base_alpha,
            "to": rate_q.quote_alpha,
        }

    extracted = extract_slots(text, now_ts).slots
    category = extracted.get("category")
    days = extracted.get("days")
    start_ts = extracted.get("start_ts")
    end_ts = extracted.get("end_ts")
    period_label = extracted.get("period_label")

    is_count = _COUNT_RE.search(t) is not None
    want_last_time = _LAST_TIME_RE.search(t) is not None
    want_recurrence = _RECURRENCE_RE.search(t) is not None
    want_top_categories = _TOP_CATEGORIES_RE.search(t) is not None
    want_top_merchants = _TOP_MERCHANTS_RE.search(t) is not None
    want_share = _SHARE_RE.search(t) is not None
    want_top_growth = _TOP_GROWTH_RE.search(t) is not None
    want_top_decline = _TOP_DECLINE_RE.search(t) is not None
    want_summary_short = _SUMMARY_SHORT_RE.search(t) is not None
    want_insights_three = _INSIGHTS_THREE_RE.search(t) is not None
    want_unusual = _UNUSUAL_RE.search(t) is not None
    want_explain_growth = _EXPLAIN_GROWTH_RE.search(t) is not None
    want_avg_ticket = _AVG_TICKET_RE.search(t) is not None
    want_combined_sum = _COMBINE_RE.search(t) is not None
    rank_position = _extract_rank_position(t)
    direction = extracted.get("direction")
    threshold_uah = extracted.get("threshold_uah")

    intent: str | None = None
    entity_kind = "spend"
    count_scope: str | None = None
    spend_basis = "real" if _REAL_SPEND_RE.search(t) is not None else "gross"
    want_sum = bool(
        re.search(
            r"\b(скільки|сколько|how\s+much|на\s+суму|сума|сумма|amount|sum|яка\s+.*сума)\b",
            t,
            re.IGNORECASE,
        )
    )
    if _INCOME_RE.search(t):
        entity_kind = "income"
        if _INCOME_COUNT_PHRASING_RE.search(t):
            intent = "income_count"
        elif want_sum:
            intent = "income_sum"
        else:
            intent = "income_count"
    if _TRANSFER_OUT_RE.search(t):
        entity_kind = "transfer_out"
        if _COUNT_PHRASING_RE.search(t) and re.search(r"\b(переказ(ів)?|транзакц(ій|ии))\b", t):
            intent = "transfer_out_count"
        elif want_sum:
            intent = "transfer_out_sum"
        else:
            intent = "transfer_out_count"
    if _TRANSFER_IN_RE.search(t):
        entity_kind = "transfer_in"
        if _COUNT_PHRASING_RE.search(t) and re.search(r"\b(переказ(ів)?|транзакц(ій|ии))\b", t):
            intent = "transfer_in_count"
        elif want_sum:
            intent = "transfer_in_sum"
        else:
            intent = "transfer_in_count"

    if intent is None:
        entity_kind = "spend"
        transaction_count_markers = [
            "транзакц",
            "операц",
        ]
        spend_count_markers = [
            "покуп",
            "скільки було витрат",
            "кількість витрат",
            "скільки витрат було",
        ]
        spend_sum_markers = [
            "скільки",
            "витратив",
            "витрати",
            "витрат",
            "реальні витрати",
            "сума витрат",
            "spent",
        ]
        if any(mk in t for mk in transaction_count_markers):
            intent = "spend_count"
            count_scope = "transactions"
        elif any(mk in t for mk in spend_count_markers) or is_count:
            intent = "spend_count"
        elif any(mk in t for mk in spend_sum_markers) or want_sum:
            intent = "spend_sum"
        else:
            intent = "unsupported"

    merchant = extracted.get("merchant_contains")
    merchant_exact = bool(extracted.get("merchant_exact"))
    merchant_targets = extracted.get("merchant_targets") or []

    recipient_alias = extracted.get("recipient_alias")
    recipient_target = extracted.get("recipient_target")
    recipient_targets = extracted.get("recipient_targets") or []
    recipient_mode = extracted.get("recipient_mode")
    recipient_explicit_name = bool(extracted.get("recipient_explicit_name"))
    comparison_mode = extracted.get("comparison_mode")
    aggregation = extracted.get("aggregation")
    target_type = extracted.get("target_type")
    category_targets = extracted.get("category_targets") or ([] if category is None else [category])
    comparison_metric = None
    combine_mode = None
    rank_only = False

    if want_avg_ticket:
        aggregation = "avg_ticket"
        comparison_metric = "avg_ticket"

    if want_combined_sum:
        combine_mode = "sum"

    multiple_targets = (
        len(merchant_targets) >= 2 or len(category_targets) >= 2 or len(recipient_targets) >= 2
    )
    compare_between_targets = comparison_mode == "between_entities" or (
        multiple_targets
        and (
            _COMPARE_RE.search(t) is not None
            or re.search(r"\b(що\s+більше|що\s+менше|хто\s+більше|хто\s+менше)\b", t) is not None
        )
    )
    compare_spend_bases = (
        _COMPARE_RE.search(t) is not None
        and _REAL_SPEND_RE.search(t) is not None
        and _SPEND_BASE_COMPARE_RE.search(t) is not None
    )

    if _INCOME_COUNT_OVERRIDE_RE.search(t):
        if intent in ("income_sum", "income_count"):
            intent = "income_count"

    if _TRANSFER_COUNT_OVERRIDE_RE.search(t):
        if intent in ("transfer_in_sum", "transfer_in_count"):
            intent = "transfer_in_count"
        elif intent in ("transfer_out_sum", "transfer_out_count"):
            intent = "transfer_out_count"

    if comparison_mode == "baseline":
        intent = "compare_to_baseline"
    elif want_top_growth:
        intent = "top_growth_categories"
    elif want_top_decline:
        intent = "top_decline_categories"
    elif comparison_mode == "previous_period":
        intent = "compare_to_previous_period"
    elif compare_spend_bases:
        intent = "compare_spend_bases"
    elif compare_between_targets:
        intent = "between_entities"
        comparison_mode = "between_entities"
        if comparison_metric is None:
            comparison_metric = "count" if is_count else "sum"
    elif multiple_targets and combine_mode == "sum":
        intent = "between_entities"
        comparison_mode = "between_entities"
        comparison_metric = "sum"
    elif want_summary_short:
        intent = "spend_summary_short"
    elif want_insights_three:
        intent = "spend_insights_three"
    elif want_unusual:
        intent = "spend_unusual_summary"
    elif want_last_time:
        intent = "last_time"
    elif want_recurrence:
        intent = "recurrence_summary"
    elif want_top_merchants:
        intent = "top_merchants"
        rank_only = rank_position is not None
        if want_combined_sum:
            combine_mode = "top_sum"
    elif want_top_categories:
        intent = "top_categories"
        rank_only = rank_position is not None
        if want_combined_sum:
            combine_mode = "top_sum"
    elif want_share and category is not None:
        intent = "category_share"
    elif want_top_growth:
        intent = "top_growth_categories"
    elif want_top_decline:
        intent = "top_decline_categories"
    elif want_explain_growth:
        intent = "explain_growth"
    elif want_avg_ticket and (merchant or category is not None):
        intent = "spend_sum"
        aggregation = "avg_ticket"
    elif (
        direction == "more_than"
        and threshold_uah is not None
        and (is_count or aggregation == "count" or str(intent or "").endswith("_count"))
    ):
        intent = "count_over"
    elif (
        direction == "less_than"
        and threshold_uah is not None
        and (is_count or aggregation == "count" or str(intent or "").endswith("_count"))
    ):
        intent = "count_under"
    elif direction is not None and threshold_uah is not None:
        intent = "threshold_query"

    llm_candidate = False
    slots_confidence = "high"

    if _is_open_ended_finance_question(text):
        llm_candidate = True
        slots_confidence = "low"

    if intent in {"unsupported", None}:
        llm_candidate = True
        slots_confidence = "low"

    if intent in {"transfer_out_sum", "transfer_out_count", "transfer_in_sum", "transfer_in_count"}:
        if recipient_mode in {"generic", "explicit"}:
            slots_confidence = "medium"

    return {
        "intent": intent,
        "days": days,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "merchant_contains": merchant,
        "merchant_targets": merchant_targets,
        "merchant_exact": merchant_exact,
        "recipient_alias": recipient_alias,
        "recipient_target": recipient_target,
        "recipient_targets": recipient_targets,
        "recipient_mode": recipient_mode,
        "recipient_explicit_name": recipient_explicit_name,
        "period_label": period_label,
        "category": category,
        "category_targets": category_targets,
        "entity_kind": entity_kind,
        "threshold_uah": threshold_uah,
        "direction": direction,
        "comparison_mode": comparison_mode,
        "comparison_metric": comparison_metric,
        "aggregation": aggregation,
        "target_type": target_type,
        "count_scope": count_scope,
        "spend_basis": spend_basis,
        "combine_mode": combine_mode,
        "rank_position": rank_position if intent in {"top_categories", "top_merchants"} else None,
        "rank_only": rank_only,
        "slots_confidence": slots_confidence,
        "llm_candidate": llm_candidate,
        "top_n": _extract_top_n(t) if intent in {"top_categories", "top_merchants"} else None,
    }


def route(req: NLQRequest) -> NLQIntent | None:
    parsed = parse_nlq_intent(req.text, req.now_ts)
    if not parsed or parsed.get("intent") in (None, "unsupported"):
        return None

    query_intent = QueryIntent(
        name=str(parsed["intent"]),
        family=canonical_intent_family(parsed.get("intent")),
    )
    payload = Slots(parsed).to_payload()
    return NLQIntent(name=query_intent.name, slots=payload)
