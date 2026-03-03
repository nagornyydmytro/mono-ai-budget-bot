from __future__ import annotations


def format_decimal_2(value: float) -> str:
    return f"{value:.2f}"


def format_money_symbol_uah(value: float) -> str:
    return f"{value:,.2f} ₴".replace(",", " ")


def format_money_grn(value: float) -> str:
    return f"{value:.2f} грн"


def uah_from_minor(amount_minor: int) -> float:
    return amount_minor / 100.0
