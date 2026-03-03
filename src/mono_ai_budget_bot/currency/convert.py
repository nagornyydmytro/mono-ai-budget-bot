from __future__ import annotations

import re
from dataclasses import dataclass

from mono_ai_budget_bot.currency.models import MonoCurrencyRate

UAH_NUM = 980

_ALPHA_TO_NUM: dict[str, int] = {
    "UAH": 980,
    "USD": 840,
    "EUR": 978,
    "PLN": 985,
    "GBP": 826,
    "CHF": 756,
    "CZK": 203,
    "SEK": 752,
    "NOK": 578,
    "DKK": 208,
    "HUF": 348,
    "RON": 946,
    "BGN": 975,
    "TRY": 949,
    "CAD": 124,
    "AUD": 36,
    "JPY": 392,
    "CNY": 156,
    "CNH": 156,
    "INR": 356,
    "SGD": 702,
    "HKD": 344,
    "ILS": 376,
    "AED": 784,
    "SAR": 682,
    "THB": 764,
    "KRW": 410,
    "RUB": 643,
    "GEL": 981,
    "MDL": 498,
    "KZT": 398,
    "AZN": 944,
}

_SYM_TO_ALPHA: dict[str, str] = {
    "₴": "UAH",
    "$": "USD",
    "€": "EUR",
}

_NAME_TO_ALPHA: dict[str, str] = {
    "грн": "UAH",
    "гривн": "UAH",
    "hryv": "UAH",
    "uah": "UAH",
    "дол": "USD",
    "бакс": "USD",
    "usd": "USD",
    "евро": "EUR",
    "євро": "EUR",
    "eur": "EUR",
    "злот": "PLN",
    "pln": "PLN",
    "фунт": "GBP",
    "gbp": "GBP",
    "франк": "CHF",
    "chf": "CHF",
}

_AMOUNT_RE = re.compile(r"(?P<amt>\d+(?:[\.,]\d+)?)", re.IGNORECASE)
_CODE_RE = re.compile(r"\b([a-z]{3})\b", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedConversion:
    amount: float
    from_alpha: str
    to_alpha: str


def alpha_to_numeric(alpha: str) -> int | None:
    a = (alpha or "").strip().upper()
    return _ALPHA_TO_NUM.get(a)


def _alpha_from_token(tok: str) -> str | None:
    s = (tok or "").strip().lower()
    if not s:
        return None

    if s in _SYM_TO_ALPHA:
        return _SYM_TO_ALPHA[s]

    for k, v in _NAME_TO_ALPHA.items():
        if k in s:
            return v

    if len(s) == 3 and s.isalpha():
        return s.upper()

    return None


def parse_currency_conversion_query(text: str) -> ParsedConversion | None:
    t = (text or "").strip()
    if not t:
        return None

    m_amt = _AMOUNT_RE.search(t)
    if m_amt is None:
        return None

    amt_s = str(m_amt.group("amt")).replace(",", ".")
    try:
        amount = float(amt_s)
    except Exception:
        return None
    if amount <= 0:
        return None

    after = t[m_amt.end() :].strip()
    if not after:
        return None

    after_norm = after.replace("—", " ").replace("–", " ")

    parts = re.split(
        r"\bв\b|\bу\b|\bto\b|\bin\b|\binto\b|=>|->",
        after_norm,
        maxsplit=1,
        flags=re.IGNORECASE,
    )
    if len(parts) < 2:
        return None

    left = parts[0].strip()
    right = parts[1].strip()

    from_alpha = _alpha_from_token(left)
    to_alpha = _alpha_from_token(right)

    if from_alpha is None:
        m = _CODE_RE.search(left)
        if m:
            from_alpha = m.group(1).upper()

    if to_alpha is None:
        m = _CODE_RE.search(right)
        if m:
            to_alpha = m.group(1).upper()

    if not from_alpha or not to_alpha:
        return None

    return ParsedConversion(amount=amount, from_alpha=from_alpha, to_alpha=to_alpha)


def _rate_to_uah_conservative(r: MonoCurrencyRate) -> float | None:
    if r.rateCross is not None:
        return float(r.rateCross)

    rb = float(r.rateBuy) if r.rateBuy is not None else None
    rs = float(r.rateSell) if r.rateSell is not None else None

    if rb is not None and rs is not None:
        return min(rb, rs)
    if rb is not None:
        return rb
    if rs is not None:
        return rs
    return None


def _rate_to_uah_for_uah_to_foreign(r: MonoCurrencyRate) -> float | None:
    if r.rateCross is not None:
        return float(r.rateCross)

    rb = float(r.rateBuy) if r.rateBuy is not None else None
    rs = float(r.rateSell) if r.rateSell is not None else None

    if rb is not None and rs is not None:
        return max(rb, rs)
    if rb is not None:
        return rb
    if rs is not None:
        return rs
    return None


def convert_amount(
    amount: float,
    *,
    from_num: int,
    to_num: int,
    rates: list[MonoCurrencyRate],
) -> float | None:
    from_num = int(from_num)
    to_num = int(to_num)

    if from_num == to_num:
        return float(amount)

    rates_to_uah: dict[int, MonoCurrencyRate] = {}
    for r in rates:
        if int(r.currencyCodeB) != UAH_NUM:
            continue
        rates_to_uah[int(r.currencyCodeA)] = r

    if from_num == UAH_NUM:
        r = rates_to_uah.get(to_num)
        if r is None:
            return None
        k = _rate_to_uah_for_uah_to_foreign(r)
        if k is None or k <= 0:
            return None
        return float(amount) / float(k)

    if to_num == UAH_NUM:
        r = rates_to_uah.get(from_num)
        if r is None:
            return None
        k = _rate_to_uah_conservative(r)
        if k is None:
            return None
        return float(amount) * float(k)

    r_from = rates_to_uah.get(from_num)
    r_to = rates_to_uah.get(to_num)
    if r_from is None or r_to is None:
        return None

    k_from = _rate_to_uah_conservative(r_from)
    k_to = _rate_to_uah_for_uah_to_foreign(r_to)
    if k_from is None or k_to is None or k_to <= 0:
        return None

    uah = float(amount) * float(k_from)
    return float(uah) / float(k_to)
