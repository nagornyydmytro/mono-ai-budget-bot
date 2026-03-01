from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MccRange:
    start: int
    end: int
    category: str

    def contains(self, mcc: int) -> bool:
        return self.start <= mcc <= self.end


MCC_CATEGORY_TABLE: dict[int, str] = {
    # Food & drink
    5811: "Кафе/Ресторани",
    5812: "Кафе/Ресторани",
    5813: "Бари/Алкоголь",
    5814: "Кафе/Ресторани",
    5921: "Бари/Алкоголь",
    5462: "Маркет/Побут",  # bakeries
    5499: "Маркет/Побут",
    # Grocery / retail
    5411: "Маркет/Побут",
    5422: "Маркет/Побут",
    5441: "Маркет/Побут",
    5451: "Маркет/Побут",
    5311: "Маркет/Побут",
    5331: "Маркет/Побут",
    # Transport / travel
    4111: "Транспорт",
    4121: "Транспорт",
    4131: "Транспорт",
    4789: "Транспорт",
    5541: "Транспорт",
    5542: "Транспорт",
    3998: "Транспорт",
    4011: "Подорожі",
    4112: "Подорожі",
    4511: "Подорожі",
    4722: "Подорожі",
    7011: "Подорожі",
    7032: "Подорожі",
    # Health
    5912: "Аптеки/Здоров'я",
    8011: "Аптеки/Здоров'я",
    8021: "Аптеки/Здоров'я",
    8031: "Аптеки/Здоров'я",
    8041: "Аптеки/Здоров'я",
    8050: "Аптеки/Здоров'я",
    8062: "Аптеки/Здоров'я",
    8071: "Аптеки/Здоров'я",
    8099: "Аптеки/Здоров'я",
    # Digital / entertainment / subscriptions
    4899: "Розваги/Діджитал",
    5734: "Розваги/Діджитал",
    5815: "Розваги/Діджитал",
    5816: "Розваги/Діджитал",
    7832: "Розваги/Діджитал",
    7841: "Розваги/Діджитал",
    7994: "Розваги/Діджитал",
    7996: "Розваги/Діджитал",
    7997: "Розваги/Діджитал",
    7999: "Розваги/Діджитал",
    # Clothing / beauty
    5621: "Одяг/Взуття",
    5631: "Одяг/Взуття",
    5641: "Одяг/Взуття",
    5651: "Одяг/Взуття",
    5661: "Одяг/Взуття",
    5691: "Одяг/Взуття",
    5699: "Одяг/Взуття",
    5977: "Одяг/Взуття",
    7230: "Краса/Догляд",
    7298: "Краса/Догляд",
    # Finance / utilities / services
    4829: "Фінансові послуги",
    6011: "Фінансові послуги",
    6012: "Фінансові послуги",
    6051: "Фінансові послуги",
    4900: "Комунальні/Платежі",
    4812: "Комунальні/Платежі",
    4814: "Комунальні/Платежі",
}


MCC_CATEGORY_FALLBACKS: list[MccRange] = [
    MccRange(4000, 4799, "Транспорт"),
    MccRange(4800, 4899, "Фінансові послуги"),
    MccRange(4900, 4999, "Комунальні/Платежі"),
    MccRange(5000, 5199, "Подорожі"),
    MccRange(5200, 5499, "Маркет/Побут"),
    MccRange(5500, 5599, "Транспорт"),
    MccRange(5600, 5699, "Одяг/Взуття"),
    MccRange(5700, 5736, "Техніка/Електроніка"),
    MccRange(5737, 5809, "Розваги/Діджитал"),
    MccRange(5810, 5830, "Кафе/Ресторани"),
    MccRange(5900, 5999, "Аптеки/Здоров'я"),
    MccRange(6000, 7299, "Послуги"),
    MccRange(7300, 7999, "Послуги"),
    MccRange(8000, 8999, "Послуги"),
]


def _validate_fallbacks() -> None:
    prev_end: int | None = None
    for r in MCC_CATEGORY_FALLBACKS:
        if prev_end is not None and r.start <= prev_end:
            raise ValueError("MCC_CATEGORY_FALLBACKS overlap or unsorted")
        prev_end = r.end


_validate_fallbacks()


def category_from_mcc(mcc: int | None) -> Optional[str]:
    if mcc is None:
        return None

    try:
        m = int(mcc)
    except Exception:
        return None

    cat = MCC_CATEGORY_TABLE.get(m)
    if cat is not None:
        return cat

    for r in MCC_CATEGORY_FALLBACKS:
        if r.contains(m):
            return r.category

    return None
