from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


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


class CoverageStatus(str, Enum):
    ok = "ok"
    partial = "partial"
    missing = "missing"


def compute_coverage(timestamps: list[int]) -> CoverageWindow | None:
    if not timestamps:
        return None

    return CoverageWindow(
        start_ts=min(timestamps),
        end_ts=max(timestamps),
    )


def classify_coverage(
    *,
    requested_from_ts: int,
    requested_to_ts: int,
    coverage_window: tuple[int, int] | None,
) -> CoverageStatus:
    if requested_to_ts < requested_from_ts:
        raise ValueError("requested_to_ts must be >= requested_from_ts")

    if coverage_window is None:
        return CoverageStatus.missing

    cov_from, cov_to = coverage_window

    if requested_to_ts < cov_from or requested_from_ts > cov_to:
        return CoverageStatus.missing

    if requested_from_ts >= cov_from and requested_to_ts <= cov_to:
        return CoverageStatus.ok

    return CoverageStatus.partial
