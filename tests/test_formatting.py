from __future__ import annotations

import pytest

from mono_ai_budget_bot.bot import formatting


def test_format_decimal_2_snapshot():
    assert formatting.format_decimal_2(0.0) == "0.00"
    assert formatting.format_decimal_2(1.234) == "1.23"
    assert formatting.format_decimal_2(1.235) == "1.24"
    assert formatting.format_decimal2(9.9) == "9.90"


def test_format_money_uah_and_grn_snapshots():
    assert formatting.format_money_symbol_uah(0.0) == "0.00 ₴"
    assert formatting.format_money_uah(12.3) == "12.30 ₴"
    assert formatting.format_money_grn(12.3) == "12.30 грн"
    assert formatting.format_money_grn(9999.999) == "10000.00 грн"


def test_format_percent_signed_snapshots():
    assert formatting.format_percent_signed(0.0) == "0.0%"
    assert formatting.format_percent_signed(1.234) == "+1.2%"
    assert formatting.format_percent_signed(-1.234) == "-1.2%"
    assert formatting.format_percent_signed(12.345, decimals=2) == "+12.35%"
    assert formatting.format_percent_signed(-12.345, decimals=2) == "-12.35%"


def test_uah_from_minor_snapshot():
    assert formatting.uah_from_minor(0) == 0.0
    assert formatting.uah_from_minor(1) == 0.01
    assert formatting.uah_from_minor(10) == 0.10
    assert formatting.uah_from_minor(105) == 1.05
    assert formatting.uah_from_minor(-105) == -1.05


def test_format_ts_local_snapshot_if_zoneinfo_available():
    if formatting.ZoneInfo is None:
        pytest.skip("ZoneInfo not available in this environment")

    ts = 1768435200
    assert formatting.format_ts_local(ts, tz_name="Europe/Kyiv") == "2026-01-15 02:00"
