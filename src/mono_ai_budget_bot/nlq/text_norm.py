from __future__ import annotations

import re


def norm(s: str) -> str:
    t = (s or "").strip().lower()
    t = t.replace("_", " ")
    t = re.sub(r"[^\w]+", " ", t, flags=re.UNICODE)
    t = re.sub(r"\s+", " ", t, flags=re.UNICODE).strip()
    return t
