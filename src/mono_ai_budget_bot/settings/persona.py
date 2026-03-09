from __future__ import annotations

from typing import Any, Literal

PersonaStyle = Literal["supportive", "rational", "motivator"]
PersonaVerbosity = Literal["concise", "balanced", "detailed"]
PersonaMotivation = Literal["soft", "balanced", "strong"]
PersonaEmoji = Literal["minimal", "normal"]

_STYLE_VALUES: tuple[PersonaStyle, ...] = ("supportive", "rational", "motivator")
_VERBOSITY_VALUES: tuple[PersonaVerbosity, ...] = ("concise", "balanced", "detailed")
_MOTIVATION_VALUES: tuple[PersonaMotivation, ...] = ("soft", "balanced", "strong")
_EMOJI_VALUES: tuple[PersonaEmoji, ...] = ("minimal", "normal")

_DEFAULTS_BY_STYLE: dict[PersonaStyle, dict[str, str]] = {
    "supportive": {
        "style": "supportive",
        "verbosity": "balanced",
        "motivation": "soft",
        "emoji": "normal",
    },
    "rational": {
        "style": "rational",
        "verbosity": "concise",
        "motivation": "balanced",
        "emoji": "minimal",
    },
    "motivator": {
        "style": "motivator",
        "verbosity": "concise",
        "motivation": "strong",
        "emoji": "normal",
    },
}


def default_persona_settings(style: PersonaStyle = "rational") -> dict[str, str]:
    if style not in _STYLE_VALUES:
        style = "rational"
    return dict(_DEFAULTS_BY_STYLE[style])


def _sanitize_style(raw: Any) -> PersonaStyle:
    value = str(raw or "").strip().lower()
    if value in _STYLE_VALUES:
        return value
    if value == "neutral":
        return "rational"
    return "rational"


def normalize_persona_settings(profile: dict[str, Any]) -> dict[str, Any]:
    out = dict(profile)
    profile_raw = out.get("persona_profile")
    profile_map = dict(profile_raw) if isinstance(profile_raw, dict) else {}

    style = _sanitize_style(profile_map.get("style") or out.get("persona"))
    defaults = default_persona_settings(style)

    verbosity = str(profile_map.get("verbosity") or defaults["verbosity"]).strip().lower()
    if verbosity not in _VERBOSITY_VALUES:
        verbosity = str(defaults["verbosity"])

    motivation = str(profile_map.get("motivation") or defaults["motivation"]).strip().lower()
    if motivation not in _MOTIVATION_VALUES:
        motivation = str(defaults["motivation"])

    emoji = str(profile_map.get("emoji") or defaults["emoji"]).strip().lower()
    if emoji not in _EMOJI_VALUES:
        emoji = str(defaults["emoji"])

    out["persona"] = style
    out["persona_profile"] = {
        "style": style,
        "verbosity": verbosity,
        "motivation": motivation,
        "emoji": emoji,
    }
    return out


def set_persona_field(profile: dict[str, Any], *, field: str, value: str) -> dict[str, Any]:
    prof = normalize_persona_settings(profile)
    persona_profile = dict(prof.get("persona_profile") or {})

    if field == "style":
        style = _sanitize_style(value)
        defaults = default_persona_settings(style)
        persona_profile.update(defaults)
    elif field == "verbosity":
        if value not in _VERBOSITY_VALUES:
            raise ValueError("invalid persona verbosity")
        persona_profile["verbosity"] = value
    elif field == "motivation":
        if value not in _MOTIVATION_VALUES:
            raise ValueError("invalid persona motivation")
        persona_profile["motivation"] = value
    elif field == "emoji":
        if value not in _EMOJI_VALUES:
            raise ValueError("invalid persona emoji")
        persona_profile["emoji"] = value
    else:
        raise ValueError("invalid persona field")

    prof["persona_profile"] = persona_profile
    return normalize_persona_settings(prof)


def reset_persona_settings(profile: dict[str, Any]) -> dict[str, Any]:
    return normalize_persona_settings({**profile, "persona": "rational", "persona_profile": {}})


def persona_style_label(value: str) -> str:
    return {
        "supportive": "Supportive",
        "rational": "Rational",
        "motivator": "Motivator",
    }.get(str(value or "").strip().lower(), "Rational")


def persona_verbosity_label(value: str) -> str:
    return {
        "concise": "Concise",
        "balanced": "Balanced",
        "detailed": "Detailed",
    }.get(str(value or "").strip().lower(), "Balanced")


def persona_motivation_label(value: str) -> str:
    return {
        "soft": "Soft",
        "balanced": "Balanced",
        "strong": "Strong",
    }.get(str(value or "").strip().lower(), "Balanced")


def persona_emoji_label(value: str) -> str:
    return {
        "minimal": "Minimal",
        "normal": "Normal",
    }.get(str(value or "").strip().lower(), "Normal")


def render_persona_summary(profile: dict[str, Any]) -> str:
    prof = normalize_persona_settings(profile)
    persona_profile = dict(prof.get("persona_profile") or {})
    return "\n".join(
        [
            f"Style: {persona_style_label(str(persona_profile.get('style') or ''))}",
            f"Verbosity: {persona_verbosity_label(str(persona_profile.get('verbosity') or ''))}",
            f"Motivation: {persona_motivation_label(str(persona_profile.get('motivation') or ''))}",
            f"Emoji: {persona_emoji_label(str(persona_profile.get('emoji') or ''))}",
        ]
    )


def build_persona_prompt_suffix(profile: dict[str, Any]) -> str:
    prof = normalize_persona_settings(profile)
    persona_profile = dict(prof.get("persona_profile") or {})
    style = str(persona_profile.get("style") or "rational")
    verbosity = str(persona_profile.get("verbosity") or "balanced")
    motivation = str(persona_profile.get("motivation") or "balanced")
    emoji = str(persona_profile.get("emoji") or "normal")
    return (
        "Стиль відповіді: "
        f"style={style}; verbosity={verbosity}; motivation={motivation}; emoji={emoji}. "
        "Змінюй лише тон і формулювання, але не змінюй факти, суми, періоди чи висновки поза переданими даними."
    )
