from __future__ import annotations

from mono_ai_budget_bot.nlq.executor import execute_intent
from mono_ai_budget_bot.nlq.memory_store import load_memory, save_memory
from mono_ai_budget_bot.nlq.resolver import resolve
from mono_ai_budget_bot.nlq.router import route
from mono_ai_budget_bot.nlq.types import NLQRequest, NLQResponse, NLQResult


def _resolve_followup_value(user_text: str, options: list[str] | None) -> str:
    s = (user_text or "").strip()
    if not s:
        return ""

    if options and s.isdigit():
        idx = int(s)
        if 1 <= idx <= len(options):
            return options[idx - 1].strip()

    return s


def _extract_recipient_alias(pending: dict) -> str:
    for k in ("recipient_alias", "recipient_contains", "recipient", "alias"):
        v = pending.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip().lower()
    return ""


def handle_nlq(req: NLQRequest) -> NLQResponse:
    mem = load_memory(req.telegram_user_id)
    pending = mem.get("pending_intent")
    pending_options = mem.get("pending_options")

    options: list[str] | None
    if isinstance(pending_options, list):
        options = [x.strip() for x in pending_options if isinstance(x, str) and x.strip()]
        if not options:
            options = None
    else:
        options = None

    if isinstance(pending, dict):
        alias = _extract_recipient_alias(pending)
        match_value = _resolve_followup_value(req.text, options).strip().lower()

        if alias and match_value:
            ra = mem.get("recipient_aliases")
            if not isinstance(ra, dict):
                ra = {}
            ra[alias] = match_value
            mem["recipient_aliases"] = ra

            mem["pending_intent"] = None
            mem["pending_kind"] = None
            mem["pending_options"] = None
            save_memory(req.telegram_user_id, mem)

            text = execute_intent(req.telegram_user_id, pending)
            return NLQResponse(result=NLQResult(text=text), clarification=None)

    intent = route(req)
    if not intent:
        return NLQResponse(result=None, clarification=None)

    intent = resolve(req, intent)
    text = execute_intent(req.telegram_user_id, intent.slots)
    return NLQResponse(result=NLQResult(text=text), clarification=None)
