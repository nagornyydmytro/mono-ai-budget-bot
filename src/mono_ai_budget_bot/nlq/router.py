from __future__ import annotations

import re
import time
from typing import Any

from mono_ai_budget_bot.currency import parse_currency_conversion_query
from mono_ai_budget_bot.nlq.category_keywords import detect_category
from mono_ai_budget_bot.nlq.models import QueryIntent, Slots, canonical_intent_family
from mono_ai_budget_bot.nlq.periods import parse_period_range
from mono_ai_budget_bot.nlq.types import NLQIntent, NLQRequest

_DAYS_RE = re.compile(r"(\d{1,3})\s*(?:дн|днів|дня|days)\b", re.IGNORECASE)
_INCOME_RE = re.compile(
    r"\b(дох(ід|оди|одів)|поповнен\w*|зачислен\w*|пополнен\w*|top\s*up|income|депозит)\b",
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
    r"\b(топ-?\s*\d*\s*мерчант\w*|топ-?\s*\d*\s*merchant\w*|де\s+я\s+витратив\s+найбільше)\b",
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
    r"\b(на\s+що\s+я\s+найбільше|на\s+яку\s+категорію\s+я\s+витратив\s+найбільше|яка\s+категорія\s+найбільш\w*|топ-?\s*\d*\s*категор)",
    re.IGNORECASE,
)

_SHARE_RE = re.compile(
    r"\b(частка|доля|share|відсот(ок|ка|ки))\b",
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
    return 5


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
        elif re.search(r"\b(цього\s+місяця|этого\s+месяца|this\s+month)\b", t):
            period_label = "цей місяць"
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
    want_compare_baseline = _COMPARE_RE.search(t) is not None and _BASELINE_RE.search(t) is not None
    want_compare_previous = _PREVIOUS_PERIOD_RE.search(t) is not None and (
        _COMPARE_RE.search(t) is not None
        or re.search(r"\b(більш\w*|менш\w*|больше|меньше|higher|lower)\b", t) is not None
    )
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
    threshold_mode, threshold_uah = _parse_threshold_uah(t)
    real_spend_only = (
        re.search(r"\bреальн\w*\s+витрат\w*\b", t, flags=re.IGNORECASE) is not None
        or re.search(r"\breal\s+spend\b", t, flags=re.IGNORECASE) is not None
    )

    intent: str | None = None
    entity_kind = "spend"
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
        count_markers = [
            "транзакц",
            "операц",
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
        if any(mk in t for mk in count_markers) or is_count:
            intent = "spend_count"
        elif any(mk in t for mk in spend_sum_markers) or want_sum:
            intent = "spend_sum"
        else:
            intent = "unsupported"

    merchant: str | None = None
    merchant_prep: str | None = None
    merchant_exact = False

    parts: list[tuple[str, str]] = []
    for m in re.finditer(r"\b(на|у|в)\s+([^\?\.,!]+)", t, flags=re.IGNORECASE):
        prep = str(m.group(1) or "").strip().lower()
        cand = str(m.group(2) or "").strip()
        if cand:
            parts.append((prep, cand))

    if parts:
        merchant_prep, cand = parts[-1]
        cand = re.split(r"\b(ніж|чем|than)\b", cand, maxsplit=1, flags=re.IGNORECASE)[0].strip()

        if re.match(r"^(скільки|сколько|how\s+much|how\s+many)\b", cand, flags=re.IGNORECASE):
            if " на " in cand:
                cand = cand.split(" на ")[-1].strip()

        cand = _strip_period_tail(cand)
        cand = _strip_threshold_tail(cand)
        cand_category = detect_category(cand)

        category_driven_query = (
            want_top_categories or want_share or want_top_growth or want_top_decline
        )
        multi_merchant_query = (
            re.search(r"\b(?:або|or|чи)\b", cand, flags=re.IGNORECASE) is not None
        )

        if cand and not re.search(r"\b(\d+%|\d+)\b", cand):
            if _is_non_merchant_prepositional_phrase(merchant_prep or "", cand):
                pass
            elif cand.startswith("яку категорію"):
                pass
            elif category_driven_query and cand_category is not None:
                pass
            else:
                explicit_merchant = _looks_like_explicit_merchant(merchant_prep or "", cand)

                if explicit_merchant:
                    if not (category is not None and cand_category == category):
                        merchant = cand
                        merchant_exact = not multi_merchant_query
                elif not (category is not None and cand_category == category):
                    merchant = cand

    recipient_target = _extract_after_trigger(
        text,
        patterns=[
            r"\b(?:переказ(?:ав|ала|ував|увала|увати|ати)?|перев(?:ів|ела|ести)?|відправ(?:ив|ила|ити)?)\s+(.+?)(?:[?.!,]|$)",
        ],
    )
    recipient_mode = None
    recipient_alias = None
    recipient_explicit_name = False

    if recipient_target:
        recipient_alias = recipient_target.lower()
        if _looks_like_person_name(recipient_target):
            recipient_mode = "explicit"
            recipient_explicit_name = True
        elif _RECIPIENT_ALIAS_RE.search(recipient_alias):
            recipient_mode = "generic"
        else:
            recipient_mode = "explicit"
            recipient_explicit_name = True

    if _INCOME_COUNT_OVERRIDE_RE.search(t):
        if intent in ("income_sum", "income_count"):
            intent = "income_count"

    if _TRANSFER_COUNT_OVERRIDE_RE.search(t):
        if intent in ("transfer_in_sum", "transfer_in_count"):
            intent = "transfer_in_count"
        elif intent in ("transfer_out_sum", "transfer_out_count"):
            intent = "transfer_out_count"

    if want_compare_baseline:
        intent = "compare_to_baseline"
    elif want_top_growth:
        intent = "top_growth_categories"
    elif want_top_decline:
        intent = "top_decline_categories"
    elif want_compare_previous:
        intent = "compare_to_previous_period"
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
    elif want_top_categories:
        intent = "top_categories"
    elif want_share and category is not None:
        intent = "category_share"
    elif want_top_growth:
        intent = "top_growth_categories"
    elif want_top_decline:
        intent = "top_decline_categories"
    elif want_explain_growth:
        intent = "explain_growth"
    elif (
        threshold_mode == "over"
        and threshold_uah is not None
        and (is_count or str(intent or "").endswith("_count"))
    ):
        intent = "count_over"
    elif (
        threshold_mode == "under"
        and threshold_uah is not None
        and (is_count or str(intent or "").endswith("_count"))
    ):
        intent = "count_under"
    elif threshold_mode is not None and threshold_uah is not None:
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
        if recipient_mode == "generic":
            slots_confidence = "medium"
        elif recipient_mode == "explicit":
            slots_confidence = "medium"

    return {
        "intent": intent,
        "days": days,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "merchant_contains": merchant,
        "merchant_exact": merchant_exact,
        "recipient_alias": recipient_alias,
        "recipient_target": recipient_target,
        "recipient_mode": recipient_mode,
        "recipient_explicit_name": recipient_explicit_name,
        "period_label": period_label,
        "category": category,
        "entity_kind": entity_kind,
        "threshold_uah": threshold_uah,
        "spend_basis": "real" if real_spend_only else "gross",
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
