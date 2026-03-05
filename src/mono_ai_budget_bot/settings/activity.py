from __future__ import annotations

from typing import Any, Literal

ActivityMode = Literal["loud", "quiet", "custom"]

ActivityToggleKey = Literal[
    "auto_reports",
    "uncat_prompts",
    "trends_alerts",
    "anomalies_alerts",
    "forecast_alerts",
    "coach_nudges",
]


def default_activity_toggles(mode: ActivityMode) -> dict[ActivityToggleKey, bool]:
    if mode == "quiet":
        return {
            "auto_reports": False,
            "uncat_prompts": False,
            "trends_alerts": False,
            "anomalies_alerts": False,
            "forecast_alerts": False,
            "coach_nudges": False,
        }

    if mode == "custom":
        return {
            "auto_reports": True,
            "uncat_prompts": True,
            "trends_alerts": False,
            "anomalies_alerts": False,
            "forecast_alerts": False,
            "coach_nudges": False,
        }

    return {
        "auto_reports": True,
        "uncat_prompts": True,
        "trends_alerts": True,
        "anomalies_alerts": True,
        "forecast_alerts": True,
        "coach_nudges": True,
    }


def normalize_activity_settings(profile: dict[str, Any]) -> dict[str, Any]:
    out = dict(profile)

    mode = str(out.get("activity_mode") or "").strip() or "custom"
    if mode not in ("loud", "quiet", "custom"):
        mode = "custom"

    act = out.get("activity")
    if not isinstance(act, dict):
        act = {}

    toggles_raw = act.get("toggles")
    toggles: dict[str, bool] = {}
    if isinstance(toggles_raw, dict):
        for k, v in toggles_raw.items():
            if isinstance(k, str):
                toggles[k] = bool(v)

    defaults = default_activity_toggles(mode)
    merged: dict[str, bool] = {k: bool(defaults[k]) for k in defaults}
    for k in defaults:
        if k in toggles:
            merged[k] = bool(toggles[k])

    out["activity_mode"] = mode
    out["activity"] = {"mode": mode, "toggles": merged}
    out.setdefault("activity_ui", {})
    return out
