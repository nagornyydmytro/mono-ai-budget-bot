from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .categories import category_from_mcc
from .models import TxRow


@dataclass(frozen=True)
class WhatIfSuggestion:
    key: str
    title: str
    reduction_pct: int
    period_spend_uah: float
    monthly_spend_uah: float
    monthly_savings_uah: float


_ws_re = re.compile(r"\s+")
_strip_re = re.compile(r"[^\w\s'&+\-\.]")


def _norm(text: str) -> str:
    s = (text or "").strip().lower()
    s = _strip_re.sub(" ", s)
    s = _ws_re.sub(" ", s).strip()
    return s


def _sum_spend_uah(rows: list[TxRow], pred) -> float:
    total_minor = 0
    for r in rows:
        if r.kind != "spend":
            continue
        if pred(r):
            total_minor += abs(int(r.amount))
    return round(total_minor / 100.0, 2)


def _project_monthly(period_spend_uah: float, period_days: int) -> float:
    if period_days <= 0:
        return 0.0
    return round(period_spend_uah * (30.0 / float(period_days)), 2)


def build_whatif_suggestions(rows: list[TxRow], period_days: int) -> list[dict[str, Any]]:
    period_days = int(period_days)
    if period_days <= 0:
        return []

    taxi_kw = {"uber", "bolt", "uklon", "taxi", "такси", "таксі"}
    delivery_kw = {"glovo", "wolt", "raketa", "bolt food", "uber eats", "ubereats", "delivery"}

    taxi_spend = _sum_spend_uah(rows, lambda r: any(k in _norm(r.description) for k in taxi_kw))
    delivery_spend = _sum_spend_uah(
        rows, lambda r: any(k in _norm(r.description) for k in delivery_kw)
    )
    cafes_spend = _sum_spend_uah(
        rows,
        lambda r: (category_from_mcc(r.mcc) or "Інше") == "Кафе/Ресторани",
    )

    candidates: list[WhatIfSuggestion] = []

    def add_candidate(key: str, title: str, pct: int, spend: float, min_monthly: float) -> None:
        monthly = _project_monthly(spend, period_days)
        savings = round(monthly * (pct / 100.0), 2)
        if monthly >= min_monthly and savings >= 100.0:
            candidates.append(
                WhatIfSuggestion(
                    key=key,
                    title=title,
                    reduction_pct=pct,
                    period_spend_uah=round(spend, 2),
                    monthly_spend_uah=monthly,
                    monthly_savings_uah=savings,
                )
            )

    add_candidate("taxi", "Таксі", 20, taxi_spend, min_monthly=400.0)
    add_candidate("delivery", "Доставка", 20, delivery_spend, min_monthly=350.0)
    add_candidate("cafes", "Кафе/Ресторани", 10, cafes_spend, min_monthly=600.0)

    candidates.sort(key=lambda x: x.monthly_savings_uah, reverse=True)

    out: list[dict[str, Any]] = []
    for s in candidates[:2]:
        out.append(
            {
                "key": s.key,
                "title": s.title,
                "reduction_pct": s.reduction_pct,
                "period_spend_uah": s.period_spend_uah,
                "monthly_spend_uah": s.monthly_spend_uah,
                "monthly_savings_uah": s.monthly_savings_uah,
            }
        )
    return out
