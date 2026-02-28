from __future__ import annotations

from mono_ai_budget_bot.nlq.executor import execute_intent
from mono_ai_budget_bot.nlq.memory_store import (
    get_pending_options,
    pop_pending_intent,
    save_recipient_alias,
)
from mono_ai_budget_bot.nlq.resolver import resolve
from mono_ai_budget_bot.nlq.router import route
from mono_ai_budget_bot.nlq.types import NLQRequest, NLQResponse, NLQResult


def _resolve_followup_value(user_text: str, options: list[str] | None) -> str:
    s = (user_text or "").strip()
    if not s:
        return ""

    if options:
        if s.isdigit():
            idx = int(s)
            if 1 <= idx <= len(options):
                return options[idx - 1].strip()

    return s


def handle_nlq(req: NLQRequest) -> NLQResponse:
    pending = pop_pending_intent(req.telegram_user_id)
    if pending:
        alias = (pending.get("recipient_alias") or "").strip().lower()
        opts = get_pending_options(req.telegram_user_id)
        match_value = _resolve_followup_value(req.text, opts).strip().lower()
        if alias and match_value:
            save_recipient_alias(req.telegram_user_id, alias, match_value)
            text = execute_intent(req.telegram_user_id, pending)
            return NLQResponse(result=NLQResult(text=text), clarification=None)

    intent = route(req)
    if not intent:
        return NLQResponse(result=None, clarification=None)

    intent = resolve(req, intent)
    text = execute_intent(req.telegram_user_id, intent.slots)
    return NLQResponse(result=NLQResult(text=text), clarification=None)
