from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from .ledger_meta_store import LedgerMetaStore

@dataclass(frozen=True)
class TxRecord:
    id: str
    time: int
    account_id: str
    amount: int
    description: str
    mcc: int | None
    currencyCode: int | None


class TxStore:
    """
    Per-user transaction ledger stored as JSONL:

      .cache/tx/<telegram_user_id>/<account_id>.jsonl

    Each line is a JSON object for a transaction.
    """

    def __init__(self, root_dir: Path | None = None):
        self.root_dir = root_dir or (Path(".cache") / "tx")
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._meta = LedgerMetaStore(self.root_dir)

    def _user_dir(self, telegram_user_id: int) -> Path:
        d = self.root_dir / str(telegram_user_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _path(self, telegram_user_id: int, account_id: str) -> Path:
        return self._user_dir(telegram_user_id) / f"{account_id}.jsonl"

    def last_ts(self, telegram_user_id: int, account_id: str) -> int | None:
        # 1️⃣ Fast path: try meta
        meta = self._meta.get(telegram_user_id, account_id)
        if meta.last_ts is not None:
            return meta.last_ts

        # 2️⃣ Fallback: scan JSONL once
        path = self._path(telegram_user_id, account_id)
        if not path.exists():
            return None

        last: int | None = None
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                obj = json.loads(line)
                t = int(obj.get("time", 0))
                if last is None or t > last:
                    last = t
        except Exception:
            return None

        # 3️⃣ Persist into meta for future fast access
        if last is not None:
            self._meta.update(telegram_user_id, account_id, last_ts=last)

        return last

    def _load_ids_set(self, telegram_user_id: int, account_id: str) -> set[str]:
        path = self._path(telegram_user_id, account_id)
        ids: set[str] = set()
        if not path.exists():
            return ids
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                obj = json.loads(line)
                tid = obj.get("id")
                if tid:
                    ids.add(str(tid))
        except Exception:
            return ids
        return ids

    def append_many(self, telegram_user_id: int, account_id: str, items: Iterable[dict[str, Any]]) -> int:
        """
        Append new transactions (dedupe by tx id). Returns count of appended rows.
        """
        path = self._path(telegram_user_id, account_id)
        ids = self._load_ids_set(telegram_user_id, account_id)

        appended = 0
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            for it in items:
                tid = str(it.get("id", "")).strip()
                if not tid or tid in ids:
                    continue
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
                ids.add(tid)
                appended += 1
        if appended > 0:
            max_t: int | None = None
            for it in items:
                try:
                    t = int(it.get("time", 0))
                except Exception:
                    continue
                if max_t is None or t > max_t:
                    max_t = t
            self._meta.update(telegram_user_id, account_id, last_ts=max_t)
        return appended

    def load_range(
        self,
        telegram_user_id: int,
        account_ids: list[str],
        ts_from: int,
        ts_to: int,
    ) -> list[TxRecord]:
        rows: list[TxRecord] = []
        for acc_id in account_ids:
            path = self._path(telegram_user_id, acc_id)
            if not path.exists():
                continue
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    obj = json.loads(line)
                    t = int(obj.get("time", 0))
                    if t < ts_from or t > ts_to:
                        continue
                    rows.append(
                        TxRecord(
                            id=str(obj.get("id", "")),
                            time=t,
                            account_id=str(obj.get("account_id", acc_id)),
                            amount=int(obj.get("amount", 0)),
                            description=str(obj.get("description", "") or "").strip(),
                            mcc=(int(obj["mcc"]) if obj.get("mcc") is not None else None),
                            currencyCode=(int(obj["currencyCode"]) if obj.get("currencyCode") is not None else None),
                        )
                    )
            except Exception:
                continue

        rows.sort(key=lambda r: r.time)
        return rows