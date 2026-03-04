from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ReportPreset = Literal["min", "max", "custom"]


@dataclass(frozen=True)
class ReportsConfig:
    preset: ReportPreset
    daily: dict[str, bool]
    weekly: dict[str, bool]
    monthly: dict[str, bool]

    def to_dict(self) -> dict[str, Any]:
        return {
            "preset": self.preset,
            "daily": dict(self.daily),
            "weekly": dict(self.weekly),
            "monthly": dict(self.monthly),
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "ReportsConfig":
        preset = str(d.get("preset") or "min")
        if preset not in {"min", "max", "custom"}:
            preset = "min"

        def _m(key: str) -> dict[str, bool]:
            v = d.get(key)
            if not isinstance(v, dict):
                return {}
            out: dict[str, bool] = {}
            for k2, v2 in v.items():
                if isinstance(k2, str) and isinstance(v2, bool):
                    out[k2] = v2
            return out

        return ReportsConfig(
            preset=preset, daily=_m("daily"), weekly=_m("weekly"), monthly=_m("monthly")
        )

    def get_enabled_blocks(self, period: str) -> list[str]:
        if period == "daily":
            return [b for b, enabled in self.daily.items() if enabled]

        if period == "weekly":
            return [b for b, enabled in self.weekly.items() if enabled]

        if period == "monthly":
            return [b for b, enabled in self.monthly.items() if enabled]

        raise ValueError(f"Unknown report period: {period}")


def build_reports_preset(preset: ReportPreset) -> ReportsConfig:
    if preset == "custom":
        return ReportsConfig(preset="custom", daily={}, weekly={}, monthly={})

    if preset == "min":
        return ReportsConfig(
            preset="min",
            daily={"totals": True},
            weekly={"totals": True, "breakdowns": True, "compare_baseline": True},
            monthly={"totals": True, "breakdowns": True},
        )

    return ReportsConfig(
        preset="max",
        daily={"totals": True, "breakdowns": True},
        weekly={"totals": True, "breakdowns": True, "compare_baseline": True, "trends": True},
        monthly={
            "totals": True,
            "breakdowns": True,
            "trends": True,
            "anomalies": True,
            "what_if": True,
        },
    )
