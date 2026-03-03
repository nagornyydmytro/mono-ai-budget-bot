from __future__ import annotations

import json
from pathlib import Path

from mono_ai_budget_bot.uncat.queue import UncatItem


class UncatStore:
    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or (Path(".cache") / "uncat")
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, user_id: int) -> Path:
        return self.base_dir / f"{user_id}.json"

    def save(self, user_id: int, items: list[UncatItem]) -> None:
        self._path(user_id).write_text(
            json.dumps([it.to_dict() for it in items], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load(self, user_id: int) -> list[UncatItem]:
        p = self._path(user_id)
        if not p.exists():
            return []
        raw = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return []
        out: list[UncatItem] = []
        for x in raw:
            if isinstance(x, dict):
                out.append(UncatItem.from_dict(x))
        return out
