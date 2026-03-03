from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class UncatPending:
    pending_id: str
    created_ts: int
    ttl_sec: int
    stage: str
    tx_id: str
    used: bool

    def is_expired(self, now_ts: int) -> bool:
        return now_ts > (self.created_ts + self.ttl_sec)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pending_id": self.pending_id,
            "created_ts": self.created_ts,
            "ttl_sec": self.ttl_sec,
            "stage": self.stage,
            "tx_id": self.tx_id,
            "used": self.used,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> UncatPending:
        return UncatPending(
            pending_id=str(d.get("pending_id") or ""),
            created_ts=int(d.get("created_ts") or 0),
            ttl_sec=int(d.get("ttl_sec") or 0),
            stage=str(d.get("stage") or ""),
            tx_id=str(d.get("tx_id") or ""),
            used=bool(d.get("used") or False),
        )


class UncatPendingStore:
    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or (Path(".cache") / "uncat_pending")
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, user_id: int) -> Path:
        return self.base_dir / f"{int(user_id)}.json"

    def create(self, user_id: int, *, tx_id: str, stage: str, ttl_sec: int = 900) -> UncatPending:
        pid = secrets.token_urlsafe(9)
        now_ts = int(time.time())
        p = UncatPending(
            pending_id=pid,
            created_ts=now_ts,
            ttl_sec=int(ttl_sec),
            stage=str(stage),
            tx_id=str(tx_id),
            used=False,
        )
        self._path(user_id).write_text(
            json.dumps(p.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return p

    def load(self, user_id: int) -> UncatPending | None:
        p = self._path(user_id)
        if not p.exists():
            return None
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(raw, dict):
            return None
        up = UncatPending.from_dict(raw)
        if not up.pending_id:
            return None
        return up

    def mark_used(self, user_id: int) -> None:
        cur = self.load(user_id)
        if cur is None:
            return
        upd = UncatPending(
            pending_id=cur.pending_id,
            created_ts=cur.created_ts,
            ttl_sec=cur.ttl_sec,
            stage=cur.stage,
            tx_id=cur.tx_id,
            used=True,
        )
        self._path(user_id).write_text(
            json.dumps(upd.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def clear(self, user_id: int) -> None:
        p = self._path(user_id)
        if p.exists():
            p.unlink()
