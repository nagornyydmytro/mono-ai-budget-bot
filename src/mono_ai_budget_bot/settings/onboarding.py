from __future__ import annotations

from typing import Any, Literal

ActivityMode = Literal["loud", "quiet", "custom"]
UncatPromptFrequency = Literal["immediate", "daily", "weekly", "before_report"]
Persona = Literal["supportive", "rational", "motivator"]


def apply_onboarding_settings(
    profile: dict[str, Any],
    *,
    activity_mode: ActivityMode | None = None,
    uncategorized_prompt_frequency: UncatPromptFrequency | None = None,
    persona: Persona | None = None,
) -> dict[str, Any]:
    out = dict(profile)

    if activity_mode is not None:
        if activity_mode not in ("loud", "quiet", "custom"):
            raise ValueError("invalid activity_mode")
        out["activity_mode"] = activity_mode

    if uncategorized_prompt_frequency is not None:
        if uncategorized_prompt_frequency not in ("immediate", "daily", "weekly", "before_report"):
            raise ValueError("invalid uncategorized_prompt_frequency")
        out["uncategorized_prompt_frequency"] = uncategorized_prompt_frequency

    if persona is not None:
        if persona not in ("supportive", "rational", "motivator"):
            raise ValueError("invalid persona")
        out["persona"] = persona

    return out
