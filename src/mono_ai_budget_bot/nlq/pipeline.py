from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from mono_ai_budget_bot.bot import templates
from mono_ai_budget_bot.config import load_settings
from mono_ai_budget_bot.llm.openai_client import OpenAIClient
from mono_ai_budget_bot.llm.tooling import execute_tool_call
from mono_ai_budget_bot.nlq.executor import execute_intent
from mono_ai_budget_bot.nlq.memory_store import (
    get_pending_contract,
    get_pending_manual_mode,
    load_memory,
    pop_pending_action,
    pop_pending_manual_mode,
    save_category_alias,
    save_memory,
    save_recipient_alias,
    update_pending_options,
)
from mono_ai_budget_bot.nlq.models import (
    AnswerStrategy,
    CanonicalQuery,
    QueryIntent,
    Slots,
    canonical_intent_family,
)
from mono_ai_budget_bot.nlq.resolver import resolve, resolve_canonical
from mono_ai_budget_bot.nlq.router import route
from mono_ai_budget_bot.nlq.types import (
    CanonicalQuerySchema,
    NLQIntent,
    NLQRequest,
    NLQResponse,
    NLQResult,
)
from mono_ai_budget_bot.settings.ai_features import (
    ai_feature_enabled,
    normalize_ai_features_settings,
)
from mono_ai_budget_bot.storage.profile_store import ProfileStore
from mono_ai_budget_bot.storage.report_store import ReportStore
from mono_ai_budget_bot.storage.tx_store import TxStore
from mono_ai_budget_bot.storage.user_store import UserStore

from .pipeline_followups import (
    extract_recipient_alias as _extract_recipient_alias,
)
from .pipeline_followups import (
    is_paging_continue as _is_paging_continue,
)
from .pipeline_followups import (
    manual_entry_try_resolve as _manual_entry_try_resolve,
)
from .pipeline_followups import (
    parse_multi_select as _parse_multi_select,
)
from .pipeline_followups import (
    recipient_has_ledger_evidence as _recipient_has_ledger_evidence,
)
from .pipeline_followups import (
    resolve_followup_value as _resolve_followup_value,
)
from .pipeline_tool_mode import (
    build_tool_mode_prompt_user as _tool_mode_prompt_user_external,
)
from .pipeline_tool_mode import (
    coerce_tool_mode_result as _coerce_tool_mode_result,
)
from .pipeline_tool_mode import (
    render_tool_payload as _render_tool_payload,
)
from .pipeline_tool_mode import (
    tool_call_is_safe as _tool_call_is_safe,
)
from .pipeline_tool_mode import (
    tool_mode_empty_text as _tool_mode_empty_text,
)
from .pipeline_tool_mode import (
    tool_mode_invalid_text as _tool_mode_invalid_text,
)
from .pipeline_tool_mode import (
    tool_payload_has_data as _tool_payload_has_data,
)


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
    r"м'?які\s+висновк|висновк|soft\s+conclusion|"
    r"як\s+коуч|as\s+coach|coach|"
    r"підсумуй|сформулюй|опиши|describe|formulate|summari[sz]e|"
    r"куди\s+.*йдуть\s+грош\w*|на\s+що\s+.*йдуть\s+грош\w*|"
    r"що\s+добре|що\s+погано|на\s+що\s+звернути\s+увагу|"
    r"який\s+один\s+.*крок|найреалістичн\w*\s+крок|без\s+сильн\w*\s+дискомфорт\w*|"
    r"чим\s+.*відрізня\w*\s+від\s+попередн\w*|"
    r"регулярн\w*\s+повсякденн\w*|"
    r"разов\w*\s+велик\w*\s+покупк\w*|"
    r"one\s*off|regular\s+everyday|"
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

