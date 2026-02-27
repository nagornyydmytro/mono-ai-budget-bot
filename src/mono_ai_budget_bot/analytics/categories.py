from __future__ import annotations

from typing import Optional

MCC_CATEGORY_RANGES: list[tuple[range, str]] = [
    (range(4000, 4800), "Транспорт"),
    (range(4800, 4900), "Фінансові послуги"),
    (range(5000, 5599), "Подорожі"),
    (range(5600, 5699), "Одяг/Взуття"),
    (range(5700, 5736), "Техніка/Електроніка"),
    (range(5737, 5800), "Розваги/Діджитал"),
    (range(5811, 5830), "Кафе/Ресторани"),
    (range(5200, 5312), "Маркет/Побут"),\
    (range(5313, 5399), "Маркет/Побут"),
    (range(5900, 5999), "Аптеки/Здоров'я"),
    (range(6000, 7300), "Послуги"),
    (range(7800, 8000), "Розваги/Ігри"),
    (range(8000, 9000), "Проф. послуги"),
]


def category_from_mcc(mcc: int | None) -> Optional[str]:
    if mcc is None:
        return None
    for r, name in MCC_CATEGORY_RANGES:
        if mcc in r:
            return name
    return "Інше"
