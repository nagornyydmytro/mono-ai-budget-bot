from __future__ import annotations

from . import templates


def map_monobank_error(e: Exception) -> str | None:
    s = str(e)

    if "Monobank API error: 401" in s or "Monobank API error: 403" in s:
        return templates.monobank_invalid_token_message()

    if "Monobank API error: 429" in s:
        return templates.monobank_rate_limit_message()

    if "Monobank API error:" in s:
        return templates.monobank_generic_error_message()

    return None


def map_llm_error(_: Exception) -> str:
    return templates.llm_unavailable_message()
