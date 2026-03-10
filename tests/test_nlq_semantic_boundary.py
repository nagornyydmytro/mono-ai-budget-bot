import pytest

import mono_ai_budget_bot.nlq.pipeline as pl
from mono_ai_budget_bot.nlq.types import NLQIntent, NLQRequest


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        (
            "скільки я витратив за 7 днів?",
            NLQIntent(name="spend_sum", slots={"intent": "spend_sum", "days": 7}),
        ),
        (
            "скільки я витратив на кафе за місяць?",
            NLQIntent(
                name="spend_sum",
                slots={
                    "intent": "spend_sum",
                    "days": 30,
                    "category": "Кафе/Ресторани",
                    "entity_kind": "spend",
                },
            ),
        ),
        (
            "скільки я витратив у novus за місяць?",
            NLQIntent(
                name="spend_sum",
                slots={
                    "intent": "spend_sum",
                    "days": 30,
                    "merchant_contains": "novus",
                    "merchant_exact": True,
                    "entity_kind": "spend",
                },
            ),
        ),
        (
            "порівняй витрати за останні 30 днів із попередніми 30 днями",
            NLQIntent(
                name="compare_to_previous_period",
                slots={"intent": "compare_to_previous_period", "days": 30},
            ),
        ),
    ],
)
def test_semantic_boundary_exact_canonical_questions_stay_deterministic(text, intent):
    req = NLQRequest(telegram_user_id=1, text=text, now_ts=1000)

    assert pl._select_answer_policy(req, intent) == "deterministic"
    assert pl._select_execution_route(req, intent) == "deterministic"


@pytest.mark.parametrize(
    "text",
    [
        "опиши мої витрати людською мовою за місяць",
        "сформулюй м'які висновки по моїх витратах за місяць",
        "поясни як коуч мої витрати за місяць",
        "що це говорить про мої звички витрат за місяць",
        "поясни мої витрати за місяць людською мовою",
        "які в мене патерни витрат у барах",
        "більше йде на регулярні витрати чи на разові покупки",
        "що це говорить про мої звички",
        "наскільки більше я зазвичай купую в novus ніж в atb",
        "наскільки частіше я витрачаю в маку ніж в kfc більше 1000 грн",
    ],
)
def test_semantic_boundary_open_ended_finance_prompts_go_to_safe_llm(text):
    req = NLQRequest(telegram_user_id=1, text=text, now_ts=1000)

    assert pl._select_answer_policy(req, None) == "safe_llm"
    assert pl._select_execution_route(req, None) == "planner"


@pytest.mark.parametrize(
    "text",
    [
        "поясни як коуч",
        "сформулюй м'які висновки",
        "опиши це людською мовою",
    ],
)
def test_semantic_boundary_too_ambiguous_open_questions_go_to_clarification(text):
    req = NLQRequest(telegram_user_id=1, text=text, now_ts=1000)

    assert pl._select_answer_policy(req, None) == "clarification"


@pytest.mark.parametrize(
    ("text", "deterministic"),
    [
        (
            "скільки я витратив на мак за місяць і що це говорить про мої звички?",
            NLQIntent(
                name="spend_sum",
                slots={
                    "intent": "spend_sum",
                    "days": 30,
                    "merchant_contains": "мак",
                    "entity_kind": "spend",
                },
            ),
        ),
        (
            "скільки я витратив на категорію кафе за місяць і сформулюй м'які висновки",
            NLQIntent(
                name="spend_sum",
                slots={
                    "intent": "spend_sum",
                    "days": 30,
                    "category": "Кафе/Ресторани",
                    "entity_kind": "spend",
                },
            ),
        ),
        (
            "порівняй витрати за місяць з попереднім і поясни як коуч що це говорить про мої звички",
            NLQIntent(
                name="compare_to_previous_period",
                slots={"intent": "compare_to_previous_period", "days": 30},
            ),
        ),
        (
            "наскільки більше я зазвичай купую в novus ніж в atb",
            NLQIntent(
                name="between_entities",
                slots={
                    "intent": "between_entities",
                    "days": 30,
                    "comparison_mode": "between_entities",
                    "target_type": "merchant",
                    "merchant_targets": ["novus", "atb"],
                    "entity_kind": "spend",
                },
            ),
        ),
    ],
)
def test_semantic_boundary_prefers_handoff_over_wrong_partial_deterministic_match(
    text,
    deterministic,
):
    req = NLQRequest(telegram_user_id=1, text=text, now_ts=1000)

    assert pl._select_answer_policy(req, deterministic) == "safe_llm"
    assert pl._select_execution_route(req, deterministic) == "planner"


@pytest.mark.parametrize(
    "text",
    [
        "опиши мої витрати по категоріях за місяць людською мовою",
        "що категорія витрат за місяць говорить про мої звички?",
        "порівняй витрати за місяць і поясни людською мовою",
        "категорія витрат за місяць: сформулюй м'які висновки",
    ],
)
def test_semantic_boundary_regression_keywords_do_not_force_wrong_route(text):
    req = NLQRequest(telegram_user_id=1, text=text, now_ts=1000)

    assert pl._select_answer_policy(req, None) == "safe_llm"
    assert pl._select_execution_route(req, None) == "planner"


def test_semantic_boundary_clarification_does_not_touch_llm_or_executor(monkeypatch):
    monkeypatch.setattr(pl, "route", lambda req: None)
    monkeypatch.setattr(pl, "load_memory", lambda telegram_user_id: {})
    monkeypatch.setattr(pl, "get_pending_manual_mode", lambda telegram_user_id, now_ts: None)

    called = {"planner": 0, "tool": 0, "resolve": 0, "execute": 0, "narrative": 0}

    def fake_plan(req):
        called["planner"] += 1
        return None

    def fake_tool(req):
        called["tool"] += 1
        return None

    def fake_resolve(req, intent):
        called["resolve"] += 1
        return intent

    def fake_execute(user_id, slots):
        called["execute"] += 1
        return "EXECUTED"

    def fake_narrative(req, deterministic_intent):
        called["narrative"] += 1
        return None

    monkeypatch.setattr(pl, "_llm_plan_intent", fake_plan)
    monkeypatch.setattr(pl, "_llm_tool_mode_intent", fake_tool)
    monkeypatch.setattr(pl, "_llm_narrative_response", fake_narrative)
    monkeypatch.setattr(pl, "resolve", fake_resolve)
    monkeypatch.setattr(pl, "execute_intent", fake_execute)

    resp = pl.handle_nlq(
        NLQRequest(
            telegram_user_id=1,
            text="поясни як коуч",
            now_ts=1000,
        )
    )

    assert resp.result is not None
    assert "Уточни, будь ласка" in resp.result.text
    assert called == {"planner": 0, "tool": 0, "resolve": 0, "execute": 0, "narrative": 0}
