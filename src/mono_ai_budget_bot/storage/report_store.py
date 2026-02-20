from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StoredReport:
    period: str
    generated_at: float  # unix timestamp
    facts: dict[str, Any]


class ReportStore:
    """
    Stores computed facts per period to disk for fast bot responses.
    Files are stored under .cache/reports/.
    """

    def __init__(self, root_dir: Path | None = None):
        self.root_dir = root_dir or (Path(".cache") / "reports")
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, period: str) -> Path:
        return self.root_dir / f"facts_{period}.json"

    def save(self, period: str, facts: dict[str, Any]) -> Path:
        payload = {
            "period": period,
            "generated_at": time.time(),
            "facts": facts,
        }
        path = self._path(period)

        # atomic-ish write
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return path

    def load(self, period: str) -> StoredReport | None:
        path = self._path(period)
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