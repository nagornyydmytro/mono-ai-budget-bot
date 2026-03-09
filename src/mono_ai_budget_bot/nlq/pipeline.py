from __future__ import annotations

import re
from functools import lru_cache
from typing import Literal

from mono_ai_budget_bot.analytics.categories import category_from_mcc
from mono_ai_budget_bot.analytics.classify import classify_kind
from mono_ai_budget_bot.config import load_settings
from mono_ai_budget_bot.llm.openai_client import OpenAIClient
from mono_ai_budget_bot.llm.tooling import execute_tool_call
from mono_ai_budget_bot.nlq.executor import execute_intent
from mono_ai_budget_bot.nlq.memory_store import (
    get_pending_manual_mode,
    load_memory,
    pending_is_alive,
    pop_pending_action,
    pop_pending_manual_mode,
    save_category_alias,
    save_memory,
    save_recipient_alias,
)
from mono_ai_budget_bot.nlq.resolver import resolve
from mono_ai_budget_bot.nlq.router import route
from mono_ai_budget_bot.nlq.text_norm import norm
from mono_ai_budget_bot.nlq.types import (
    CanonicalQuerySchema,
    NLQIntent,
    NLQRequest,
    NLQResponse,
    NLQResult,
)
from mono_ai_budget_bot.storage.report_store import ReportStore
from mono_ai_budget_bot.storage.tx_store import TxRecord, TxStore
from mono_ai_budget_bot.storage.user_store import UserStore


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

RouteStrategy = Literal["deterministic", "planner", "tool_mode", "none"]

_OPEN_ENDED_FINANCE_RE = re.compile(
    r"\b("
    r"звичк|звички|"
    r"поведінк|патерн|"
    r"що\s+це\s+говорить|what\s+does\s+this\s+say|"
    r"людськ\w*\s+мов|human\s+language|"
    r"м'?які\s+висновк|soft\s+conclusion|"
    r"як\s+коуч|as\s+coach|coach|"
    r"підсумуй|сформулюй|опиши|describe|formulate|summari[sz]e|"
    r"аналіз|analysis"
    r")\b",
    re.IGNORECASE,
)

_HUMAN_TONE_RE = re.compile(
    r"\b("
    r"людськ\w*\s+мов|human\s+language|"
    r"м'?яко|м'?які\s+висновк|soft|"
    r"як\s+коуч|as\s+coach|coach"
    r")\b",
    re.IGNORECASE,
)

_BRIEF_TONE_RE = re.compile(r"\b(коротко|brief|short)\b", re.IGNORECASE)

_MULTI_CLAUSE_RE = re.compile(
    r"\b(і|та|and)\b.*\b(що\s+це\s+говорить|поясни|опиши|підсумуй|сформулюй|formulate|summari[sz]e|describe)\b",
    re.IGNORECASE,
)

_ABSTRACT_FINANCE_RE = re.compile(
    r"\b(звичк|поведінк|патерн|інсайт|висновк|аналіз)\b",
    re.IGNORECASE,
)

_NARRATIVE_ONLY_RE = re.compile(
    r"\b("
    r"опиши|describe|"
    r"підсумуй|сформулюй|formulate|summari[sz]e|"
    r"що\s+це\s+говорить|what\s+does\s+this\s+say|"
    r"людськ\w*\s+мов|human\s+language|"
    r"м'?які\s+висновк|soft\s+conclusion|"
    r"як\s+коуч|as\s+coach|coach"
    r")\b",
    re.IGNORECASE,
)

_FINANCE_SUBJECT_RE = re.compile(
    r"\b("
    r"витрат\w*|доход\w*|переказ\w*|"
    r"категор\w*|мерчант\w*|магазин\w*|покупк\w*|"
    r"бюджет\w*|фінанс\w*|грош\w*"
    r")\b",
    re.IGNORECASE,
)

