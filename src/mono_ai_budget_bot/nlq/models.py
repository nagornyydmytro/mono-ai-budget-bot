from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from mono_ai_budget_bot.nlq.types import NLQIntent

IntentFamily = Literal[
    "spend",
    "income",
    "transfer_out",
    "transfer_in",
    "comparison",
    "ranking",
    "share",
    "threshold",
    "recurrence",
    "recent_event",
    "summary",
    "explanation",
    "simulation",
    "conversion",
    "unknown",
]

StrategyMode = Literal["deterministic", "clarify", "llm", "none"]


@dataclass(frozen=True)
class QueryIntent:
    name: str
    family: IntentFamily


@dataclass(frozen=True)
class Slots:
    values: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return dict(self.values)

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)


@dataclass(frozen=True)
class ResolutionState:
    intent: QueryIntent
    slots: Slots
    resolved_slots: Slots
    confidence: Literal["high", "medium", "low"]
    needs_clarification: bool = False

    def to_intent(self) -> NLQIntent:
        payload = self.resolved_slots.to_payload()
        payload.setdefault("intent", self.intent.name)
        return NLQIntent(name=self.intent.name, slots=payload)


@dataclass(frozen=True)
class AnswerStrategy:
    mode: StrategyMode
    reason: str


@dataclass(frozen=True)
class CanonicalQuery:
    raw_text: str
    normalized_text: str
    intent: QueryIntent | None
    slots: Slots


def canonical_intent_family(intent_name: str | None) -> IntentFamily:
    name = str(intent_name or "").strip()
    if name.startswith("spend_"):
        return "spend"
    if name.startswith("income_"):
        return "income"
    if name.startswith("transfer_out_"):
        return "transfer_out"
    if name.startswith("transfer_in_"):
        return "transfer_in"
    if name in {"compare_to_baseline", "compare_to_previous_period"}:
        return "comparison"
    if name in {
        "top_merchants",
        "top_categories",
        "top_growth_categories",
        "top_decline_categories",
    }:
        return "ranking"
    if name == "category_share":
        return "share"
    if name in {"threshold_query", "count_over", "count_under"}:
        return "threshold"
    if name == "recurrence_summary":
        return "recurrence"
    if name == "last_time":
        return "recent_event"
    if name in {"spend_summary_short", "spend_insights_three", "spend_unusual_summary"}:
        return "summary"
    if name == "explain_growth":
        return "explanation"
    if name == "what_if":
        return "simulation"
    if name == "currency_convert":
        return "conversion"
    return "unknown"
