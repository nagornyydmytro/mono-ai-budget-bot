from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LedgerAccountMeta:
    last_ts: int | None
    last_sync_at: float | None
    coverage_from_ts: int | None
    coverage_to_ts: int | None


class LedgerMetaStore:
    """
    Per-user ledger meta stored as JSON:

      .cache/tx/<telegram_user_id>/_meta.json

    Structure:
      {
        "<account_id>": {
          "last_ts": 123,
          "last_sync_at": 123.45,
          "coverage_from_ts": 1700000000,
          "coverage_to_ts": 1702500000
        },
        ...
      }

    Notes:
    - coverage_* reflects requested sync windows, not necessarily exact min/max tx timestamps.
    - Fields are backward compatible with older meta files that only have last_ts/last_sync_at.
    """

    def __init__(self, root_dir: Path | None = None):
        self.root_dir = root_dir or (Path(".cache") / "tx")
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _user_dir(self, telegram_user_id: int) -> Path:
        d = self.root_dir / str(telegram_user_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _path(self, telegram_user_id: int) -> Path:
        return self._user_dir(telegram_user_id) / "_meta.json"

    def load_raw(self, telegram_user_id: int) -> dict[str, Any]:
        p = self._path(telegram_user_id)
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save_raw(self, telegram_user_id: int, data: dict[str, Any]) -> None:
        p = self._path(telegram_user_id)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(p)

    def get(self, telegram_user_id: int, account_id: str) -> LedgerAccountMeta:
        raw = self.load_raw(telegram_user_id)
        obj = raw.get(account_id) or {}

        last_ts = obj.get("last_ts")
        last_sync_at = obj.get("last_sync_at")
        cov_from = obj.get("coverage_from_ts")
        cov_to = obj.get("coverage_to_ts")

        return LedgerAccountMeta(
            last_ts=int(last_ts) if isinstance(last_ts, (int, float)) else None,
            last_sync_at=float(last_sync_at) if isinstance(last_sync_at, (int, float)) else None,
            coverage_from_ts=int(cov_from) if isinstance(cov_from, (int, float)) else None,
            coverage_to_ts=int(cov_to) if isinstance(cov_to, (int, float)) else None,
        )

    def update(self, telegram_user_id: int, account_id: str, *, last_ts: int | None) -> None:
        raw = self.load_raw(telegram_user_id)
        cur = raw.get(account_id) or {}

        prev_ts = cur.get("last_ts")
        prev_ts_int = int(prev_ts) if isinstance(prev_ts, (int, float)) else None

        if last_ts is not None:
            if prev_ts_int is None or last_ts > prev_ts_int:
                cur["last_ts"] = int(last_ts)

        cur["last_sync_at"] = time.time()
        raw[account_id] = cur
        self.save_raw(telegram_user_id, raw)

    def update_coverage_window(
        self,
        telegram_user_id: int,
        account_id: str,
        *,
        coverage_from_ts: int,
        coverage_to_ts: int,
    ) -> None:
        if coverage_to_ts < coverage_from_ts:
            raise ValueError("coverage_to_ts must be >= coverage_from_ts")

        raw = self.load_raw(telegram_user_id)
        cur = raw.get(account_id) or {}

        prev_from = cur.get("coverage_from_ts")
        prev_to = cur.get("coverage_to_ts")

        prev_from_int = int(prev_from) if isinstance(prev_from, (int, float)) else None
        prev_to_int = int(prev_to) if isinstance(prev_to, (int, float)) else None

        if prev_from_int is None or int(coverage_from_ts) < prev_from_int:
            cur["coverage_from_ts"] = int(coverage_from_ts)

        if prev_to_int is None or int(coverage_to_ts) > prev_to_int:
            cur["coverage_to_ts"] = int(coverage_to_ts)

        cur["last_sync_at"] = time.time()
        raw[account_id] = cur
        self.save_raw(telegram_user_id, raw)

    def get_coverage_window(self, telegram_user_id: int, account_id: str) -> tuple[int, int] | None:
        meta = self.get(telegram_user_id, account_id)
        if meta.coverage_from_ts is None or meta.coverage_to_ts is None:
            return None
        return meta.coverage_from_ts, meta.coverage_to_ts