_TOOL_MODE_HINT_RE = re.compile(
    r"\b("
    r"топ|top|"
    r"розбий|розклади|break\s*down|"
    r"покажи\s+останні|show\s+last|last\s+\d+|"
    r"по\s+категоріях\s+і\s+мерчантах|"
    r"по\s+категоріях\s+та\s+мерчантах|"
    r"по\s+категоріях\s+і\s+магазинах|"
    r"список|list|"
    r"найбільші|найкрупніші|largest"
    r")\b",
    re.IGNORECASE,
)

_ALLOWED_PLANNER_KEYS = {
    "intent",
    "days",
    "start_ts",
    "end_ts",
    "merchant_contains",
    "recipient_alias",
    "period_label",
    "category",
    "entity_kind",
    "threshold_uah",
}

_ALLOWED_PLANNER_INTENTS = {
    "unsupported",
    "spend_sum",
    "spend_count",
    "income_sum",
    "income_count",
    "transfer_out_sum",
    "transfer_out_count",
    "transfer_in_sum",
    "transfer_in_count",
    "compare_to_baseline",
    "threshold_query",
    "count_over",
    "count_under",
    "last_time",
    "recurrence_summary",
    "what_if",
    "currency_convert",
}


def _planner_slots_to_dict(raw: object) -> dict | None:
    if hasattr(raw, "model_dump") and callable(raw.model_dump):
        try:
            data = raw.model_dump(exclude_none=True)
        except TypeError:
            data = raw.model_dump()
    else:
        data = raw

    if not isinstance(data, dict):
        return None

    if "tool" in data or "args" in data:
        return None

    keys = {str(k) for k in data.keys()}
    if not keys.issubset(_ALLOWED_PLANNER_KEYS):
        return None

    intent = str(data.get("intent") or "").strip()
    if not intent or intent not in _ALLOWED_PLANNER_INTENTS:
        return None

    return dict(data)


def _is_tool_mode_candidate(text: str) -> bool:
    s = (text or "").strip()
    if not s:
        return False
    return _TOOL_MODE_HINT_RE.search(s) is not None


def _facts_scope_from_intent(intent_name: str | None) -> str:
    name = str(intent_name or "").strip()
    if name.endswith("_sum"):
        return "amount"
    if name.endswith("_count"):
        return "count"
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
    if name in {
        "spend_summary_short",
        "spend_insights_three",
        "spend_unusual_summary",
    }:
        return "summary"
    if name == "explain_growth":
        return "explanation"
    if name == "what_if":
        return "simulation"
    if name == "currency_convert":
        return "conversion"
    return "unknown"


def _entity_scope_from_slots(slots: dict[str, object]) -> str:
    has_category = isinstance(slots.get("category"), str) and bool(
        str(slots.get("category") or "").strip()
    )
    has_merchant = isinstance(slots.get("merchant_contains"), str) and bool(
        str(slots.get("merchant_contains") or "").strip()
    )
    has_recipient = isinstance(slots.get("recipient_alias"), str) and bool(
        str(slots.get("recipient_alias") or "").strip()
    )

    scopes: list[str] = []
    if has_category:
        scopes.append("category")
    if has_merchant:
        scopes.append("merchant")
    if has_recipient:
        scopes.append("recipient")

    if len(scopes) > 1:
        return "mixed"
    if scopes:
        return scopes[0]

    entity_kind = str(slots.get("entity_kind") or "").strip()
    if entity_kind in {"spend", "income", "transfer_out", "transfer_in"}:
        return entity_kind
    return "unknown"


def _comparison_mode_from_intent(intent_name: str | None) -> str:
    name = str(intent_name or "").strip()
    if name == "compare_to_baseline":
        return "baseline"
    if name == "compare_to_previous_period":
        return "previous_period"
    if name == "count_over":
        return "threshold_over"
    if name == "count_under":
        return "threshold_under"
    if name == "what_if":
        return "simulation"
    return "none"


