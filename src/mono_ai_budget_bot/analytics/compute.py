from __future__ import annotations

from collections import defaultdict
from typing import Any

from .categories import category_from_mcc
from .models import TxRow


def minor_to_uah(value: int) -> float:
    return round(value / 100.0, 2)


def _shares(amounts_uah: dict[str, float], total_uah: float) -> dict[str, float]:
    if total_uah <= 0:
        return {k: 0.0 for k in amounts_uah.keys()}
    return {k: round((v / total_uah) * 100.0, 1) for k, v in amounts_uah.items()}


def compute_facts(rows: list[TxRow]) -> dict[str, Any]:
    tx_count = len(rows)

    spend_total = 0
    income_total = 0
    transfer_out_total = 0
    transfer_in_total = 0

    by_account = defaultdict(
        lambda: {"spend": 0, "income": 0, "transfer_out": 0, "transfer_in": 0, "count": 0}
    )

    merchant_spend = defaultdict(int)
    mcc_spend = defaultdict(int)

    category_real_spend = defaultdict(int)
    uncategorized_real_spend = 0

    for r in rows:
        by_account[r.account_id]["count"] += 1

        if r.kind == "spend":
            amt = abs(r.amount)
            spend_total += amt
            by_account[r.account_id]["spend"] += amt

            merchant_spend[r.description] += amt

            if r.mcc is not None:
                mcc_spend[str(r.mcc)] += amt

            cat = category_from_mcc(r.mcc)
            if cat is None:
                uncategorized_real_spend += amt
            else:
                category_real_spend[cat] += amt

        elif r.kind == "income":
            income_total += r.amount
            by_account[r.account_id]["income"] += r.amount

        elif r.kind == "transfer_out":
            amt = abs(r.amount)
            transfer_out_total += amt
            by_account[r.account_id]["transfer_out"] += amt

        elif r.kind == "transfer_in":
            transfer_in_total += r.amount
            by_account[r.account_id]["transfer_in"] += r.amount

    cash_out_total = spend_total + transfer_out_total
    real_spend_total = spend_total

    top_merchants = sorted(merchant_spend.items(), key=lambda x: x[1], reverse=True)[:10]
    top_mcc = sorted(mcc_spend.items(), key=lambda x: x[1], reverse=True)[:10]
    top_named_categories = sorted(category_real_spend.items(), key=lambda x: x[1], reverse=True)[
        :10
    ]

    categories_uah = {k: minor_to_uah(v) for k, v in sorted(category_real_spend.items())}
    real_spend_total_uah = minor_to_uah(real_spend_total)

    category_shares = _shares(categories_uah, real_spend_total_uah)

    top_merchants_uah = {k: minor_to_uah(v) for k, v in top_merchants}
    top_merchants_shares = _shares(top_merchants_uah, real_spend_total_uah)

    facts: dict[str, Any] = {
        "transactions_count": tx_count,
        "totals": {
            "income_total_uah": minor_to_uah(income_total),
            "spend_total_uah": minor_to_uah(cash_out_total),
            "transfer_in_total_uah": minor_to_uah(transfer_in_total),
            "transfer_out_total_uah": minor_to_uah(transfer_out_total),
            "real_spend_total_uah": real_spend_total_uah,
        },
        "category_method": "mcc",
        "categories_real_spend": categories_uah,
        "category_shares_real_spend": category_shares,
        "top_merchants_shares_real_spend": top_merchants_shares,
        "top_categories_named_real_spend": [
            {"category": k, "amount_uah": minor_to_uah(v)} for k, v in top_named_categories
        ],
        "uncategorized_real_spend_total_uah": minor_to_uah(uncategorized_real_spend),
        "top_merchants_real_spend": [
            {"merchant": k, "amount_uah": minor_to_uah(v)} for k, v in top_merchants
        ],
        "top_categories_real_spend": [
            {"mcc": k, "amount_uah": minor_to_uah(v)} for k, v in top_mcc
        ],
        "by_account": {
            acc_id: {
                "count": v["count"],
                "income_uah": minor_to_uah(v["income"]),
                "spend_uah": minor_to_uah(v["spend"]),
                "transfer_in_uah": minor_to_uah(v["transfer_in"]),
                "transfer_out_uah": minor_to_uah(v["transfer_out"]),
            }
            for acc_id, v in by_account.items()
        },
    }

    return facts
