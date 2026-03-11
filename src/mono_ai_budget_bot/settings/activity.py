from __future__ import annotations

from typing import Any, Literal

ActivityMode = Literal["loud", "quiet", "custom"]

ActivityToggleKey = Literal[
    "auto_reports",
    "uncat_prompts",
    "trends_alerts",
    "anomalies_alerts",
    "coach_nudges",
]

_ACTIVITY_KEYS: tuple[ActivityToggleKey, ...] = (
    "auto_reports",
    "uncat_prompts",
    "trends_alerts",
    "anomalies_alerts",
    "coach_nudges",
)


def default_activity_toggles(mode: ActivityMode) -> dict[ActivityToggleKey, bool]:
    if mode == "quiet":
        return {
            "auto_reports": False,
            "uncat_prompts": False,
            "trends_alerts": False,
            "anomalies_alerts": False,
            "coach_nudges": False,
        }

    if mode == "custom":
        return {
            "auto_reports": True,
            "uncat_prompts": True,
            "trends_alerts": False,
            "anomalies_alerts": False,
            "coach_nudges": False,
        }

    return {
        "auto_reports": True,
        "uncat_prompts": True,
        "trends_alerts": True,
        "anomalies_alerts": True,
        "coach_nudges": True,
    }


def _sanitize_toggle_map(raw: Any) -> dict[ActivityToggleKey, bool]:
    defaults = default_activity_toggles("custom")
    out: dict[ActivityToggleKey, bool] = {k: bool(defaults[k]) for k in _ACTIVITY_KEYS}
    if isinstance(raw, dict):
        for key in _ACTIVITY_KEYS:
            if key in raw:
                out[key] = bool(raw[key])
    return out


def normalize_activity_settings(profile: dict[str, Any]) -> dict[str, Any]:
    out = dict(profile)

    mode = str(out.get("activity_mode") or "").strip() or "custom"
    if mode not in ("loud", "quiet", "custom"):
        mode = "custom"

    act = out.get("activity")
    if not isinstance(act, dict):
        act = {}

    custom_toggles = _sanitize_toggle_map(
        act.get("custom_toggles")
        if isinstance(act.get("custom_toggles"), dict)
        else act.get("toggles"),
    )

    effective = (
        dict(custom_toggles)
        if mode == "custom"
        else {k: bool(v) for k, v in default_activity_toggles(mode).items()}
    )

    out["activity_mode"] = mode
    out["activity"] = {
        "mode": mode,
        "toggles": effective,
        "custom_toggles": dict(custom_toggles),
    }
    out.setdefault("activity_ui", {})
    return out


def get_activity_toggles(profile: dict[str, Any]) -> dict[ActivityToggleKey, bool]:
    prof = normalize_activity_settings(profile)
    activity = prof.get("activity")
    toggles = activity.get("toggles") if isinstance(activity, dict) else {}
    return _sanitize_toggle_map(toggles)


def is_activity_enabled(profile: dict[str, Any], key: ActivityToggleKey) -> bool:
    return bool(get_activity_toggles(profile).get(key, False))


def set_activity_mode(profile: dict[str, Any], mode: ActivityMode) -> dict[str, Any]:
    if mode not in ("loud", "quiet", "custom"):
        raise ValueError("invalid activity_mode")

    prof = normalize_activity_settings(profile)
    custom_toggles = _sanitize_toggle_map(prof.get("activity", {}).get("custom_toggles"))

    prof["activity_mode"] = mode
    prof["activity"] = {
        "mode": mode,
        "toggles": dict(custom_toggles) if mode == "custom" else default_activity_toggles(mode),
        "custom_toggles": dict(custom_toggles),
    }
    return normalize_activity_settings(prof)


def set_activity_toggle(
    profile: dict[str, Any],
    key: ActivityToggleKey,
    enabled: bool,
) -> dict[str, Any]:
    if key not in _ACTIVITY_KEYS:
        raise ValueError("invalid activity_toggle")

    prof = normalize_activity_settings(profile)
    custom_toggles = _sanitize_toggle_map(prof.get("activity", {}).get("custom_toggles"))
    custom_toggles[key] = bool(enabled)

    prof["activity_mode"] = "custom"
    prof["activity"] = {
        "mode": "custom",
        "toggles": dict(custom_toggles),
        "custom_toggles": dict(custom_toggles),
    }
    return normalize_activity_settings(prof)
