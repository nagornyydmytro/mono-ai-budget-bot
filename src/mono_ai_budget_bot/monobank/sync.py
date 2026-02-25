from __future__ import annotations

import time
from dataclasses import dataclass

from .client import MonobankClient
from .models import MonoStatementItem


MAX_RANGE_SECONDS = 31 * 24 * 3600 + 3600  # 31 days + 1 hour

def iter_statement_windows(start_ts: int, end_ts: int, max_span_seconds: int = MAX_RANGE_SECONDS):
    """
    Yield (from_ts, to_ts) windows where (to_ts - from_ts) <= max_span_seconds.

    Monobank statement limit: 31 days + 1 hour (MAX_RANGE_SECONDS).
    """
    if max_span_seconds <= 0:
        raise ValueError("max_span_seconds must be > 0")

    if end_ts <= start_ts:
        return

    cur = int(start_ts)
    end_ts = int(end_ts)

    while cur < end_ts:
        nxt = min(end_ts, cur + max_span_seconds)
        if nxt <= cur:
            # Safety: prevent infinite loop if something goes wrong with timestamps
            raise RuntimeError(f"Invalid window progression: cur={cur}, nxt={nxt}, end={end_ts}")
        yield cur, nxt
        cur = nxt

@dataclass(frozen=True)
class SyncResult:
    accounts: int
    fetched_requests: int
    appended: int


def _normalize_item(account_id: str, it: MonoStatementItem) -> dict:
    return {
        "id": it.id,
        "time": it.time,
        "account_id": account_id,
        "amount": it.amount,
        "description": (it.description or "").strip(),
        "mcc": it.mcc,
        "currencyCode": it.currencyCode,
    }


def sync_accounts_ledger(
    *,
    mb: MonobankClient,
    tx_store,
    telegram_user_id: int,
    account_ids: list[str],
    days_back: int,
) -> SyncResult:
    """
    Sync transactions for selected accounts:
    - If ledger has last_ts: sync from last_ts - 3600 (safety overlap) to now
    - Else: sync from now - days_back
    Chunked by Mono statement range limit.
    """
    now = int(time.time())
    appended_total = 0
    fetched_requests = 0

    for acc_id in account_ids:
        last = tx_store.last_ts(telegram_user_id, acc_id)
        if last is None:
            start = now - days_back * 24 * 3600
        else:
            start = max(0, last - 3600)  # overlap 1h for safety

        for frm, to in iter_statement_windows(start, now):
            items = mb.statement(account=acc_id, date_from=frm, date_to=to)
            fetched_requests += 1

            normalized = [_normalize_item(acc_id, it) for it in items]
            appended_total += tx_store.append_many(telegram_user_id, acc_id, normalized)

    return SyncResult(accounts=len(account_ids), fetched_requests=fetched_requests, appended=appended_total)