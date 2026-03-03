from __future__ import annotations

import json
from pathlib import Path

from mono_ai_budget_bot.reports.config import ReportsConfig, build_reports_preset


class ReportsStore:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, user_id: int) -> Path:
        return self.base_dir / f"{user_id}.json"

    def save(self, user_id: int, cfg: ReportsConfig) -> None:
        self._path(user_id).write_text(
            json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load(self, user_id: int) -> ReportsConfig:
        p = self._path(user_id)
        if not p.exists():
            return build_reports_preset("min")
        d = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(d, dict):
            return build_reports_preset("min")
        return ReportsConfig.from_dict(d)
