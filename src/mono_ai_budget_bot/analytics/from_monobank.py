from __future__ import annotations

from .classify import classify_kind
from .models import TxRow
from ..monobank.models import MonoStatementItem


def rows_from_statement(account_id: str, items: list[MonoStatementItem]) -> list[TxRow]:
    rows: list[TxRow] = []
    for it in items:
        desc = (it.description or "").strip()
        kind = classify_kind(amount=it.amount, mcc=it.mcc, description=desc)
        rows.append(
            TxRow(
                account_id=account_id,
                ts=it.time,
                amount=it.amount,
                description=desc,
                mcc=it.mcc,
                kind=kind,
            )
        )
    return rows