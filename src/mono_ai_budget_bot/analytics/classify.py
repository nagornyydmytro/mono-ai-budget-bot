from __future__ import annotations

from .models import TxKind

TRANSFER_MCC = {4829, 6536}


def is_transfer(mcc: int | None, description: str) -> bool:
    if mcc in TRANSFER_MCC:
        return True

    d = (description or "").lower()
    keywords = [
        "переказ",
        "перевод",
        "transfer",
        "card to card",
        "p2p",
    ]
    return any(k in d for k in keywords)


def classify_kind(amount: int, mcc: int | None, description: str) -> TxKind:
    """
    amount: negative = money out, positive = money in
    """
    if is_transfer(mcc, description):
        return "transfer_out" if amount < 0 else "transfer_in"
    return "spend" if amount < 0 else "income"
