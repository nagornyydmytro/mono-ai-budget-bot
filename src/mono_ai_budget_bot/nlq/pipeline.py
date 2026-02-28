from __future__ import annotations

from mono_ai_budget_bot.nlq.executor import execute_intent
from mono_ai_budget_bot.nlq.resolver import resolve
from mono_ai_budget_bot.nlq.router import route
from mono_ai_budget_bot.nlq.types import NLQRequest, NLQResponse, NLQResult


def handle_nlq(req: NLQRequest) -> NLQResponse:
    intent = route(req)
    if not intent:
        return NLQResponse(result=None, clarification=None)

    intent = resolve(req, intent)

    text = execute_intent(req.telegram_user_id, intent.slots)
    return NLQResponse(result=NLQResult(text=text), clarification=None)
