from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from mono_ai_budget_bot.analytics.categories import category_from_mcc
from mono_ai_budget_bot.analytics.normalization import normalize_merchant
from mono_ai_budget_bot.storage.tx_store import TxRecord


@dataclass(frozen=True)
class TablePage:
    title: str
    lines: list[str]
    has_more: bool


def _fmt_uah(cents: int) -> str:
    return f"{cents/100:.2f} ₴"


def _top_merchants(rows: Iterable[TxRecord]) -> list[tuple[str, int, int]]:
    acc: dict[str, tuple[int, int]] = {}
    for r in rows:
        desc = normalize_merchant(r.description or "")
        cents = -int(r.amount)
        prev = acc.get(desc)
        if prev is None:
            acc[desc] = (cents, 1)
        else:
            acc[desc] = (prev[0] + cents, prev[1] + 1)

    items = [(k, v[0], v[1]) for k, v in acc.items() if v[0] > 0]
    items.sort(key=lambda x: x[1], reverse=True)
    return items


def _top_categories(rows: Iterable[TxRecord]) -> list[tuple[str, int, int]]:
    acc: dict[str, tuple[int, int]] = {}
    for r in rows:
        cat = category_from_mcc(r.mcc)
        cents = -int(r.amount)
        prev = acc.get(cat)
        if prev is None:
            acc[cat] = (cents, 1)
        else:
            acc[cat] = (prev[0] + cents, prev[1] + 1)

    items = [(k, v[0], v[1]) for k, v in acc.items() if v[0] > 0]
    items.sort(key=lambda x: x[1], reverse=True)
    return items


def render_top_merchants(
    rows: list[TxRecord],
    page: int,
    page_size: int = 5,
    title: str = "Топ мерчанти",
) -> TablePage:
    items = _top_merchants(rows)
    return _render_ranked(title, items, page=page, page_size=page_size)


def render_top_categories(
    rows: list[TxRecord],
    page: int,
    page_size: int = 5,
    title: str = "Топ категорії",
) -> TablePage:
    items = _top_categories(rows)
    return _render_ranked(title, items, page=page, page_size=page_size)


def _render_ranked(
    title: str,
    items: list[tuple[str, int, int]],
    *,
    page: int,
    page_size: int,
) -> TablePage:
    page = max(1, int(page))
    page_size = max(3, min(int(page_size), 10))

    start = (page - 1) * page_size
    end = start + page_size
    slice_items = items[start:end]
    has_more = end < len(items)

    lines: list[str] = []
    if not slice_items:
        return TablePage(title=title, lines=lines, has_more=False)

    for i, (name, cents, n) in enumerate(slice_items, start=start + 1):
        lines.append(f"{i}. {name}: {_fmt_uah(cents)} ({n})")

    return TablePage(title=title, lines=lines, has_more=has_more)


def suggest_merchant_candidates(rows: list[TxRecord], limit: int = 8) -> list[str]:
    limit = max(3, min(int(limit), 15))
    items = _top_merchants(rows)
    out: list[str] = []
    for name, _, _ in items[:limit]:
        if name and name != "unknown":
            out.append(name)
    return out
