from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mono_ai_budget_bot.storage.tx_store import TxRecord
from mono_ai_budget_bot.taxonomy.pipeline import categorize_tx
from mono_ai_budget_bot.taxonomy.rules import Rule


@dataclass(frozen=True)
class UncatItem:
    tx_id: str
    time: int
    account_id: str
    amount: int
    description: str
    mcc: int | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "tx_id": self.tx_id,
            "time": self.time,
            "account_id": self.account_id,
            "amount": self.amount,
            "description": self.description,
            "mcc": self.mcc,
            "reason": self.reason,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "UncatItem":
        return UncatItem(
            tx_id=str(d.get("tx_id") or ""),
            time=int(d.get("time") or 0),
            account_id=str(d.get("account_id") or ""),
            amount=int(d.get("amount") or 0),
            description=str(d.get("description") or ""),
            mcc=(int(d["mcc"]) if d.get("mcc") is not None else None),
            reason=str(d.get("reason") or ""),
        )


def build_uncat_queue(
    *,
    tax: dict[str, Any],
    records: list[TxRecord],
    rules: list[Rule] | None = None,
    limit: int = 200,
) -> list[UncatItem]:
    items: list[UncatItem] = []
    seen: set[str] = set()

    for tx in sorted(records, key=lambda r: r.time, reverse=True):
        if tx.id in seen:
            continue
        seen.add(tx.id)

        out = categorize_tx(
            tax=tax,
            tx=tx,
            rules=(rules or []),
            override_leaf_id=None,
            alias_categories=None,
        )

        if out.bucket != "needs_clarify":
            continue
        if out.reason != "purchase_without_rule":
            continue

        items.append(
            UncatItem(
                tx_id=tx.id,
                time=tx.time,
                account_id=tx.account_id,
                amount=tx.amount,
                description=tx.description,
                mcc=tx.mcc,
                reason=out.reason,
            )
        )

        if len(items) >= int(limit):
            break

    return items
