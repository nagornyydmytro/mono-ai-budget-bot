from __future__ import annotations

from typing import Any, Literal

AIFeatureKey = Literal[
    "report_explanations",
    "ai_summaries",
    "ai_insights_wording",
    "semantic_fallback",
    "tool_mode",
]

_AI_FEATURE_KEYS: tuple[AIFeatureKey, ...] = (
    "report_explanations",
    "ai_summaries",
    "ai_insights_wording",
    "semantic_fallback",
    "tool_mode",
)

_DEFAULT_AI_FEATURES: dict[AIFeatureKey, bool] = {
    "report_explanations": True,
    "ai_summaries": True,
    "ai_insights_wording": True,
    "semantic_fallback": True,
    "tool_mode": True,
}


def default_ai_features() -> dict[AIFeatureKey, bool]:
    return dict(_DEFAULT_AI_FEATURES)


def normalize_ai_features_settings(profile: dict[str, Any]) -> dict[str, Any]:
    out = dict(profile)
    raw = out.get("ai_features")
    features = default_ai_features()
    if isinstance(raw, dict):
        for key in _AI_FEATURE_KEYS:
            if key in raw:
                features[key] = bool(raw[key])
    out["ai_features"] = features
    return out


def get_ai_features(profile: dict[str, Any]) -> dict[AIFeatureKey, bool]:
    prof = normalize_ai_features_settings(profile)
    raw = prof.get("ai_features")
    if not isinstance(raw, dict):
        return default_ai_features()
    return {key: bool(raw.get(key, _DEFAULT_AI_FEATURES[key])) for key in _AI_FEATURE_KEYS}


def ai_feature_enabled(profile: dict[str, Any], key: AIFeatureKey) -> bool:
    if key not in _AI_FEATURE_KEYS:
        raise ValueError("invalid ai feature key")
    return bool(get_ai_features(profile).get(key, False))


def set_ai_feature(profile: dict[str, Any], key: AIFeatureKey, enabled: bool) -> dict[str, Any]:
    if key not in _AI_FEATURE_KEYS:
        raise ValueError("invalid ai feature key")
    prof = normalize_ai_features_settings(profile)
    features = get_ai_features(prof)
    features[key] = bool(enabled)
    prof["ai_features"] = features
    return normalize_ai_features_settings(prof)


def reset_ai_features_settings(profile: dict[str, Any]) -> dict[str, Any]:
    prof = dict(profile)
    prof["ai_features"] = default_ai_features()
    return normalize_ai_features_settings(prof)


def ai_feature_label(key: str) -> str:
    return {
        "report_explanations": "AI explanations",
        "ai_summaries": "AI summaries",
        "ai_insights_wording": "AI insights wording",
        "semantic_fallback": "Semantic fallback",
        "tool_mode": "Planner / tool-mode",
    }.get(str(key or "").strip(), str(key or "").strip())


def render_ai_features_summary(profile: dict[str, Any]) -> str:
    features = get_ai_features(profile)
    lines: list[str] = []
    for key in _AI_FEATURE_KEYS:
        lines.append(f"{ai_feature_label(key)}: {'ON' if features[key] else 'OFF'}")
    return "\n".join(lines)


def compact_ai_features_label(profile: dict[str, Any]) -> str:
    features = get_ai_features(profile)
    return (
        "AI explanations ON"
        if bool(features.get("report_explanations", True))
        else "AI explanations OFF"
    )
