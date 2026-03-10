from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from mono_ai_budget_bot.analytics.categories import category_from_mcc
from mono_ai_budget_bot.analytics.classify import classify_kind
from mono_ai_budget_bot.nlq.query_spec import QuerySpec
from mono_ai_budget_bot.nlq.text_norm import norm
from mono_ai_budget_bot.storage.tx_store import TxRecord


@dataclass(frozen=True)
class QueryFilter:
    intent: str
    category: str | None
    merchant_contains: list[str]
    recipient_contains: str | None


@dataclass(frozen=True)
class EntityComparison:
    label: str
    rows: list[TxRecord]
    total_cents: int
    count: int
    avg_ticket_cents: int


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

    def filter_for_spec(self, rows: list[TxRecord], spec: QuerySpec) -> list[TxRecord]:
        filtered = self.filter_rows(
            rows,
            QueryFilter(
                intent=spec.base_intent,
                category=spec.category,
                merchant_contains=list(spec.targets.merchant_terms),
                recipient_contains=spec.recipient_contains,
            ),
        )
        if spec.targets.merchant_exact and spec.targets.merchant_terms:
            terms = {_match_key(x) for x in spec.targets.merchant_terms if _match_key(x)}
            filtered = [
                r for r in filtered if _match_key(str(getattr(r, "description", "") or "")) in terms
            ]
        return filtered

    def sum_cents(self, rows: list[TxRecord], intent: str) -> int:
        if intent in {"spend_sum", "transfer_out_sum"}:
            return sum(-r.amount for r in rows)
        if intent in {"income_sum", "transfer_in_sum"}:
            return sum(r.amount for r in rows)
        raise ValueError(f"Unsupported intent for sum: {intent}")

    def sum_for_kind(self, rows: list[TxRecord], kind: str) -> int:
        if kind in {"spend", "transfer_out"}:
            return sum(abs(int(r.amount)) for r in rows)
        if kind in {"income", "transfer_in"}:
            return sum(max(0, int(r.amount)) for r in rows)
        raise ValueError(f"Unsupported kind for sum: {kind}")

    def count_for_rows(self, rows: list[TxRecord]) -> int:
        return len(rows)

    def average_ticket_cents(self, rows: list[TxRecord], kind: str) -> int:
        count = len(rows)
        if count <= 0:
            return 0
        return int(round(self.sum_for_kind(rows, kind) / count))

    def last_row(self, rows: list[TxRecord]) -> TxRecord | None:
        if not rows:
            return None
        return max(rows, key=lambda r: int(r.time))

    def recurrence_stats(self, rows: list[TxRecord]) -> tuple[int, int, int]:
        if not rows:
            return 0, 0, 0
        day_keys = sorted({int(r.time) // 86400 for r in rows})
        gaps = [int(day_keys[i] - day_keys[i - 1]) for i in range(1, len(day_keys))]
        median_gap = int(median(gaps)) if gaps else 0
        return len(rows), len(day_keys), median_gap

    def share_percent(
        self, *, numerator_rows: list[TxRecord], denominator_rows: list[TxRecord], kind: str
    ) -> float:
        denominator = self.sum_for_kind(denominator_rows, kind)
        if denominator <= 0:
            return 0.0
        numerator = self.sum_for_kind(numerator_rows, kind)
        return (numerator / denominator) * 100.0

    def compare_entities(
        self,
        rows: list[TxRecord],
        *,
        spec: QuerySpec,
    ) -> list[EntityComparison]:
        def _merchant_filter(value: str) -> QueryFilter:
            return QueryFilter(
                intent=spec.base_intent,
                category=None,
                merchant_contains=[value],
                recipient_contains=None,
            )

        def _category_filter(value: str) -> QueryFilter:
            return QueryFilter(
                intent=spec.base_intent,
                category=value,
                merchant_contains=[],
                recipient_contains=None,
            )

        def _recipient_filter(value: str) -> QueryFilter:
            return QueryFilter(
                intent=spec.base_intent,
                category=None,
                merchant_contains=[],
                recipient_contains=value,
            )

        if spec.targets.target_type == "merchant":
            values = list(spec.targets.merchant_terms)
            build_filter = _merchant_filter
            exact = spec.targets.merchant_exact
        elif spec.targets.target_type == "category":
            values = list(spec.targets.category_terms)
            build_filter = _category_filter
            exact = False
        elif spec.targets.target_type == "recipient":
            values = list(spec.targets.recipient_terms)
            build_filter = _recipient_filter
            exact = False
        else:
            values = []
            build_filter = None
            exact = False

        out: list[EntityComparison] = []
        if build_filter is None:
            return out

        for value in values:
            subset = self.filter_rows(rows, build_filter(value))
            if exact and spec.targets.target_type == "merchant":
                key = _match_key(value)
                subset = [
                    r for r in subset if _match_key(str(getattr(r, "description", "") or "")) == key
                ]
            out.append(
                EntityComparison(
                    label=value,
                    rows=subset,
                    total_cents=self.sum_for_kind(subset, spec.kind),
                    count=len(subset),
                    avg_ticket_cents=self.average_ticket_cents(subset, spec.kind),
                )
            )
        return out


def _match_key(s: str) -> str:
    return norm(s).replace(" ", "")