_SEMANTIC_REASONING_RE = re.compile(
    r"\b("
    r"патерн\w*|звичк\w*|поведінк\w*|"
    r"регулярн\w*|разов\w*|one\s*off|recurring|habit\w*|pattern\w*|"
    r"аномал\w*|незвичн\w*|interpret\w*|інтерпрет\w*|"
    r"що\s+це\s+говорить|"
    r"наскільки\s+більше|наскільки\s+частіше|частіше|рідше|зазвичай|"
    r"більше\s+йде\s+на|"
    r"куди\s+.*йдуть\s+грош\w*|на\s+що\s+.*йдуть\s+грош\w*|"
    r"що\s+добре|що\s+погано|на\s+що\s+звернути\s+увагу|"
    r"який\s+один\s+.*крок|найреалістичн\w*\s+крок|без\s+сильн\w*\s+дискомфорт\w*|"
    r"чим\s+.*відрізня\w*\s+від\s+попередн\w*|"
    r"коротко\s+і\s+по\s+суті|"
    r"чому\s+саме|поясни\s+чому|"
    r"порівняй.*(novus|atb|мак|kfc)|"
    r"курс\w*|валют\w*|currency"
    r")\b",
    re.IGNORECASE,
)

_NARRATIVE_ONLY_RE = re.compile(
    r"\b("
    r"опиши|describe|"
    r"підсумуй|сформулюй|formulate|summari[sz]e|"
    r"що\s+це\s+говорить|what\s+does\s+this\s+say|"
    r"людськ\w*\s+мов|human\s+language|"
    r"м'?які\s+висновк|висновк|soft\s+conclusion|"
    r"як\s+коуч|as\s+coach|coach|"
    r"куди\s+.*йдуть\s+грош\w*|на\s+що\s+.*йдуть\s+грош\w*|"
    r"що\s+добре|що\s+погано|на\s+що\s+звернути\s+увагу|"
    r"який\s+один\s+.*крок|найреалістичн\w*\s+крок|без\s+сильн\w*\s+дискомфорт\w*|"
    r"чим\s+.*відрізня\w*\s+від\s+попередн\w*|"
    r"регулярн\w*\s+повсякденн\w*|разов\w*\s+велик\w*\s+покупк\w*|one\s*off|regular\s+everyday|"
    r"патерн\w*|звичк\w*|поведінк\w*|"
    r"наскільки\s+більше|наскільки\s+частіше|частіше|рідше|зазвичай|"
    r"поясни\s+чому|інтерпрет\w*|аномал\w*|незвичн\w*|"
    r"курс\w*|валют\w*|currency"
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
    "currency_rate",
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


def _normalize_text_value(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _detect_canonical_intent(req: NLQRequest) -> CanonicalQuery:
    normalized = _normalize_text_value(req.text)
    routed = route(
        NLQRequest(telegram_user_id=req.telegram_user_id, text=normalized, now_ts=req.now_ts)
    )
    if routed is None:
        return CanonicalQuery(
            raw_text=req.text,
            normalized_text=normalized,
            intent=None,
            slots=Slots({}),
        )

    return CanonicalQuery(
        raw_text=req.text,
        normalized_text=normalized,
        intent=QueryIntent(name=routed.name, family=canonical_intent_family(routed.name)),
        slots=Slots(dict(routed.slots or {})),
    )


def _resolve_canonical_query(req: NLQRequest, query: CanonicalQuery):
    if query.intent is None:
        return None
    return resolve_canonical(
        NLQRequest(
            telegram_user_id=req.telegram_user_id, text=query.normalized_text, now_ts=req.now_ts
        ),
        NLQIntent(name=query.intent.name, slots=query.slots.to_payload()),
    )


def _choose_answer_strategy(
    req: NLQRequest,
    deterministic_intent: NLQIntent | None,
) -> AnswerStrategy:
    policy = _select_answer_policy(req, deterministic_intent)
    if policy == "deterministic":
        return AnswerStrategy(mode="deterministic", reason="canonical_deterministic")
    if policy == "clarification":
        return AnswerStrategy(mode="clarify", reason="semantic_ambiguity")
    if policy == "safe_llm":
        return AnswerStrategy(mode="llm", reason=_select_execution_route(req, deterministic_intent))
    return AnswerStrategy(mode="none", reason="no_safe_route")


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
    if name in {"currency_convert", "currency_rate"}:
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

    if _SEMANTIC_REASONING_RE.search(text):
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

    semantic_enabled = _ai_feature_enabled_for_user(req.telegram_user_id, "semantic_fallback")
    tool_mode_enabled = _ai_feature_enabled_for_user(req.telegram_user_id, "tool_mode")

    if _is_tool_mode_candidate(req.text):
        if tool_mode_enabled:
            return "tool_mode"
        return "planner" if semantic_enabled else "none"

    if not semantic_enabled:
        return "none"
    return "planner"


def _needs_open_question_clarification(
    req: NLQRequest,
    deterministic_intent: NLQIntent | None,
) -> bool:
    if deterministic_intent is not None:
        return False
    if not _is_narrative_candidate(req):
        return False

    text = req.text or ""

    if _SEMANTIC_REASONING_RE.search(text):
        return False

    if _FINANCE_SUBJECT_RE.search(text):
        return False

    return _OPEN_ENDED_FINANCE_RE.search(text) is not None


def _open_question_clarification_text(
    req: NLQRequest,
    deterministic_intent: NLQIntent | None,
) -> str | None:
    if not _needs_open_question_clarification(req, deterministic_intent):
        return None
    return templates.nlq_clarify_scope_message()


def _out_of_scope_response_text() -> str:
    return templates.nlq_llm_scope_guard_message()


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
    if not _ai_feature_enabled_for_user(req.telegram_user_id, "semantic_fallback"):
        return "none"
    return "safe_llm"


def _llm_cooldown_ok(user_id: int, now_ts: int, seconds: int = 10) -> bool:
    seconds = max(5, min(int(seconds), 120))
    last = int(_LLM_LAST_TS.get(int(user_id), 0))
    if int(now_ts) - last < seconds:
        return False
    _LLM_LAST_TS[int(user_id)] = int(now_ts)
    return True


def _load_ai_profile(user_id: int) -> dict[str, object]:
    store = ProfileStore(Path(".cache") / "profiles")
    return normalize_ai_features_settings(store.load(user_id) or {})


def _ai_feature_enabled_for_user(user_id: int, key: str) -> bool:
    try:
        return ai_feature_enabled(_load_ai_profile(user_id), key)
    except Exception:
        return True


def _narrative_feature_key(
    req: NLQRequest,
    deterministic_intent: NLQIntent | None,
) -> str:
    schema = _build_canonical_query_schema(req, deterministic_intent)
    if schema.output_mode == "summary" or schema.facts_scope == "summary":
        return "ai_summaries"
    return "ai_insights_wording"


def _tool_mode_prompt_system() -> str:
    return (
        "Ти safe tool-router для персональної фінансової аналітики. "
        "Ти не рахуєш гроші самостійно, не пишеш у storage, не працюєш із секретами, токенами або raw транзакціями. "
        "Ти можеш повернути тільки strict JSON з полем tool_calls. "
        "Кожен tool_call має містити тільки allowlisted tool і тільки безпечні args. "
        "Якщо запит надто неоднозначний або не вкладається в allowlist, поверни мінімально достатній allowlisted tool call."
    )


def _tool_mode_prompt_user(req: NLQRequest) -> str:
    schema = _schema_to_payload(_build_canonical_query_schema(req, None))
    return _tool_mode_prompt_user_external(req, schema)


def _llm_tool_mode_intent(req: NLQRequest) -> NLQIntent | NLQResponse | None:
    if _is_out_of_scope_for_llm(req.text):
        return None
    if not _llm_cooldown_ok(req.telegram_user_id, req.now_ts, seconds=10):
        return None
    client = _get_llm_client()
    if client is None:
        return None

    try:
        raw = client.tool_mode(_tool_mode_prompt_system(), _tool_mode_prompt_user(req))
    except Exception:
        return NLQResponse(result=NLQResult(text=_tool_mode_invalid_text()), clarification=None)

    calls = _coerce_tool_mode_result(raw)
    if not calls:
        return NLQResponse(result=NLQResult(text=_tool_mode_invalid_text()), clarification=None)

    executed: list[dict[str, Any]] = []
    for tool, args in calls:
        if not _tool_call_is_safe(tool, args):
            return NLQResponse(result=NLQResult(text=_tool_mode_invalid_text()), clarification=None)
        try:
            executed.append(
                execute_tool_call(
                    req.telegram_user_id,
                    tool=tool,
                    args=args,
                    users=UserStore(),
                    report_store=ReportStore(),
                    tx_store=TxStore(),
                    now_ts=req.now_ts,
                )
            )
        except Exception:
            return NLQResponse(result=NLQResult(text=_tool_mode_invalid_text()), clarification=None)

    if not any(_tool_payload_has_data(payload) for payload in executed):
        return NLQResponse(result=NLQResult(text=_tool_mode_empty_text()), clarification=None)

    lines = [
        "Використав safe AI-assisted tool path.",
        "AI лише вибрав дозволені інструменти, а всі факти нижче детерміновано отримані кодом.",
        "",
    ]
    for payload in executed:
        rendered = _render_tool_payload(payload)
        if rendered:
            lines.extend(rendered)
            lines.append("")

    while lines and not lines[-1]:
        lines.pop()

    return NLQResponse(
        result=NLQResult(
            text="\n".join(lines),
            meta={
                "mode": "llm_tool_mode",
                "tools": [tool for tool, _ in calls],
            },
        ),
        clarification=None,
    )


def _is_narrative_candidate(req: NLQRequest) -> bool:
    text = req.text or ""
    return (
        _NARRATIVE_ONLY_RE.search(text) is not None
        or _SEMANTIC_REASONING_RE.search(text) is not None
    )


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


def _semantic_period(
    req: NLQRequest,
    deterministic_intent: NLQIntent | None,
) -> str:
    schema = _build_canonical_query_schema(req, deterministic_intent)
    label = str(schema.period.get("label") or "").strip().lower()
    days = schema.period.get("days")

    if label in {"сьогодні", "вчора"}:
        return "today"
    try:
        if days is not None and int(days) <= 7:
            return "week"
    except Exception:
        pass
    return "month"


def _safe_slot_summary(deterministic_intent: NLQIntent | None) -> dict[str, object]:
    if deterministic_intent is None:
        return {}

    slots = dict(deterministic_intent.slots or {})
    allowlist = {
        "intent",
        "days",
        "period_label",
        "entity_kind",
        "category",
        "category_targets",
        "merchant_contains",
        "merchant_targets",
        "recipient_alias",
        "recipient_target",
        "recipient_targets",
        "threshold_uah",
        "direction",
        "comparison_mode",
        "aggregation",
        "target_type",
    }

    summary: dict[str, object] = {}
    for key in allowlist:
        if key not in slots:
            continue
        value = slots.get(key)
        if value in (None, "", [], {}):
            continue
        summary[key] = value
    return summary


def _load_narrative_facts(
    req: NLQRequest,
    deterministic_intent: NLQIntent | None,
) -> dict[str, object] | None:
    period = _semantic_period(req, deterministic_intent)
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

    safe_payload: dict[str, object] = {
        "tool": "query_facts",
        "period": period,
        "facts": facts,
        "slot_summary": _safe_slot_summary(deterministic_intent),
    }

    if deterministic_intent is not None:
        try:
            safe_payload["deterministic_preview"] = {
                "intent": deterministic_intent.name,
                "answer": execute_intent(
                    req.telegram_user_id, dict(deterministic_intent.slots or {})
                ),
            }
        except Exception:
            pass

    return safe_payload


def _missing_narrative_facts_text(
    req: NLQRequest,
    deterministic_intent: NLQIntent | None,
) -> str:
    period = _semantic_period(req, deterministic_intent)
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


def _strip_llm_debug_text(text: str) -> str:
    lines = [line.strip() for line in str(text or "").splitlines()]
    bad_markers = (
        "user_text=",
        "schema_json=",
        "facts_json=",
        "slot_summary",
        "merchant_targets",
        "recipient_alias",
        "threshold_uah",
        "comparison_mode",
        "target_type",
        "original_query_spec",
    )
    kept = [line for line in lines if line and not any(marker in line for marker in bad_markers)]
    cleaned = " ".join(kept) if kept else str(text or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _looks_like_total_only_llm_answer(answer: str) -> bool:
    text = str(answer or "").strip()
    if not text:
        return False
    if (
        "За останні" not in text
        and "Цього місяця" not in text
        and "Вчора" not in text
        and "Сьогодні" not in text
    ):
        return False
    insight_markers = (
        "бо ",
        "тому що",
        "схоже",
        "ймовірно",
        "це означає",
        "виглядає",
        "звич",
        "патерн",
        "регуляр",
        "разов",
        "аномал",
        "варто",
        "спробуй",
        "зверни увагу",
        "причин",
    )
    lowered = text.lower()
    return not any(marker in lowered for marker in insight_markers)


def _polish_llm_narrative_answer(answer: str, facts_payload: dict[str, object]) -> str | None:
    cleaned = _strip_llm_debug_text(answer)
    if not cleaned:
        return None

    preview = facts_payload.get("deterministic_preview")
    preview_answer = preview.get("answer") if isinstance(preview, dict) else None
    if isinstance(preview_answer, str) and cleaned == preview_answer.strip():
        return (
            "Бачу базовий підсумок по цифрах, але корисний висновок тут залежить від того, "
            "що саме тебе цікавить: патерни, причини змін чи конкретне порівняння."
        )

    if _looks_like_total_only_llm_answer(cleaned):
        return (
            "Бачу базовий підсумок по цифрах, але тут ще варто уточнити, "
            "який саме висновок тобі потрібен: патерни, звички, причини змін чи порівняння."
        )

    return cleaned


def _polish_llm_clarify_question(question: str) -> str | None:
    cleaned = _strip_llm_debug_text(question)
    if not cleaned:
        return None
    cleaned = cleaned.rstrip(". ").strip()
    if not cleaned.endswith("?"):
        cleaned = f"{cleaned}?"
    return cleaned


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
    facts_payload = _load_narrative_facts(req, deterministic_intent)
    if facts_payload is None:
        return NLQResponse(
            result=NLQResult(text=_missing_narrative_facts_text(req, deterministic_intent)),
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

    mode = str(raw.get("mode") or "").strip().lower()
    if mode == "narrative_answer":
        mode = "narrative"
    elif mode == "semantic_clarify":
        mode = "clarify"

    if mode == "narrative_answer":
        mode = "narrative"
    elif mode == "semantic_clarify":
        mode = "clarify"

    if mode == "narrative":
        answer = _polish_llm_narrative_answer(str(raw.get("answer") or ""), facts_payload)
        if not answer:
            return None
        return NLQResponse(
            result=NLQResult(
                text=answer,
                meta={
                    "mode": "llm_narrative",
                    "period": _semantic_period(req, deterministic_intent),
                },
            ),
            clarification=None,
        )

    if mode == "clarify":
        question = _polish_llm_clarify_question(str(raw.get("question") or ""))
        if not question:
            return None
        return NLQResponse(
            result=NLQResult(
                text=question,
                meta={
                    "mode": "llm_clarify",
                    "period": _semantic_period(req, deterministic_intent),
                },
            ),
            clarification=None,
        )

    if mode == "unsupported":
        return NLQResponse(
            result=NLQResult(
                text=(
                    "Зараз не можу дати коректне пояснення без ризику вигадати зайве. "
                    "Уточни період, сутність або метрику, яку хочеш інтерпретувати."
                ),
                meta={
                    "mode": "llm_unsupported",
                    "period": _semantic_period(req, deterministic_intent),
                },
            ),
            clarification=None,
        )

    return None


def _looks_like_new_nlq_question(text: str, options: list[str] | None = None) -> bool:
    s = (text or "").strip()
    if not s:
        return False

    low = s.lower()
    if low in {"0", "cancel", "скасувати", "ні", "нет"}:
        return False

    if re.fullmatch(r"\d+(?:\s*,\s*\d+)*", s):
        return False

    if options and any(low == str(opt).strip().lower() for opt in options):
        return False

    if s.endswith("?"):
        return True

    return len(s.split()) >= 4


def _load_validation_rows(user_id: int, now_ts: int, days: int = 180):
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


def _maybe_handle_open_ended_finance(req: NLQRequest, intent: NLQIntent) -> NLQResponse | None:
    if not _SEMANTIC_REASONING_RE.search(req.text or "") and not _OPEN_ENDED_FINANCE_RE.search(
        req.text or ""
    ):
        return None
    return _llm_narrative_response(req, intent)


def handle_nlq(req: NLQRequest) -> NLQResponse:
    mem = load_memory(req.telegram_user_id)
    manual_mode = get_pending_manual_mode(req.telegram_user_id, now_ts=req.now_ts)
    if manual_mode is not None:
        expected = str(manual_mode.get("expected") or "").strip() or "merchant_or_recipient"
        contract = get_pending_contract(req.telegram_user_id, now_ts=req.now_ts)
        pending = (
            contract.get("original_query_spec")
            if isinstance(contract, dict) and isinstance(contract.get("original_query_spec"), dict)
            else None
        )
        options = (
            contract.get("options")
            if isinstance(contract, dict) and isinstance(contract.get("options"), list)
            else None
        )

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
                update_pending_options(req.telegram_user_id, list(suggested))
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

    contract = get_pending_contract(req.telegram_user_id, now_ts=req.now_ts)
    pending = (
        contract.get("original_query_spec")
        if isinstance(contract, dict) and isinstance(contract.get("original_query_spec"), dict)
        else None
    )
    options = (
        contract.get("options")
        if isinstance(contract, dict) and isinstance(contract.get("options"), list)
        else None
    )
    pending_kind = contract.get("kind") if isinstance(contract, dict) else None

    if isinstance(pending, dict):
        if _looks_like_new_nlq_question(req.text, options):
            pop_pending_action(req.telegram_user_id)
            mem = load_memory(req.telegram_user_id)
            pending = None
            options = None
            pending_kind = None
        else:
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
                    return NLQResponse(
                        result=NLQResult(text="Ок, не зберігаю."), clarification=None
                    )

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
                    return NLQResponse(
                        result=NLQResult(text="Ок, не зберігаю."), clarification=None
                    )

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
                    update_pending_options(req.telegram_user_id, list(suggested))
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

    if _is_out_of_scope_for_llm(req.text):
        return NLQResponse(
            result=NLQResult(text=_out_of_scope_response_text()),
            clarification=None,
        )

    canonical_query = _detect_canonical_intent(req)
    deterministic_intent = (
        NLQIntent(name=canonical_query.intent.name, slots=canonical_query.slots.to_payload())
        if canonical_query.intent is not None
        else None
    )

    if deterministic_intent is not None:
        slots = dict(deterministic_intent.slots or {})
        if bool(slots.get("llm_candidate")) or str(slots.get("slots_confidence") or "") in {
            "low",
            "medium",
        }:
            llm_resp = _maybe_handle_open_ended_finance(req, deterministic_intent)
            if llm_resp is not None:
                return llm_resp

    strategy_decision = _choose_answer_strategy(req, deterministic_intent)

    intent: NLQIntent | None
    narrative_resp: NLQResponse | None = None

    if strategy_decision.mode == "deterministic":
        resolved_state = _resolve_canonical_query(req, canonical_query)
        intent = resolved_state.to_intent() if resolved_state is not None else deterministic_intent
    elif strategy_decision.mode == "clarify":
        text = _open_question_clarification_text(req, deterministic_intent)
        return NLQResponse(
            result=NLQResult(text=(text or "Уточни, будь ласка, свій запит.")),
            clarification=None,
        )
    elif strategy_decision.mode == "llm":
        if strategy_decision.reason == "tool_mode":
            tool_mode_out = _llm_tool_mode_intent(req)
            if isinstance(tool_mode_out, NLQResponse):
                return tool_mode_out
            intent = tool_mode_out
            if intent is None:
                intent = _llm_plan_intent(req)
            if (
                intent is None
                and _is_narrative_candidate(req)
                and _ai_feature_enabled_for_user(
                    req.telegram_user_id,
                    _narrative_feature_key(req, deterministic_intent),
                )
            ):
                narrative_resp = _llm_narrative_response(req, deterministic_intent)
        elif strategy_decision.reason == "planner":
            intent = _llm_plan_intent(req)
            if (
                intent is None
                and _is_narrative_candidate(req)
                and _ai_feature_enabled_for_user(
                    req.telegram_user_id,
                    _narrative_feature_key(req, deterministic_intent),
                )
            ):
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
