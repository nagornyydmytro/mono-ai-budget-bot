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


def last_days(days: int) -> DateRange:
    now = datetime.now(tz=KYIV_TZ)
    dt_to = now
    dt_from = now - timedelta(days=days)
    return DateRange(dt_from=dt_from, dt_to=dt_to)