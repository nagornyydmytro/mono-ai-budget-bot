from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BASE_DIR = Path(".cache") / "profile"


def load_profile(telegram_user_id: int) -> dict[str, Any] | None:
    path = BASE_DIR / f"{int(telegram_user_id)}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def save_profile(telegram_user_id: int, data: dict[str, Any]) -> None:
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    path = BASE_DIR / f"{int(telegram_user_id)}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
