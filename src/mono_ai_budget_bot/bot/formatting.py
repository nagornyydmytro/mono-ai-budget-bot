from __future__ import annotations

from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None


def format_decimal_2(value: float) -> str:
    return f"{value:.2f}"


def format_decimal2(value: float) -> str:
    return format_decimal_2(value)


def format_money_symbol_uah(value: float) -> str:
    return f"{format_decimal_2(value)} ₴"


def format_money_uah(value: float) -> str:
    return format_money_symbol_uah(value)


def format_money_uah_pretty(value: float) -> str:
    return f"{value:,.2f} ₴".replace(",", " ")


def format_money_grn(value: float) -> str:
    return f"{format_decimal_2(value)} грн"


def format_percent_signed(value: float, *, decimals: int = 1) -> str:
    sign = "+" if value > 0 else ""
    spec = f"{{:{sign}.{decimals}f}}"
    return f"{spec.format(value)}%"


def format_ts_local(ts: int, *, tz_name: str = "Europe/Kyiv") -> str:
    if ZoneInfo is None:
        dt = datetime.fromtimestamp(ts)
    else:
        dt = datetime.fromtimestamp(ts, tz=ZoneInfo(tz_name))
    return dt.strftime("%Y-%m-%d %H:%M")


def uah_from_minor(amount_minor: int) -> float:
    return amount_minor / 100.0
