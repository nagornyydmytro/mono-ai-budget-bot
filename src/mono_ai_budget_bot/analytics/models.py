from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TxKind = Literal["income", "spend", "transfer_in", "transfer_out"]


@dataclass(frozen=True)
class TxRow:
    account_id: str
    ts: int
    amount: int  # in minor units (kopiyky)
    description: str
    mcc: int | None
    kind: TxKind
