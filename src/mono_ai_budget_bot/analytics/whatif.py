from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .categories import category_from_mcc
from .models import TxRow


@dataclass(frozen=True)
class SavingsProjection:
    base_monthly_uah: float
    reduce_pct: int | None
    reduce_amount_uah: float | None
    projected_monthly_uah: float
    monthly_savings_uah: float


_ws_re = re.compile(r"\s+")
_strip_re = re.compile(r"[^\w\s'&+\-\.]")


def _norm(text: str) -> str:
    s = (text or "").strip().lower()
    s = _strip_re.sub(" ", s)
    s = _ws_re.sub(" ", s).strip()
    return s


def project_savings(
    base_monthly_uah: float,
    reduce_pct: int | None = None,
    reduce_amount_uah: float | None = None,
) -> SavingsProjection:
    base = max(float(base_monthly_uah), 0.0)

    if reduce_pct is not None and reduce_amount_uah is not None:
        raise ValueError("Specify either reduce_pct or reduce_amount_uah, not both")

    if reduce_pct is None and reduce_amount_uah is None:
        raise ValueError("One of reduce_pct or reduce_amount_uah must be provided")

    if reduce_pct is not None:
        pct = max(min(int(reduce_pct), 100), 0)
        savings = round(base * (pct / 100.0), 2)
        projected = round(base - savings, 2)
        return SavingsProjection(
            base_monthly_uah=round(base, 2),
            reduce_pct=pct,
            reduce_amount_uah=None,
            projected_monthly_uah=projected,
            monthly_savings_uah=savings,
        )

    amount = max(float(reduce_amount_uah), 0.0)
    savings = round(min(amount, base), 2)
    projected = round(base - savings, 2)

    return SavingsProjection(
        base_monthly_uah=round(base, 2),
        reduce_pct=None,
        reduce_amount_uah=round(amount, 2),
        projected_monthly_uah=projected,
        monthly_savings_uah=savings,
    )


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

    candidates: list[dict[str, Any]] = []

    def maybe_add(key: str, title: str, pct: int, spend: float, min_monthly: float) -> None:
        monthly = _project_monthly(spend, period_days)
        if monthly < min_monthly:
            return
        proj = project_savings(monthly, reduce_pct=pct)
        if proj.monthly_savings_uah < 100.0:
            return
        candidates.append(
            {
                "key": key,
                "title": title,
                "reduction_pct": pct,
                "monthly_spend_uah": proj.base_monthly_uah,
                "monthly_savings_uah": proj.monthly_savings_uah,
                "projected_monthly_uah": proj.projected_monthly_uah,
            }
        )

    maybe_add("taxi", "Таксі", 20, taxi_spend, 400.0)
    maybe_add("delivery", "Доставка", 20, delivery_spend, 350.0)
    maybe_add("cafes", "Кафе/Ресторани", 10, cafes_spend, 600.0)

    candidates.sort(key=lambda x: x["monthly_savings_uah"], reverse=True)
    return candidates[:2]
