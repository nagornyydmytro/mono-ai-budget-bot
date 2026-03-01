from __future__ import annotations

from dataclasses import dataclass

from mono_ai_budget_bot.analytics.categories import category_from_mcc
from mono_ai_budget_bot.analytics.classify import classify_kind
from mono_ai_budget_bot.nlq.text_norm import norm
from mono_ai_budget_bot.storage.tx_store import TxRecord


@dataclass(frozen=True)
class QueryFilter:
    intent: str
    category: str | None
    merchant_contains: list[str]
    recipient_contains: str | None


class QueryEngine:
    def filter_rows(self, rows: list[TxRecord], f: QueryFilter) -> list[TxRecord]:
        out: list[TxRecord] = []

        merchant_terms = [
            _match_key(x) for x in (f.merchant_contains or []) if isinstance(x, str) and x.strip()
        ]
        merchant_terms = [x for x in merchant_terms if x]
        recipient = (f.recipient_contains or "").strip().lower() or None
        category = (f.category or "").strip() or None

        for r in rows:
            kind = classify_kind(r.amount, r.mcc, r.description)

            if f.intent.startswith("spend_"):
                if kind != "spend":
                    continue
                if category:
                    c = category_from_mcc(r.mcc)
                    if c != category:
                        continue
                if merchant_terms:
                    d = _match_key(r.description or "")
                    if not any(m in d for m in merchant_terms):
                        continue

            elif f.intent.startswith("income_"):
                if kind != "income":
                    continue

            elif f.intent.startswith("transfer_out_"):
                if kind != "transfer_out":
                    continue
                if recipient and recipient not in (r.description or "").lower():
                    continue

            elif f.intent.startswith("transfer_in_"):
                if kind != "transfer_in":
                    continue
                if recipient and recipient not in (r.description or "").lower():
                    continue

            else:
                continue

            out.append(r)

        return out

    def sum_cents(self, rows: list[TxRecord], intent: str) -> int:
        if intent in {"spend_sum", "transfer_out_sum"}:
            return sum(-r.amount for r in rows)
        if intent in {"income_sum", "transfer_in_sum"}:
            return sum(r.amount for r in rows)
        raise ValueError(f"Unsupported intent for sum: {intent}")


def _match_key(s: str) -> str:
    return norm(s).replace(" ", "")
