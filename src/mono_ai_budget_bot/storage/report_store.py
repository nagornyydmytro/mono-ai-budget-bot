from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StoredReport:
    period: str
    generated_at: float
    facts: dict[str, Any]


class ReportStore:
    """
    Per-user local cache:
      .cache/reports/<telegram_user_id>/facts_<period>.json

    period: today | week | month
    """

    def __init__(self, root_dir: Path | None = None):
        self.root_dir = root_dir or (Path(".cache") / "reports")
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _user_dir(self, telegram_user_id: int) -> Path:
        d = self.root_dir / str(telegram_user_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _path(self, telegram_user_id: int, period: str) -> Path:
        return self._user_dir(telegram_user_id) / f"facts_{period}.json"

    def save(self, telegram_user_id: int, period: str, facts: dict[str, Any]) -> Path:
        payload: dict[str, Any] = {
            "period": period,
            "generated_at": time.time(),
            "facts": facts,
        }
        path = self._path(telegram_user_id, period)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return path

    def load(self, telegram_user_id: int, period: str) -> StoredReport | None:
        path = self._path(telegram_user_id, period)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return StoredReport(
                period=str(data.get("period", period)),
                generated_at=float(data.get("generated_at", 0.0)),
                facts=dict(data.get("facts", {})),
            )
        except Exception:
            return None

    def last_generated_at(self, telegram_user_id: int, period: str) -> float | None:
        stored = self.load(telegram_user_id, period)
        return None if stored is None else stored.generated_at