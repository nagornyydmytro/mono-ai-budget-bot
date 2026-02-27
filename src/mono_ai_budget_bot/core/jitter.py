from __future__ import annotations

import os
import random


def jitter_seconds() -> int:
    mn = int(os.getenv("AUTO_REFRESH_JITTER_MIN", "0"))
    mx = int(os.getenv("AUTO_REFRESH_JITTER_MAX", "0"))
    if mx <= mn:
        return max(0, mn)
    return random.randint(mn, mx)
