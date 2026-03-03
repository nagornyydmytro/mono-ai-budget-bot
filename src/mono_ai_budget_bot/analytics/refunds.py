from __future__ import annotations

import re
from dataclasses import dataclass

from mono_ai_budget_bot.analytics.classify import classify_kind
from mono_ai_budget_bot.storage.tx_store import TxRecord


@dataclass(frozen=True)
class RefundPair:
    purchase_id: str
    refund_id: str
    purchase_ts: int
    refund_ts: int
    purchase_amount: int
    refund_amount: int
    merchant_key: str


_STOP = {
    "повернення",
    "поверненням",
    "refund",
    "reversal",
    "chargeback",
    "скасування",
    "відміна",
    "отмена",
    "return",
    "rev",
    "re",
    "txn",
}


def _tokens(s: str) -> list[str]:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9а-яіїєґ]+", " ", s, flags=re.IGNORECASE)
    parts = [p.strip() for p in s.split() if p.strip()]
    out: list[str] = []
    for p in parts:
        if p in _STOP:
            continue
        if len(p) < 3:
            continue
        out.append(p)
    return out[:12]


def _merchant_key(desc: str) -> str:
    t = _tokens(desc)
    return " ".join(t[:8])


def _match_merchant(a: str, b: str) -> bool:
    ta = set(_tokens(a))
    tb = set(_tokens(b))
    if not ta or not tb:
        return False
    inter = ta & tb
    if len(inter) >= 2:
        return True
    if len(inter) == 1:
        x = next(iter(inter))
        if len(x) >= 5:
            return True
    return False


def _amount_close(purchase_abs: int, refund_amt: int) -> bool:
    if purchase_abs <= 0 or refund_amt <= 0:
        return False
    tol = max(100, int(purchase_abs * 0.01))
    return abs(purchase_abs - refund_amt) <= tol


def detect_refund_pairs(
    records: list[TxRecord],
    *,
    max_days: int = 14,
) -> list[RefundPair]:
    if not records:
        return []

    spend: list[TxRecord] = []
    pos: list[TxRecord] = []

    for r in records:
        desc = (r.description or "").strip()
        k = classify_kind(amount=r.amount, mcc=r.mcc, description=desc)
        if k == "spend" and r.amount < 0:
            spend.append(r)
        elif r.amount > 0 and k in {"income", "transfer_in"}:
            pos.append(r)

    spend.sort(key=lambda r: int(r.time))
    pos.sort(key=lambda r: int(r.time))

    max_dt = int(max_days) * 24 * 60 * 60
    used_refunds: set[str] = set()
    pairs: list[RefundPair] = []

    j0 = 0
    for p in spend:
        p_ts = int(p.time)
        p_abs = abs(int(p.amount))
        if p_abs <= 0:
            continue

        while j0 < len(pos) and int(pos[j0].time) < (p_ts - max_dt):
            j0 += 1

        best: TxRecord | None = None
        best_score = -1

        for j in range(j0, len(pos)):
            r = pos[j]
            r_ts = int(r.time)
            if r_ts > (p_ts + max_dt):
                break
            if r.id in used_refunds:
                continue
            if r.account_id != p.account_id:
                continue
            if p.mcc is not None and r.mcc is not None and int(p.mcc) != int(r.mcc):
                continue
            if not _amount_close(p_abs, int(r.amount)):
                continue
            if not _match_merchant(p.description or "", r.description or ""):
                continue

            score = 0
            score += 5
            score -= int(abs(p_abs - int(r.amount)) / 100)
            score -= int(abs(r_ts - p_ts) / (6 * 3600))
            if score > best_score:
                best_score = score
                best = r

        if best is None:
            continue

        used_refunds.add(best.id)
        pairs.append(
            RefundPair(
                purchase_id=p.id,
                refund_id=best.id,
                purchase_ts=p_ts,
                refund_ts=int(best.time),
                purchase_amount=int(p.amount),
                refund_amount=int(best.amount),
                merchant_key=_merchant_key(p.description or ""),
            )
        )

    return pairs


def refund_ignore_ids(pairs: list[RefundPair]) -> set[str]:
    out: set[str] = set()
    for x in pairs:
        if x.purchase_id:
            out.add(x.purchase_id)
        if x.refund_id:
            out.add(x.refund_id)
    return out
