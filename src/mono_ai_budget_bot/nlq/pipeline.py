from __future__ import annotations

from mono_ai_budget_bot.nlq.executor import execute_intent
from mono_ai_budget_bot.nlq.memory_store import load_memory, save_category_alias, save_memory
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


def _is_paging_continue(user_text: str) -> bool:
    s = (user_text or "").strip().lower()
    if not s:
        return False
    if s.isdigit():
        return int(s) == 1
    return s in {"далі", "ще", "дальше", "next", "more", ">", ">>"}


def _parse_multi_select(user_text: str, options: list[str]) -> list[str]:
    s = (user_text or "").strip().lower()
    if not s or s in {"0", "ні", "нет", "cancel", "скасувати"}:
        return []

    tokens = []
    for part in s.replace(";", ",").replace(" ", ",").split(","):
        part = part.strip()
        if not part:
            continue
        tokens.append(part)

    idxs: set[int] = set()
    for t in tokens:
        if "-" in t:
            a, b = t.split("-", 1)
            if a.strip().isdigit() and b.strip().isdigit():
                x, y = int(a), int(b)
                if x > y:
                    x, y = y, x
                for i in range(x, y + 1):
                    idxs.add(i)
            continue
        if t.isdigit():
            idxs.add(int(t))

    picked: list[str] = []
    for i in sorted(idxs):
        if 1 <= i <= len(options):
            v = options[i - 1].strip()
            if v:
                picked.append(v)

    return picked


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
        pending_kind = mem.get("pending_kind")
        if pending_kind == "paging" and _is_paging_continue(req.text):
            mem["pending_intent"] = None
            mem["pending_kind"] = None
            mem["pending_options"] = None
            save_memory(req.telegram_user_id, mem)

            text = execute_intent(req.telegram_user_id, pending)
            return NLQResponse(result=NLQResult(text=text), clarification=None)

        if pending_kind == "category_alias" and options:
            alias_to_learn = str(pending.get("alias_to_learn") or "").strip()
            selected = _parse_multi_select(req.text, options)

            if alias_to_learn and selected:
                save_category_alias(req.telegram_user_id, alias_to_learn, selected)

                mem = load_memory(req.telegram_user_id)
                mem["pending_intent"] = None
                mem["pending_kind"] = None
                mem["pending_options"] = None
                save_memory(req.telegram_user_id, mem)

                text = execute_intent(req.telegram_user_id, pending)
                return NLQResponse(result=NLQResult(text=text), clarification=None)

            if alias_to_learn and req.text.strip() in {"0", "cancel", "скасувати", "ні", "нет"}:
                mem["pending_intent"] = None
                mem["pending_kind"] = None
                mem["pending_options"] = None
                save_memory(req.telegram_user_id, mem)
                return NLQResponse(result=NLQResult(text="Ок, не зберігаю."), clarification=None)

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
