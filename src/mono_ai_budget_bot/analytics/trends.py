from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .categories import category_from_mcc

try:
    from .anomalies import _norm_merchant  # type: ignore
except Exception:  # pragma: no cover
    _norm_merchant = None  # type: ignore


@dataclass(frozen=True)
class TrendItem:
    kind: str
    label: str
    delta_uah: float
    pct: float | None
    cur_uah: float
    prev_uah: float
    active_days_cur: int
    active_days_prev: int


def _pct_change(cur: float, prev: float) -> float | None:
    if prev <= 0:
        return None
    return round(((cur - prev) / prev) * 100.0, 2)


def _get_ts(r: Any) -> int:
    if hasattr(r, "ts"):
        return int(r.ts)
    return int(r.time)


def _get_kind(r: Any) -> str:
    if hasattr(r, "kind"):
        return str(r.kind)
    amt = int(getattr(r, "amount", 0))
    if amt > 0:
        return "income"
    if amt < 0:
        return "spend"
    return "other"


def _get_amount_minor(r: Any) -> int:
    return abs(int(getattr(r, "amount", 0)))


def _merchant_label(desc: str) -> str:
    s = (desc or "").strip()
    if _norm_merchant is not None:
        out = _norm_merchant(s)
        return out or "unknown"
    s = " ".join(s.lower().split())
    return s[:48] if s else "unknown"


def _sum_by_label(
    rows: list[Any],
    start_ts: int,
    end_ts: int,
    label_fn: Callable[[Any], str],
) -> tuple[dict[str, int], dict[str, set[int]]]:
    totals: dict[str, int] = {}
    days: dict[str, set[int]] = {}

    for r in rows:
        t = _get_ts(r)
        if not (start_ts <= t < end_ts):
            continue

        if _get_kind(r) != "spend":
            continue

        label = label_fn(r) or "unknown"
        if label == "unknown":
            continue

        cents = _get_amount_minor(r)
        totals[label] = totals.get(label, 0) + cents
        days.setdefault(label, set()).add(t // 86400)

    return totals, days


def _build_items(
    kind: str,
    cur: dict[str, int],
    prev: dict[str, int],
    days_cur: dict[str, set[int]],
    days_prev: dict[str, set[int]],
    *,
    min_prev_uah: float,
    min_abs_delta_uah: float,
    min_active_days: int,
) -> list[TrendItem]:
    labels = set(cur.keys()) | set(prev.keys())
    out: list[TrendItem] = []

    for lab in labels:
        cur_uah = round(cur.get(lab, 0) / 100.0, 2)
        prev_uah = round(prev.get(lab, 0) / 100.0, 2)
        delta = round(cur_uah - prev_uah, 2)

        if prev_uah < min_prev_uah and cur_uah < min_prev_uah:
            continue
        if abs(delta) < min_abs_delta_uah:
            continue

        ad_cur = len(days_cur.get(lab, set()))
        ad_prev = len(days_prev.get(lab, set()))
        if max(ad_cur, ad_prev) < min_active_days:
            continue

        out.append(
            TrendItem(
                kind=kind,
                label=lab,
                delta_uah=delta,
                pct=_pct_change(cur_uah, prev_uah),
                cur_uah=cur_uah,
                prev_uah=prev_uah,
                active_days_cur=ad_cur,
                active_days_prev=ad_prev,
            )
        )

    return out


def compute_trends(
    rows: list[Any],
    now_ts: int,
    *,
    window_days: int = 7,
    min_prev_uah: float = 200.0,
    min_abs_delta_uah: float = 150.0,
    min_active_days: int = 2,
) -> dict[str, list[dict[str, Any]]]:
    now_ts = int(now_ts)
    w = max(3, min(int(window_days), 30))

    cur_start = now_ts - w * 86400
    prev_start = now_ts - 2 * w * 86400
    prev_end = cur_start

    cat_cur, cat_days_cur = _sum_by_label(
        rows,
        start_ts=cur_start,
        end_ts=now_ts,
        label_fn=lambda r: category_from_mcc(getattr(r, "mcc", None)) or "Інше",
    )
    cat_prev, cat_days_prev = _sum_by_label(
        rows,
        start_ts=prev_start,
        end_ts=prev_end,
        label_fn=lambda r: category_from_mcc(getattr(r, "mcc", None)) or "Інше",
    )

    mer_cur, mer_days_cur = _sum_by_label(
        rows,
        start_ts=cur_start,
        end_ts=now_ts,
        label_fn=lambda r: _merchant_label(getattr(r, "description", "")),
    )
    mer_prev, mer_days_prev = _sum_by_label(
        rows,
        start_ts=prev_start,
        end_ts=prev_end,
        label_fn=lambda r: _merchant_label(getattr(r, "description", "")),
    )

    cat_items = _build_items(
        "category",
        cat_cur,
        cat_prev,
        cat_days_cur,
        cat_days_prev,
        min_prev_uah=min_prev_uah,
        min_abs_delta_uah=min_abs_delta_uah,
        min_active_days=min_active_days,
    )
    mer_items = _build_items(
        "merchant",
        mer_cur,
        mer_prev,
        mer_days_cur,
        mer_days_prev,
        min_prev_uah=min_prev_uah,
        min_abs_delta_uah=min_abs_delta_uah,
        min_active_days=min_active_days,
    )

    all_items = [*cat_items, *mer_items]

    growing = sorted(
        [x for x in all_items if x.delta_uah > 0], key=lambda x: x.delta_uah, reverse=True
    )
    declining = sorted([x for x in all_items if x.delta_uah < 0], key=lambda x: x.delta_uah)

    def to_dict(x: TrendItem) -> dict[str, Any]:
        return {
            "kind": x.kind,
            "label": x.label,
            "delta_uah": x.delta_uah,
            "pct": x.pct,
            "cur_uah": x.cur_uah,
            "prev_uah": x.prev_uah,
            "active_days_cur": x.active_days_cur,
            "active_days_prev": x.active_days_prev,
        }

    return {
        "growing": [to_dict(x) for x in growing[:3]],
        "declining": [to_dict(x) for x in declining[:3]],
    }
