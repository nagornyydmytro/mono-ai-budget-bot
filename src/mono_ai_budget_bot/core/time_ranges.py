from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

KYIV_TZ = ZoneInfo("Europe/Kyiv")

@dataclass(frozen=True)
class DateRange:
    dt_from: datetime
    dt_to: datetime

    def to_unix(self) -> tuple[int, int]:
        return int(self.dt_from.timestamp()), int(self.dt_to.timestamp())


def _floor_to_minute(dt: datetime) -> datetime:
    return dt.replace(second=0, microsecond=0)


def range_today() -> DateRange:
    now = datetime.now(tz=KYIV_TZ)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return DateRange(dt_from=start, dt_to=_floor_to_minute(now))


def range_last_days(days: int) -> DateRange:
    if days < 1:
        raise ValueError("days must be >= 1")
    now = datetime.now(tz=KYIV_TZ)
    end = _floor_to_minute(now)
    start_day = (now - timedelta(days=days)).date()
    start = datetime.combine(start_day, datetime.min.time(), tzinfo=KYIV_TZ)
    return DateRange(dt_from=start, dt_to=end)


def range_week() -> DateRange:
    return range_last_days(7)


def range_month() -> DateRange:
    return range_last_days(30)

def previous_period(dr: DateRange, days: int) -> DateRange:
    """
    Previous period with the same duration ending exactly at dr.dt_from.
    Example: current = [Feb 13 00:00 .. Feb 20 19:00], prev = [Feb 6 00:00 .. Feb 13 00:00]
    """
    prev_to = dr.dt_from
    prev_from = dr.dt_from - timedelta(days=days)
    return DateRange(dt_from=prev_from, dt_to=prev_to)