from __future__ import annotations

from collections import Counter
from typing import Any

from .from_ledger import rows_from_ledger
from .compute import minor_to_uah


def build_user_profile(records: list) -> dict[str, Any]:
    rows = rows_from_ledger(records)

    if not rows:
        return {}

    spend_rows = [r for r in rows if r.direction == "spend"]

    total_spend_minor = sum(r.amount_minor for r in spend_rows)
    tx_count = len(spend_rows)

    avg_check = (
        minor_to_uah(total_spend_minor // tx_count) if tx_count > 0 else 0.0
    )

    cat_counter = Counter()
    merchant_counter = Counter()

    for r in spend_rows:
        cat_counter[r.category] += r.amount_minor
        merchant_counter[r.merchant] += r.amount_minor

    top_categories = [
        {"category": k, "amount_uah": minor_to_uah(v)}
        for k, v in cat_counter.most_common(5)
    ]

    top_merchants = [
        {"merchant": k, "amount_uah": minor_to_uah(v)}
        for k, v in merchant_counter.most_common(5)
    ]

    return {
        "avg_check_uah": avg_check,
        "total_spend_uah": minor_to_uah(total_spend_minor),
        "spend_tx_count": tx_count,
        "top_categories_long_term": top_categories,
        "top_merchants_long_term": top_merchants,
    }