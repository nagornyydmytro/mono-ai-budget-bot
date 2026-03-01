from __future__ import annotations

import re

from .categories import category_from_mcc

_ws_re = re.compile(r"\s+")
_strip_re = re.compile(r"[^\w\s'&+\-\.]")

_tail_id_re = re.compile(
    r"(?:\s*[#№]\s*\w+|\s+\d{3,}|\s+[a-f0-9]{6,})\s*$",
    re.IGNORECASE,
)
_tail_cut_re = re.compile(r"\b(?:kyiv|kiev|ua|ukraine|terminal|pos)\b", re.IGNORECASE)


def normalize_text(text: str) -> str:
    s = (text or "").strip().lower()
    s = _strip_re.sub(" ", s)
    s = _ws_re.sub(" ", s).strip()
    return s


def normalize_merchant(description: str) -> str:
    s = normalize_text(description)
    if not s:
        return "unknown"

    s = _tail_id_re.sub("", s).strip()
    if not s:
        return "unknown"

    m = _tail_cut_re.search(s)
    if m:
        s = s[: m.start()].strip()

    if not s:
        return "unknown"

    return s[:48]


def category_label(mcc: int | None) -> str:
    return category_from_mcc(mcc) or "Інше"
