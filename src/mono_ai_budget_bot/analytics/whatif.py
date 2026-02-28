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


def scenario_presets(share_pct: float | None = None) -> list[int]:
    if share_pct is None:
        return [10, 20]
    if share_pct >= 30.0:
        return [15, 25]
    return [10, 20]


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


def _build_keyword_suggestions(rows: list[TxRow], period_days: int) -> list[dict[str, Any]]:
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

    out: list[dict[str, Any]] = []

    def maybe_add(key: str, title: str, spend: float, min_monthly: float) -> None:
        monthly = _project_monthly(spend, period_days)
        if monthly < min_monthly:
            return

        presets = scenario_presets(None)
        scenarios: list[dict[str, Any]] = []
        for p in presets:
            sp = project_savings(monthly, reduce_pct=p)
            if sp.monthly_savings_uah < 100.0:
                continue
            scenarios.append(
                {
                    "pct": p,
                    "monthly_savings_uah": sp.monthly_savings_uah,
                    "projected_monthly_uah": sp.projected_monthly_uah,
                }
            )

        if not scenarios:
            return

        out.append(
            {
                "key": key,
                "title": title,
                "monthly_spend_uah": round(monthly, 2),
                "source": "keyword",
                "scenarios": scenarios,
            }
        )

    maybe_add("taxi", "Таксі", taxi_spend, 400.0)
    maybe_add("delivery", "Доставка", delivery_spend, 350.0)
    maybe_add("cafes", "Кафе/Ресторани", cafes_spend, 600.0)

    def _top_savings_uah(s: dict) -> float:
        sc = s.get("scenarios")
        if not isinstance(sc, list) or not sc:
            return 0.0
        return float(max(float(x.get("monthly_savings_uah", 0.0)) for x in sc))

    out.sort(key=_top_savings_uah, reverse=True)
    return out


def build_whatif_suggestions(rows: list[TxRow], period_days: int) -> list[dict[str, Any]]:
    period_days = int(period_days)
    if period_days <= 0:
        return []

    suggestions: list[dict[str, Any]] = []
    suggestions.extend(_build_keyword_suggestions(rows, period_days))

    total_spend_minor = 0
    category_minor: dict[str, int] = {}
    category_days: dict[str, set[int]] = {}

    for r in rows:
        if r.kind != "spend":
            continue

        cents = abs(int(r.amount))
        total_spend_minor += cents

        cat = category_from_mcc(r.mcc) or "Інше"
        category_minor[cat] = category_minor.get(cat, 0) + cents

        day = int(r.ts) // 86400
        category_days.setdefault(cat, set()).add(day)

    if total_spend_minor == 0:

        def _top_savings_uah(s: dict) -> float:
            sc = s.get("scenarios")
            if not isinstance(sc, list) or not sc:
                return 0.0
            return float(max(float(x.get("monthly_savings_uah", 0.0)) for x in sc))

        suggestions.sort(key=_top_savings_uah, reverse=True)
        return suggestions[:3]

    existing_keys = {s.get("key") for s in suggestions}

    for cat, cents in category_minor.items():
        share = cents / total_spend_minor
        active_days = len(category_days.get(cat, set()))

        if share < 0.15:
            continue
        if active_days < 4:
            continue

        period_spend_uah = cents / 100.0
        monthly = _project_monthly(period_spend_uah, period_days)
        if monthly < 800.0:
            continue

        pct = 15 if share > 0.25 else 10
        proj = project_savings(monthly, reduce_pct=pct)
        if proj.monthly_savings_uah < 150.0:
            continue

        key = f"cat:{cat}"
        if key in existing_keys:
            continue

        share_pct = round(share * 100, 1)
        presets = scenario_presets(share_pct)
        scenarios: list[dict[str, Any]] = []
        for p in presets:
            sp = project_savings(monthly, reduce_pct=p)
            scenarios.append(
                {
                    "pct": p,
                    "monthly_savings_uah": sp.monthly_savings_uah,
                    "projected_monthly_uah": sp.projected_monthly_uah,
                }
            )

        suggestions.append(
            {
                "key": key,
                "title": cat,
                "monthly_spend_uah": proj.base_monthly_uah,
                "share": share_pct,
                "source": "category",
                "scenarios": scenarios,
            }
        )

    def _top_savings_uah(s: dict) -> float:
        sc = s.get("scenarios")
        if not isinstance(sc, list) or not sc:
            return 0.0
        best = 0.0
        for x in sc:
            v = float(x.get("monthly_savings_uah", 0.0))
            if v > best:
                best = v
        return best

    keyword = [s for s in suggestions if s.get("source") == "keyword"]
    category = [s for s in suggestions if s.get("source") != "keyword"]

    keyword.sort(key=_top_savings_uah, reverse=True)
    category.sort(key=_top_savings_uah, reverse=True)

    out: list[dict[str, Any]] = []
    out.extend(keyword[:2])
    out.extend(category)

    out.sort(key=_top_savings_uah, reverse=True)
    return out[:3]
