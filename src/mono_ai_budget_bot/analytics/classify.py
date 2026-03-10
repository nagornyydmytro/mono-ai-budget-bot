from __future__ import annotations

from .models import TxKind

TRANSFER_MCC = {4829, 6536}
CASH_MOVEMENT_MCC = {6011}


def _looks_like_cash_movement(description: str) -> bool:
    d = (description or "").lower()
    keywords = [
        "банкомат",
        "atm",
        "cash withdrawal",
        "cash out",
        "withdrawal",
        "видача готівки",
        "зняття готівки",
    ]
    return any(k in d for k in keywords)


def is_transfer(mcc: int | None, description: str) -> bool:
    if mcc in TRANSFER_MCC:
        return True

    if mcc in CASH_MOVEMENT_MCC and _looks_like_cash_movement(description):
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
