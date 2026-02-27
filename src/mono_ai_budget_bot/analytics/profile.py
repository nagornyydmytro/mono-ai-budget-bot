from __future__ import annotations

from typing import Any

from .compute import compute_facts
from .from_ledger import rows_from_ledger


def _top5_from_amount_map(d: dict[str, float]) -> list[dict[str, Any]]:
    items = sorted(d.items(), key=lambda kv: kv[1], reverse=True)[:5]
    return [{"name": k, "amount_uah": float(v)} for k, v in items]


def build_user_profile(records: list) -> dict[str, Any]:
    """
    Lightweight profile derived from computed facts (robust to TxRow internals).
    Uses long-term ledger slice (e.g. last 90 days).
    """
    rows = rows_from_ledger(records)
    if not rows:
        return {}

    facts = compute_facts(rows)

    totals = facts.get("totals", {}) or {}

    real_spend_total_uah = float(totals.get("real_spend_total_uah", 0.0) or 0.0)

    spend_tx_count = int(facts.get("real_spend_tx_count") or facts.get("spend_tx_count") or totals.get("spend_tx_count") or 0)
    if spend_tx_count <= 0:
        spend_tx_count = max(0, int(facts.get("tx_count") or 0))

    avg_check_uah = round(real_spend_total_uah / spend_tx_count, 2) if spend_tx_count > 0 else 0.0

    categories = facts.get("categories_real_spend", {}) or {}
    merchants = facts.get("merchants_real_spend", {}) or {}

    return {
        "avg_check_uah": avg_check_uah,
        "total_real_spend_uah": real_spend_total_uah,
        "real_spend_tx_count": spend_tx_count,
        "top_categories_long_term": _top5_from_amount_map(categories),
        "top_merchants_long_term": _top5_from_amount_map(merchants),
    }