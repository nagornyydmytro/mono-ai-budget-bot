from __future__ import annotations

from functools import lru_cache

from mono_ai_budget_bot.config import load_settings
from mono_ai_budget_bot.llm.openai_client import OpenAIClient
from mono_ai_budget_bot.nlq.executor import execute_intent
from mono_ai_budget_bot.nlq.memory_store import (
    load_memory,
    pending_is_alive,
    pop_pending_action,
    save_category_alias,
    save_memory,
)
from mono_ai_budget_bot.nlq.resolver import resolve
from mono_ai_budget_bot.nlq.router import route
from mono_ai_budget_bot.nlq.types import NLQIntent, NLQRequest, NLQResponse, NLQResult


@lru_cache(maxsize=1)
def _get_llm_client() -> OpenAIClient | None:
    s = load_settings()
    if not s.openai_api_key:
        return None
    return OpenAIClient(api_key=s.openai_api_key, model=s.openai_model)


def _is_out_of_scope_for_llm(text: str) -> bool:
    s = (text or "").lower()
    banned = [
        "інвест",
        "акц",
        "облігац",
        "крипт",
        "bitcoin",
        "btc",
        "eth",
        "ethereum",
        "trading",
        "trade",
        "buy",
        "sell",
        "портфел",
        "etf",
        "форекс",
        "forex",
        "дивіденд",
        "yield",
        "staking",
        "system prompt",
        "developer message",
        "ignore previous",
        "jailbreak",
        "ігноруй правила",
        "ігноруй попередні",
        "розкрий промпт",
        "розкрий інструкції",
    ]
    return any(k in s for k in banned)


_LLM_LAST_TS: dict[int, int] = {}


def _llm_cooldown_ok(user_id: int, now_ts: int, seconds: int = 10) -> bool:
    seconds = max(5, min(int(seconds), 120))
    last = int(_LLM_LAST_TS.get(int(user_id), 0))
    if int(now_ts) - last < seconds:
        return False
    _LLM_LAST_TS[int(user_id)] = int(now_ts)
    return True


def _llm_plan_intent(req: NLQRequest) -> NLQIntent | None:
    if _is_out_of_scope_for_llm(req.text):
        return None
    if not _llm_cooldown_ok(req.telegram_user_id, req.now_ts, seconds=10):
        return None
    client = _get_llm_client()
    if client is None:
        return None

    try:
        slots = client.plan_nlq(user_text=req.text, now_ts=req.now_ts)
    except Exception:
        return None

    if not slots or not isinstance(slots, dict):
        return None

    name = str(slots.get("intent") or "").strip()
    if not name or name == "unsupported":
        return None

    return NLQIntent(name=name, slots=slots)


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
    if not s:
        return []

    if s in {"0", "ні", "нет", "cancel", "скасувати"}:
        return []

    normalized_options = [o.strip() for o in options if isinstance(o, str) and o.strip()]
    if not normalized_options:
        return []

    if s in {"всі", "усі", "all"}:
        return list(normalized_options)

    if s.startswith("всі крім") or s.startswith("усі крім"):
        tail = s.split("крім", 1)[1].strip()
        excluded = _parse_multi_select(tail, options)
        return [o for o in normalized_options if o not in excluded]

    tokens = []
    for part in s.replace(";", ",").split(","):
        part = part.strip()
        if part:
            tokens.append(part)

    picked: set[str] = set()

    for t in tokens:
        if "-" in t:
            a, b = t.split("-", 1)
            if a.strip().isdigit() and b.strip().isdigit():
                x, y = int(a), int(b)
                if x > y:
                    x, y = y, x
                for i in range(x, y + 1):
                    if 1 <= i <= len(normalized_options):
                        picked.add(normalized_options[i - 1])
            continue

        if t.isdigit():
            i = int(t)
            if 1 <= i <= len(normalized_options):
                picked.add(normalized_options[i - 1])
            continue

    for t in tokens:
        if t.isdigit() or "-" in t:
            continue
        for o in normalized_options:
            if t in o.lower():
                picked.add(o)

    return list(picked)


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

    if pending and not pending_is_alive(mem, now_ts=req.now_ts):
        pop_pending_action(req.telegram_user_id)
        pending = None
        options = None
        mem = load_memory(req.telegram_user_id)

    if isinstance(pending, dict):
        pending_kind = mem.get("pending_kind")

        if pending_kind == "paging" and _is_paging_continue(req.text):
            pop_pending_action(req.telegram_user_id)
            text = execute_intent(req.telegram_user_id, pending)
            return NLQResponse(result=NLQResult(text=text), clarification=None)

        if pending_kind == "category_alias" and options:
            alias_to_learn = str(pending.get("alias_to_learn") or "").strip()
            selected = _parse_multi_select(req.text, options)

            if alias_to_learn and selected:
                save_category_alias(req.telegram_user_id, alias_to_learn, selected)
                pop_pending_action(req.telegram_user_id)
                text = execute_intent(req.telegram_user_id, pending)
                return NLQResponse(result=NLQResult(text=text), clarification=None)

            if alias_to_learn and req.text.strip().lower() in {
                "0",
                "cancel",
                "скасувати",
                "ні",
                "нет",
            }:
                pop_pending_action(req.telegram_user_id)
                return NLQResponse(result=NLQResult(text="Ок, не зберігаю."), clarification=None)

        alias = _extract_recipient_alias(pending)
        match_value = _resolve_followup_value(req.text, options).strip().lower()

        if alias and match_value:
            ra = mem.get("recipient_aliases")
            if not isinstance(ra, dict):
                ra = {}
            ra[alias] = match_value
            mem["recipient_aliases"] = ra
            save_memory(req.telegram_user_id, mem)

            pop_pending_action(req.telegram_user_id)
            text = execute_intent(req.telegram_user_id, pending)
            return NLQResponse(result=NLQResult(text=text), clarification=None)

    intent = route(req)
    if not intent:
        intent = _llm_plan_intent(req)
        if not intent:
            return NLQResponse(result=None, clarification=None)

    intent = resolve(req, intent)
    text = execute_intent(req.telegram_user_id, intent.slots)
    return NLQResponse(result=NLQResult(text=text), clarification=None)