def _output_mode_from_schema(text: str, facts_scope: str) -> str:
    s = text or ""
    if facts_scope == "conversion":
        return "conversion"
    if facts_scope in {"summary", "ranking"} and re.search(
        r"\b(список|list|топ|top|покажи\s+останні|show\s+last)\b",
        s,
        re.IGNORECASE,
    ):
        return "list"
    if facts_scope == "ranking":
        return "list"
    if facts_scope == "explanation":
        return "explanation"
    if facts_scope == "summary":
        return "summary"
    if facts_scope in {
        "amount",
        "count",
        "comparison",
        "share",
        "threshold",
        "recurrence",
        "recent_event",
        "simulation",
    }:
        return "numeric"
    return "unknown"


def _tone_style_from_text(text: str) -> str:
    s = text or ""
    if _HUMAN_TONE_RE.search(s):
        return "coach" if re.search(r"\b(коуч|coach)\b", s, re.IGNORECASE) else "human"
    if _BRIEF_TONE_RE.search(s):
        return "brief"
    if re.search(r"\b(чому|why|поясни|explain|аналіз|analysis)\b", s, re.IGNORECASE):
        return "analytical"
    return "neutral"


def _build_canonical_query_schema(
    req: NLQRequest,
    deterministic_intent: NLQIntent | None,
) -> CanonicalQuerySchema:
    slots = deterministic_intent.slots if deterministic_intent is not None else {}
    intent_name = deterministic_intent.name if deterministic_intent is not None else None
    facts_scope = _facts_scope_from_intent(intent_name)
    return CanonicalQuerySchema(
        facts_scope=facts_scope,
        entity_scope=_entity_scope_from_slots(slots),
        period={
            "days": slots.get("days"),
            "start_ts": slots.get("start_ts"),
            "end_ts": slots.get("end_ts"),
            "label": slots.get("period_label"),
        },
        comparison_mode=_comparison_mode_from_intent(intent_name),
        output_mode=_output_mode_from_schema(req.text, facts_scope),
        tone_style=_tone_style_from_text(req.text),
    )


def _should_handoff_deterministic_intent(
    req: NLQRequest,
    deterministic_intent: NLQIntent,
    schema: CanonicalQuerySchema,
) -> bool:
    text = req.text or ""

    if _OPEN_ENDED_FINANCE_RE.search(text):
        return True

    if _MULTI_CLAUSE_RE.search(text):
        return True

    if schema.entity_scope == "mixed":
        return True

    if schema.facts_scope == "unknown" or schema.output_mode == "unknown":
        return True

    if schema.facts_scope in {"summary", "explanation"} and schema.tone_style in {
        "coach",
        "human",
    }:
        return True

    if schema.facts_scope in {"amount", "count"} and _ABSTRACT_FINANCE_RE.search(text):
        return True

    if deterministic_intent.name in {"spend_sum", "spend_count"} and schema.tone_style in {
        "coach",
        "human",
    }:
        return True

    return False


def _select_execution_route(
    req: NLQRequest,
    deterministic_intent: NLQIntent | None,
) -> RouteStrategy:
    if deterministic_intent is not None:
        schema = _build_canonical_query_schema(req, deterministic_intent)
        if not _should_handoff_deterministic_intent(req, deterministic_intent, schema):
            return "deterministic"
    if _is_out_of_scope_for_llm(req.text):
        return "none"
    if _is_tool_mode_candidate(req.text):
        return "tool_mode"
    return "planner"


def _needs_open_question_clarification(
    req: NLQRequest,
    deterministic_intent: NLQIntent | None,
) -> bool:
    if deterministic_intent is not None:
        return False
    if not _is_narrative_candidate(req):
        return False
    return _FINANCE_SUBJECT_RE.search(req.text or "") is None


def _open_question_clarification_text(
    req: NLQRequest,
    deterministic_intent: NLQIntent | None,
) -> str | None:
    if not _needs_open_question_clarification(req, deterministic_intent):
        return None
    return (
        "Уточни, будь ласка, що саме проаналізувати: витрати, доходи чи перекази. "
        "Можеш також додати період, наприклад за місяць або за 7 днів."
    )


