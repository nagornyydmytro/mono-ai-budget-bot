from __future__ import annotations

from ..storage.tx_store import TxRecord
from .classify import classify_kind
from .models import TxRow


def rows_from_ledger(records: list[TxRecord]) -> list[TxRow]:
    rows: list[TxRow] = []
    for r in records:
        desc = (r.description or "").strip()
        kind = classify_kind(amount=r.amount, mcc=r.mcc, description=desc)
        rows.append(
            TxRow(
                account_id=r.account_id,
                ts=r.time,
                amount=r.amount,
                description=desc,
                mcc=r.mcc,
                kind=kind,
            )
        )
    return rows
