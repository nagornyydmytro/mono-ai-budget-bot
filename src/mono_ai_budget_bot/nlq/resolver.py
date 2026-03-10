from __future__ import annotations

from mono_ai_budget_bot.nlq.models import ResolutionState, Slots, canonical_intent_family
from mono_ai_budget_bot.nlq.types import NLQIntent, NLQRequest


def resolve(req: NLQRequest, intent: NLQIntent) -> NLQIntent:
    state = resolve_canonical(req, intent)
    return state.to_intent()


def resolve_canonical(req: NLQRequest, intent: NLQIntent) -> ResolutionState:
    slots = Slots(dict(intent.slots or {}))
    confidence = str(slots.get("slots_confidence") or "high").strip().lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "high"
    return ResolutionState(
        intent=canonical_intent(intent),
        slots=slots,
        resolved_slots=slots,
        confidence=confidence,
        needs_clarification=False,
    )


def canonical_intent(intent: NLQIntent):
    from mono_ai_budget_bot.nlq.models import QueryIntent

    return QueryIntent(
        name=intent.name,
        family=canonical_intent_family(intent.name),
    )