def _select_answer_policy(
    req: NLQRequest,
    deterministic_intent: NLQIntent | None,
) -> Literal["deterministic", "safe_llm", "clarification", "none"]:
    if deterministic_intent is not None:
        schema = _build_canonical_query_schema(req, deterministic_intent)
        if not _should_handoff_deterministic_intent(req, deterministic_intent, schema):
            return "deterministic"
    if _is_out_of_scope_for_llm(req.text):
        return "none"
    if _needs_open_question_clarification(req, deterministic_intent):
        return "clarification"
    return "safe_llm"


def _llm_cooldown_ok(user_id: int, now_ts: int, seconds: int = 10) -> bool:
    seconds = max(5, min(int(seconds), 120))
    last = int(_LLM_LAST_TS.get(int(user_id), 0))
    if int(now_ts) - last < seconds:
        return False
    _LLM_LAST_TS[int(user_id)] = int(now_ts)
    return True


def _llm_tool_mode_intent(req: NLQRequest) -> NLQIntent | None:
    return None


def _is_narrative_candidate(req: NLQRequest) -> bool:
    text = req.text or ""
    return _NARRATIVE_ONLY_RE.search(text) is not None


def _llm_plan_intent(req: NLQRequest) -> NLQIntent | None:
    if _is_out_of_scope_for_llm(req.text):
        return None
    if not _llm_cooldown_ok(req.telegram_user_id, req.now_ts, seconds=10):
        return None
    client = _get_llm_client()
    if client is None:
        return None

    try:
        raw = client.plan_nlq(user_text=req.text, now_ts=req.now_ts)
    except Exception:
        return None

    slots = _planner_slots_to_dict(raw)
    if not slots:
        return None

    name = str(slots.get("intent") or "").strip()
    if not name or name == "unsupported":
        return None

    return NLQIntent(name=name, slots=slots)


def _narrative_period_from_text(text: str) -> str:
    s = (text or "").lower()
    if re.search(r"\b(сьогодні|сьогоднішн\w*|today)\b", s, re.IGNORECASE):
        return "today"
    if re.search(r"\b(тиж|week)\b", s, re.IGNORECASE):
        return "week"
    return "month"


def _schema_to_payload(schema: CanonicalQuerySchema) -> dict[str, object]:
    return {
        "facts_scope": schema.facts_scope,
        "entity_scope": schema.entity_scope,
        "period": dict(schema.period),
        "comparison_mode": schema.comparison_mode,
        "output_mode": schema.output_mode,
        "tone_style": schema.tone_style,
    }


def _load_narrative_facts(req: NLQRequest) -> dict[str, object] | None:
    period = _narrative_period_from_text(req.text)
    try:
        payload = execute_tool_call(
            req.telegram_user_id,
            tool="query_facts",
            args={
                "period": period,
                "keys": [
                    "totals",
                    "comparison",
                    "top_categories_named_real_spend",
                    "top_merchants_real_spend",
                    "coverage",
                    "requested_period_label",
                    "transactions_count",
                ],
            },
            report_store=ReportStore(),
            now_ts=req.now_ts,
        )
    except Exception:
        return None

    facts = payload.get("facts")
    if not isinstance(facts, dict):
        return None
    if not isinstance(facts.get("totals"), dict):
        return None

    return payload


def _missing_narrative_facts_text(req: NLQRequest) -> str:
    period = _narrative_period_from_text(req.text)
    label = {
        "today": "сьогодні",
        "week": "тиждень",
        "month": "місяць",
    }[period]
    return (
        "Можу описати твої витрати людською мовою або сформулювати м'які висновки, "
        f"але зараз у мене немає підготовлених фактів за {label}. "
        "Спочатку онови дані або підготуй звіт за цей період, а потім повтори запит."
    )


