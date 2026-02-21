from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .client import MonobankClient
from ..monobank.models import MonoAccount, MonoStatementItem


@dataclass(frozen=True)
class AccountStatement:
    account_id: str
    items: list[MonoStatementItem]


def fetch_statements_for_accounts(
    mb: MonobankClient,
    accounts: Iterable[MonoAccount],
    date_from: int,
    date_to: int,
) -> list[AccountStatement]:
    merged: list[AccountStatement] = []

    for acc in accounts:
        items = mb.statement(account=acc.id, date_from=date_from, date_to=date_to)
        merged.append(AccountStatement(account_id=acc.id, items=items))

    return merged