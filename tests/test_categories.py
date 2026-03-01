from __future__ import annotations

import pytest

from mono_ai_budget_bot.analytics.categories import (
    MCC_CATEGORY_FALLBACKS,
    MCC_CATEGORY_TABLE,
    category_from_mcc,
)


def test_category_from_mcc_none_and_unknown():
    assert category_from_mcc(None) is None
    assert category_from_mcc(999) is None


@pytest.mark.parametrize(
    ("mcc", "expected"),
    [
        (5814, "Кафе/Ресторани"),
        (5813, "Бари/Алкоголь"),
        (5411, "Маркет/Побут"),
        (5912, "Аптеки/Здоров'я"),
        (4111, "Транспорт"),
        (7011, "Подорожі"),
        (5734, "Розваги/Діджитал"),
        (4900, "Комунальні/Платежі"),
        (6011, "Фінансові послуги"),
        (5621, "Одяг/Взуття"),
    ],
)
def test_known_mccs_mapped_stably(mcc: int, expected: str):
    assert category_from_mcc(mcc) == expected


def test_all_table_mccs_roundtrip():
    for mcc, expected in MCC_CATEGORY_TABLE.items():
        assert category_from_mcc(mcc) == expected


def test_fallbacks_are_sorted_and_non_overlapping():
    assert MCC_CATEGORY_FALLBACKS, "fallbacks must not be empty"

    prev_end: int | None = None
    for r in MCC_CATEGORY_FALLBACKS:
        assert r.start <= r.end
        assert r.category.strip() != ""
        if prev_end is not None:
            assert r.start > prev_end
        prev_end = r.end