def _llm_narrative_response(
    req: NLQRequest,
    deterministic_intent: NLQIntent | None,
) -> NLQResponse | None:
    if _is_out_of_scope_for_llm(req.text):
        return None

    client = _get_llm_client()
    if client is None:
        return None

    schema = _build_canonical_query_schema(req, deterministic_intent)
    facts_payload = _load_narrative_facts(req)
    if facts_payload is None:
        return NLQResponse(
            result=NLQResult(text=_missing_narrative_facts_text(req)),
            clarification=None,
        )

    try:
        raw = client.interpret_nlq(
            user_text=req.text,
            schema=_schema_to_payload(schema),
            facts_payload=facts_payload,
        )
    except Exception:
        return None

    mode = str(raw.get("mode") or "").strip()
    if mode == "narrative":
        answer = str(raw.get("answer") or "").strip()
        if not answer:
            return None
        return NLQResponse(
            result=NLQResult(
                text=answer,
                meta={
                    "mode": "llm_narrative",
                    "period": _narrative_period_from_text(req.text),
                },
            ),
            clarification=None,
        )

    if mode == "clarify":
        question = str(raw.get("question") or "").strip()
        if not question:
            return None
        return NLQResponse(
            result=NLQResult(
                text=question,
                meta={
                    "mode": "llm_clarify",
                    "period": _narrative_period_from_text(req.text),
                },
            ),
            clarification=None,
        )

    return None


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


def _load_validation_rows(user_id: int, now_ts: int, days: int = 180) -> list[TxRecord]:
    days = max(7, min(int(days), 365))
    cfg = UserStore().load(int(user_id))
    if cfg is None or not cfg.mono_token:
        return []
    account_ids = cfg.selected_account_ids or []
    if not account_ids:
        return []

    ts_to = int(now_ts)
    ts_from = max(0, ts_to - days * 86400)
    return TxStore().load_range(
        telegram_user_id=int(user_id),
        account_ids=list(account_ids),
        ts_from=ts_from,
        ts_to=ts_to,
    )


def _top_merchants(rows: list[TxRecord], query: str, limit: int = 8) -> list[str]:
    q = norm(query)
    if not q:
        return []
    qk = q.replace(" ", "")
    scores: dict[str, int] = {}

    for r in rows:
        kind = classify_kind(r.amount, r.mcc, r.description)
        if kind != "spend":
            continue
        desc = (r.description or "").strip()
        if not desc:
            continue
        dk = norm(desc).replace(" ", "")
        if qk not in dk:
            continue
        scores[desc] = scores.get(desc, 0) + abs(int(r.amount))

    items = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [k for k, _ in items[: max(1, min(int(limit), 15))]]


def _top_recipients(
    rows: list[TxRecord], query: str, *, kind_prefix: str | None, limit: int = 8
) -> list[str]:
    q = norm(query)
    if not q:
        return []
    qk = q.replace(" ", "")
    scores: dict[str, int] = {}

    for r in rows:
        kind = classify_kind(r.amount, r.mcc, r.description)
        if kind_prefix == "transfer_out" and kind != "transfer_out":
            continue
        if kind_prefix == "transfer_in" and kind != "transfer_in":
            continue
        if kind_prefix is None and kind not in {"transfer_out", "transfer_in"}:
            continue

        desc = (r.description or "").strip()
        if not desc:
            continue
        dk = norm(desc).replace(" ", "")
        if qk not in dk:
            continue
        scores[desc] = scores.get(desc, 0) + abs(int(r.amount))

    items = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [k for k, _ in items[: max(1, min(int(limit), 15))]]


