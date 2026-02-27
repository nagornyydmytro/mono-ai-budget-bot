from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class PeriodRange:
    start_ts: int
    end_ts: int


_MONTHS = {
    "січень": 1,
    "сiчень": 1,
    "январь": 1,
    "january": 1,
    "лютий": 2,
    "февраль": 2,
    "february": 2,
    "березень": 3,
    "март": 3,
    "march": 3,
    "квітень": 4,
    "апрель": 4,
    "april": 4,
    "травень": 5,
    "май": 5,
    "may": 5,
    "червень": 6,
    "июнь": 6,
    "june": 6,
    "липень": 7,
    "июль": 7,
    "july": 7,
    "серпень": 8,
    "август": 8,
    "august": 8,
    "вересень": 9,
    "сентябрь": 9,
    "september": 9,
    "жовтень": 10,
    "октябрь": 10,
    "october": 10,
    "листопад": 11,
    "ноябрь": 11,
    "november": 11,
    "грудень": 12,
    "декабрь": 12,
    "december": 12,
}


def _utc_day_start(ts: int) -> int:
    dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
    d0 = datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)
    return int(d0.timestamp())


def _month_range_utc(year: int, month: int) -> PeriodRange:
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return PeriodRange(int(start.timestamp()), int(end.timestamp()))


def parse_period_range(text: str, now_ts: int) -> PeriodRange | None:
    s = (text or "").strip().lower()

    if not s:
        return None

    now_ts = int(now_ts)

    if re.search(r"\b(сьогодні|сегодня|today)\b", s):
        start = _utc_day_start(now_ts)
        return PeriodRange(start, now_ts)

    if re.search(r"\b(вчора|вчера|yesterday)\b", s):
        today0 = _utc_day_start(now_ts)
        return PeriodRange(today0 - 86400, today0)

    m = re.search(
        r"\b(за\s+останні\s+|за\s+последние\s+|last\s+)(\d{1,3})\s*(дн(і|ів)?|дней|days)\b", s
    )
    if m:
        n = int(m.group(2))
        end = now_ts
        start = end - n * 86400
        return PeriodRange(start, end)

    if re.search(r"\b(за\s+тиждень|за\s+неделю|last\s+week)\b", s):
        end = now_ts
        start = end - 7 * 86400
        return PeriodRange(start, end)

    if re.search(r"\b(за\s+минулий\s+місяць|за\s+прошлый\s+месяц|last\s+month)\b", s):
        dt = datetime.fromtimestamp(now_ts, tz=timezone.utc)
        y, mth = dt.year, dt.month
        if mth == 1:
            y -= 1
            mth = 12
        else:
            mth -= 1
        return _month_range_utc(y, mth)

    for name, month in _MONTHS.items():
        if re.search(rf"\bза\s+{re.escape(name)}\b", s):
            dt = datetime.fromtimestamp(now_ts, tz=timezone.utc)
            return _month_range_utc(dt.year, month)

    m2 = re.search(r"\bза\s+(\d{4})[-./](\d{1,2})\b", s)
    if m2:
        year = int(m2.group(1))
        month = int(m2.group(2))
        if 1 <= month <= 12:
            return _month_range_utc(year, month)

    return None
