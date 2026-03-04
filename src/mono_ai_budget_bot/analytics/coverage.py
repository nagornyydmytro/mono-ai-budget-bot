from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class CoverageWindow:
    start_ts: int
    end_ts: int

    @property
    def days(self) -> int:
        return max(0, (self.end_ts - self.start_ts) // 86400)

    @property
    def start_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.start_ts, tz=timezone.utc)

    @property
    def end_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.end_ts, tz=timezone.utc)


def compute_coverage(timestamps: list[int]) -> CoverageWindow | None:
    if not timestamps:
        return None

    return CoverageWindow(
        start_ts=min(timestamps),
        end_ts=max(timestamps),
    )