def _seen_categories(rows: list[TxRecord]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for r in rows:
        if r.mcc is None:
            continue
        c = category_from_mcc(r.mcc)
        if not c:
            continue
        key = c.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def _recipient_has_ledger_evidence(
    rows: list[TxRecord],
    *,
    value: str,
    pending_intent: dict | None,
) -> bool:
    s = norm(value)
    if not s:
        return False

    kind_prefix: str | None = None
    if isinstance(pending_intent, dict):
        intent_name = str(pending_intent.get("intent") or "")
        if intent_name.startswith("transfer_out"):
            kind_prefix = "transfer_out"
        elif intent_name.startswith("transfer_in"):
            kind_prefix = "transfer_in"

    for cand in _top_recipients(rows, value, kind_prefix=kind_prefix, limit=50):
        cand_norm = norm(cand)
        if cand_norm == s or s in cand_norm:
            return True
    return False


def _manual_entry_try_resolve(
    *,
    expected: str,
    user_text: str,
    pending_intent: dict | None,
    pending_options: list[str] | None,
    rows: list[TxRecord],
) -> tuple[str | None, list[str] | None, str | None]:
    s = (user_text or "").strip()
    if not s:
        return None, None, "Порожнє значення."

    if pending_options and s.isdigit():
        idx = int(s)
        if 1 <= idx <= len(pending_options):
            return pending_options[idx - 1].strip(), None, None

    expected = (expected or "").strip()

    if expected == "category":
        cats = _seen_categories(rows)
        low = s.lower()
        for c in cats:
            if c.lower() == low:
                return c, None, None
        sugg = [c for c in cats if norm(low) and norm(low) in norm(c)]
        sugg = sugg[:8]
        return None, (sugg or None), "Не знайшов таку категорію в твоїх транзакціях."

    kind_prefix: str | None = None
    if isinstance(pending_intent, dict):
        intent_name = str(pending_intent.get("intent") or "")
        if intent_name.startswith("transfer_out"):
            kind_prefix = "transfer_out"
        elif intent_name.startswith("transfer_in"):
            kind_prefix = "transfer_in"

    if expected == "recipient":
        for cand in _top_recipients(rows, s, kind_prefix=kind_prefix, limit=15):
            if cand.lower() == s.lower():
                return cand, None, None
        sugg = _top_recipients(rows, s, kind_prefix=kind_prefix, limit=8)
        return None, (sugg or None), "Не знайшов такого отримувача в виписці."

    for cand in _top_merchants(rows, s, limit=15):
        if cand.lower() == s.lower():
            return cand, None, None

    sugg = _top_merchants(rows, s, limit=8)
    if not sugg and kind_prefix is not None:
        sugg = _top_recipients(rows, s, kind_prefix=kind_prefix, limit=8)

    return None, (sugg or None), "Не знайшов таку назву в твоїх транзакціях."


def handle_nlq(req: NLQRequest) -> NLQResponse:
    mem = load_memory(req.telegram_user_id)
    manual_mode = get_pending_manual_mode(req.telegram_user_id, now_ts=req.now_ts)
    if manual_mode is not None:
        expected = str(manual_mode.get("expected") or "").strip() or "merchant_or_recipient"
        pending = mem.get("pending_intent")
        pending_options = mem.get("pending_options")
        options: list[str] | None
        if isinstance(pending_options, list):
            options = [x.strip() for x in pending_options if isinstance(x, str) and x.strip()]
            if not options:
                options = None
        else:
            options = None

        rows = _load_validation_rows(req.telegram_user_id, req.now_ts)
        selected, suggested, err = _manual_entry_try_resolve(
            expected=expected,
            user_text=req.text,
            pending_intent=pending if isinstance(pending, dict) else None,
            pending_options=options,
            rows=rows,
        )

        if selected:
            pop_pending_manual_mode(req.telegram_user_id)
            req = NLQRequest(
                telegram_user_id=req.telegram_user_id,
                text=selected,
                now_ts=req.now_ts,
            )
            mem = load_memory(req.telegram_user_id)
        else:
            if suggested:
                mem["pending_options"] = list(suggested)
                save_memory(req.telegram_user_id, mem)
                lines = [
                    (err or "Не знайшов відповідність."),
                    "Вибери номер або введи точну назву як у виписці:",
                ]
                for i, opt in enumerate(suggested, start=1):
                    lines.append(f"{i}) {opt}")
                return NLQResponse(result=NLQResult(text="\\n".join(lines)), clarification=None)

            return NLQResponse(
                result=NLQResult(text=(err or "Не знайшов відповідність.")),
                clarification=None,
            )

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

        if pending_kind == "recipient":
            alias = _extract_recipient_alias(pending)
            if alias and req.text.strip().lower() in {
                "0",
                "cancel",
                "скасувати",
                "ні",
                "нет",
            }:
                pop_pending_action(req.telegram_user_id)
                return NLQResponse(result=NLQResult(text="Ок, не зберігаю."), clarification=None)

            rows = _load_validation_rows(req.telegram_user_id, req.now_ts)
            match_value = _resolve_followup_value(req.text, options).strip()

            if (
                alias
                and match_value
                and _recipient_has_ledger_evidence(
                    rows,
                    value=match_value,
                    pending_intent=pending,
                )
            ):
                save_recipient_alias(req.telegram_user_id, alias, match_value)
                pop_pending_action(req.telegram_user_id)
                text = execute_intent(req.telegram_user_id, pending)
                return NLQResponse(result=NLQResult(text=text), clarification=None)

            selected, suggested, err = _manual_entry_try_resolve(
                expected="recipient",
                user_text=req.text,
                pending_intent=pending,
                pending_options=options,
                rows=rows,
            )

            if (
                alias
                and selected
                and _recipient_has_ledger_evidence(
                    rows,
                    value=selected,
                    pending_intent=pending,
                )
            ):
                save_recipient_alias(req.telegram_user_id, alias, selected)
                pop_pending_action(req.telegram_user_id)
                text = execute_intent(req.telegram_user_id, pending)
                return NLQResponse(result=NLQResult(text=text), clarification=None)

            if suggested:
                mem["pending_options"] = list(suggested)
                save_memory(req.telegram_user_id, mem)
                lines = [
                    (err or "Не знайшов відповідність."),
                    "Вибери номер або введи точне ім'я як у виписці:",
                ]
                for i, opt in enumerate(suggested, start=1):
                    lines.append(f"{i}) {opt}")
                return NLQResponse(result=NLQResult(text="\n".join(lines)), clarification=None)

            return NLQResponse(
                result=NLQResult(text=(err or "Не знайшов такого отримувача в виписці.")),
                clarification=None,
            )

    deterministic_intent = route(req)
    policy = _select_answer_policy(req, deterministic_intent)
    strategy = _select_execution_route(req, deterministic_intent)

    intent: NLQIntent | None
    narrative_resp: NLQResponse | None = None

    if policy == "deterministic":
        intent = deterministic_intent
    elif policy == "clarification":
        text = _open_question_clarification_text(req, deterministic_intent)
        return NLQResponse(
            result=NLQResult(text=(text or "Уточни, будь ласка, свій запит.")),
            clarification=None,
        )
    elif policy == "safe_llm":
        if strategy == "tool_mode":
            intent = _llm_tool_mode_intent(req)
            if intent is None:
                intent = _llm_plan_intent(req)
            if intent is None and _is_narrative_candidate(req):
                narrative_resp = _llm_narrative_response(req, deterministic_intent)
        elif strategy == "planner":
            intent = _llm_plan_intent(req)
            if intent is None and _is_narrative_candidate(req):
                narrative_resp = _llm_narrative_response(req, deterministic_intent)
        else:
            intent = None
    else:
        intent = None

    if not intent:
        if narrative_resp is not None:
            return narrative_resp
        return NLQResponse(result=None, clarification=None)

    intent = resolve(req, intent)
    text = execute_intent(req.telegram_user_id, intent.slots)
    return NLQResponse(result=NLQResult(text=text), clarification=None)
