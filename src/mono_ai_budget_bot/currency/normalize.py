from __future__ import annotations

from dataclasses import replace

from mono_ai_budget_bot.currency.models import MonoCurrencyRate
from mono_ai_budget_bot.storage.tx_store import TxRecord

UAH_CODE = 980


def _conservative_rate_to_uah(rate: MonoCurrencyRate) -> float | None:
    if rate.rateCross is not None:
        return float(rate.rateCross)

    rb = float(rate.rateBuy) if rate.rateBuy is not None else None
    rs = float(rate.rateSell) if rate.rateSell is not None else None

    if rb is not None and rs is not None:
        return min(rb, rs)
    if rb is not None:
        return rb
    if rs is not None:
        return rs
    return None


def _build_rate_map_to_uah(rates: list[MonoCurrencyRate]) -> dict[int, float]:
    out: dict[int, float] = {}
    for r in rates:
        if int(r.currencyCodeB) != UAH_CODE:
            continue
        code_a = int(r.currencyCodeA)
        k = _conservative_rate_to_uah(r)
        if k is None:
            continue
        out[code_a] = float(k)
    return out


def normalize_amount_to_uah_cents(
    amount_cents: int,
    *,
    currency_code: int | None,
    rates: list[MonoCurrencyRate],
) -> int:
    code = int(currency_code) if currency_code is not None else UAH_CODE
    if code == UAH_CODE:
        return int(amount_cents)

    rate_map = _build_rate_map_to_uah(rates)
    k = rate_map.get(code)
    if k is None:
        return int(amount_cents)

    return int(round(float(amount_cents) * float(k)))


def normalize_records_to_uah(
    records: list[TxRecord],
    rates: list[MonoCurrencyRate],
) -> list[TxRecord]:
    if not records:
        return []

    rate_map = _build_rate_map_to_uah(rates)
    if not rate_map:
        return list(records)

    out: list[TxRecord] = []
    for r in records:
        code = int(r.currencyCode) if r.currencyCode is not None else UAH_CODE
        if code == UAH_CODE:
            out.append(r)
            continue

        k = rate_map.get(code)
        if k is None:
            out.append(r)
            continue

        new_amount = int(round(float(r.amount) * float(k)))
        out.append(replace(r, amount=new_amount, currencyCode=UAH_CODE))

    return out
