import mono_ai_budget_bot.nlq.pipeline as pl
from mono_ai_budget_bot.nlq.types import NLQIntent, NLQRequest


def test_build_canonical_query_schema_for_deterministic_query():
    req = NLQRequest(telegram_user_id=1, text="скільки я витратив на мак за 7 днів?", now_ts=1000)
    deterministic = NLQIntent(
        name="spend_sum",
        slots={
            "intent": "spend_sum",
            "days": 7,
            "merchant_contains": "мак",
            "entity_kind": "spend",
            "period_label": "останні 7 днів",
        },
    )

    schema = pl._build_canonical_query_schema(req, deterministic)

    assert schema.facts_scope == "amount"
    assert schema.entity_scope == "merchant"
    assert schema.period == {
        "days": 7,
        "start_ts": None,
        "end_ts": None,
        "label": "останні 7 днів",
    }
    assert schema.comparison_mode == "none"
    assert schema.output_mode == "numeric"
    assert schema.tone_style == "neutral"


def test_select_execution_route_prefers_deterministic_when_router_matched():
    req = NLQRequest(telegram_user_id=1, text="скільки я витратив на мак за 7 днів?", now_ts=1000)
    deterministic = NLQIntent(name="spend_sum", slots={"intent": "spend_sum", "days": 7})
    assert pl._select_execution_route(req, deterministic) == "deterministic"


def test_select_execution_route_handoffs_ambiguous_open_ended_match_to_planner():
    req = NLQRequest(
        telegram_user_id=1,
        text="скільки я витратив на мак за 7 днів і що це говорить про мої звички?",
        now_ts=1000,
    )
    deterministic = NLQIntent(
        name="spend_sum",
        slots={"intent": "spend_sum", "days": 7, "merchant_contains": "мак"},
    )
    assert pl._select_execution_route(req, deterministic) == "planner"


def test_select_execution_route_uses_planner_for_non_deterministic_plain_question():
    req = NLQRequest(
        telegram_user_id=1,
        text="підсумуй мої звички витрат за останній місяць",
        now_ts=1000,
    )
    assert pl._select_execution_route(req, None) == "planner"


def test_select_execution_route_uses_tool_mode_for_decomposable_query():
    req = NLQRequest(
        telegram_user_id=1,
        text="покажи топ категорій і мерчантів за місяць та останні 5 витрат",
        now_ts=1000,
    )
    assert pl._select_execution_route(req, None) == "tool_mode"


def test_select_answer_policy_prefers_deterministic_before_safe_llm():
    req = NLQRequest(telegram_user_id=1, text="скільки я витратив на мак за 7 днів?", now_ts=1000)
    deterministic = NLQIntent(name="spend_sum", slots={"intent": "spend_sum", "days": 7})
    assert pl._select_answer_policy(req, deterministic) == "deterministic"


def test_select_answer_policy_prefers_safe_llm_over_wrong_deterministic_match():
    req = NLQRequest(
        telegram_user_id=1,
        text="скільки я витратив на мак за 7 днів і що це говорить про мої звички?",
        now_ts=1000,
    )
    deterministic = NLQIntent(
        name="spend_sum",
        slots={"intent": "spend_sum", "days": 7, "merchant_contains": "мак"},
    )
    assert pl._select_answer_policy(req, deterministic) == "safe_llm"


def test_select_answer_policy_returns_clarification_for_too_ambiguous_open_question():
    req = NLQRequest(
        telegram_user_id=1,
        text="поясни як коуч",
        now_ts=1000,
    )
    assert pl._select_answer_policy(req, None) == "clarification"


def test_handle_nlq_does_not_call_llm_when_deterministic_route_exists(monkeypatch):
    monkeypatch.setattr(
        pl,
        "route",
        lambda req: NLQIntent(name="spend_sum", slots={"intent": "spend_sum", "days": 7}),
    )
    monkeypatch.setattr(pl, "load_memory", lambda telegram_user_id: {})
    monkeypatch.setattr(pl, "get_pending_manual_mode", lambda telegram_user_id, now_ts: None)

    called = {"planner": 0, "tool": 0, "resolve": 0, "execute": 0}

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
        return "OK"

    monkeypatch.setattr(pl, "_llm_plan_intent", fake_plan)
    monkeypatch.setattr(pl, "_llm_tool_mode_intent", fake_tool)
    monkeypatch.setattr(pl, "resolve", fake_resolve)
    monkeypatch.setattr(pl, "execute_intent", fake_execute)

    resp = pl.handle_nlq(
        NLQRequest(telegram_user_id=1, text="скільки я витратив на мак за 7 днів?", now_ts=1000)
    )
    assert resp.result is not None
    assert resp.result.text == "OK"
    assert resp.clarification is None
    assert called == {"planner": 0, "tool": 0, "resolve": 1, "execute": 1}


def test_handle_nlq_handoffs_ambiguous_deterministic_match_to_planner(monkeypatch):
    monkeypatch.setattr(
        pl,
        "route",
        lambda req: NLQIntent(
            name="spend_sum",
            slots={"intent": "spend_sum", "days": 7, "merchant_contains": "мак"},
        ),
    )
    monkeypatch.setattr(pl, "load_memory", lambda telegram_user_id: {})
    monkeypatch.setattr(pl, "get_pending_manual_mode", lambda telegram_user_id, now_ts: None)

    called = {"planner": 0, "tool": 0, "resolve": 0, "execute": 0}

    def fake_plan(req):
        called["planner"] += 1
        return NLQIntent(name="spend_sum", slots={"intent": "spend_sum", "days": 7})

    def fake_tool(req):
        called["tool"] += 1
        return None

    def fake_resolve(req, intent):
        called["resolve"] += 1
        return intent

    def fake_execute(user_id, slots):
        called["execute"] += 1
        return "PLANNER"

    monkeypatch.setattr(pl, "_llm_plan_intent", fake_plan)
    monkeypatch.setattr(pl, "_llm_tool_mode_intent", fake_tool)
    monkeypatch.setattr(pl, "resolve", fake_resolve)
    monkeypatch.setattr(pl, "execute_intent", fake_execute)

    resp = pl.handle_nlq(
        NLQRequest(
            telegram_user_id=1,
            text="скільки я витратив на мак за 7 днів і що це говорить про мої звички?",
            now_ts=1000,
        )
    )
    assert resp.result is not None
    assert resp.result.text == "PLANNER"
    assert resp.clarification is None
    assert called == {"planner": 1, "tool": 0, "resolve": 1, "execute": 1}


def test_handle_nlq_uses_planner_for_non_deterministic_plain_query(monkeypatch):
    monkeypatch.setattr(pl, "route", lambda req: None)
    monkeypatch.setattr(pl, "load_memory", lambda telegram_user_id: {})
    monkeypatch.setattr(pl, "get_pending_manual_mode", lambda telegram_user_id, now_ts: None)

    called = {"planner": 0, "tool": 0, "resolve": 0, "execute": 0}

    def fake_plan(req):
        called["planner"] += 1
        return NLQIntent(name="spend_sum", slots={"intent": "spend_sum", "days": 30})

    def fake_tool(req):
        called["tool"] += 1
        return None

    def fake_resolve(req, intent):
        called["resolve"] += 1
        return intent

    def fake_execute(user_id, slots):
        called["execute"] += 1
        return "PLANNER"

    monkeypatch.setattr(pl, "_llm_plan_intent", fake_plan)
    monkeypatch.setattr(pl, "_llm_tool_mode_intent", fake_tool)
    monkeypatch.setattr(pl, "resolve", fake_resolve)
    monkeypatch.setattr(pl, "execute_intent", fake_execute)

    resp = pl.handle_nlq(
        NLQRequest(
            telegram_user_id=1,
            text="підсумуй мої звички витрат за останній місяць",
            now_ts=1000,
        )
    )
    assert resp.result is not None
    assert resp.result.text == "PLANNER"
    assert resp.clarification is None
    assert called == {"planner": 1, "tool": 0, "resolve": 1, "execute": 1}


def test_handle_nlq_tries_tool_mode_then_falls_back_to_planner(monkeypatch):
    monkeypatch.setattr(pl, "route", lambda req: None)
    monkeypatch.setattr(pl, "load_memory", lambda telegram_user_id: {})
    monkeypatch.setattr(pl, "get_pending_manual_mode", lambda telegram_user_id, now_ts: None)

    called = {"planner": 0, "tool": 0, "resolve": 0, "execute": 0}

    def fake_plan(req):
        called["planner"] += 1
        return NLQIntent(name="spend_count", slots={"intent": "spend_count", "days": 30})

    def fake_tool(req):
        called["tool"] += 1
        return None

    def fake_resolve(req, intent):
        called["resolve"] += 1
        return intent

    def fake_execute(user_id, slots):
        called["execute"] += 1
        return "TOOL-FALLBACK"

    monkeypatch.setattr(pl, "_llm_plan_intent", fake_plan)
    monkeypatch.setattr(pl, "_llm_tool_mode_intent", fake_tool)
    monkeypatch.setattr(pl, "resolve", fake_resolve)
    monkeypatch.setattr(pl, "execute_intent", fake_execute)

    resp = pl.handle_nlq(
        NLQRequest(
            telegram_user_id=1,
            text="покажи топ категорій і мерчантів за місяць та останні 5 витрат",
            now_ts=1000,
        )
    )
    assert resp.result is not None
    assert resp.result.text == "TOOL-FALLBACK"
    assert resp.clarification is None
    assert called == {"planner": 1, "tool": 1, "resolve": 1, "execute": 1}


def test_select_answer_policy_returns_none_when_semantic_fallback_disabled(monkeypatch):
    req = NLQRequest(
        telegram_user_id=1,
        text="підсумуй мої звички витрат за останній місяць",
        now_ts=1000,
    )
    monkeypatch.setattr(
        pl,
        "_ai_feature_enabled_for_user",
        lambda user_id, key: False if key == "semantic_fallback" else True,
    )
    assert pl._select_answer_policy(req, None) == "none"


def test_select_execution_route_returns_none_when_tool_mode_and_semantic_fallback_disabled(
    monkeypatch,
):
    req = NLQRequest(
        telegram_user_id=1,
        text="покажи топ категорій і мерчантів за місяць та останні 5 витрат",
        now_ts=1000,
    )
    monkeypatch.setattr(
        pl,
        "_ai_feature_enabled_for_user",
        lambda user_id, key: False if key in {"semantic_fallback", "tool_mode"} else True,
    )
    assert pl._select_execution_route(req, None) == "none"


def test_handle_nlq_returns_user_visible_tool_mode_result(monkeypatch):
    monkeypatch.setattr(pl, "route", lambda req: None)
    monkeypatch.setattr(pl, "load_memory", lambda telegram_user_id: {})
    monkeypatch.setattr(pl, "get_pending_manual_mode", lambda telegram_user_id, now_ts: None)
    monkeypatch.setattr(pl, "_llm_cooldown_ok", lambda *args, **kwargs: True)

    class DummyClient:
        def tool_mode(self, system: str, user: str):
            return {
                "tool_calls": [
                    {
                        "tool": "query_primitive",
                        "args": {"primitive": "top_categories", "intent": "spend_sum", "days": 30},
                    },
                    {
                        "tool": "query_safe_view",
                        "args": {"intent": "spend_sum", "days": 30, "limit": 2},
                    },
                ]
            }

    monkeypatch.setattr(pl, "_get_llm_client", lambda: DummyClient())
    monkeypatch.setattr(
        pl,
        "execute_tool_call",
        lambda telegram_user_id, **kwargs: (
            {
                "tool": "query_primitive",
                "primitive": "top_categories",
                "items": [{"category": "Food", "amount_uah": 1200.0}],
            }
            if kwargs["tool"] == "query_primitive"
            else {
                "tool": "query_safe_view",
                "count": 2,
                "rows": [
                    {
                        "date": "2025-01-01",
                        "counterparty_hint": "mac#123abc",
                        "category": "Food",
                        "amount_uah": 250.0,
                    }
                ],
            }
        ),
    )

    resp = pl.handle_nlq(
        NLQRequest(
            telegram_user_id=1,
            text="покажи топ категорій і мерчантів за місяць та останні 5 витрат",
            now_ts=1000,
        )
    )

    assert resp.result is not None
    assert resp.result.meta == {
        "mode": "llm_tool_mode",
        "tools": ["query_primitive", "query_safe_view"],
    }
    assert "safe AI-assisted tool path" in resp.result.text
    assert "Food" in resp.result.text
    assert "mac#123abc" in resp.result.text


def test_handle_nlq_tool_mode_rejects_invalid_schema_with_safe_message(monkeypatch):
    monkeypatch.setattr(pl, "route", lambda req: None)
    monkeypatch.setattr(pl, "load_memory", lambda telegram_user_id: {})
    monkeypatch.setattr(pl, "get_pending_manual_mode", lambda telegram_user_id, now_ts: None)
    monkeypatch.setattr(pl, "_llm_cooldown_ok", lambda *args, **kwargs: True)

    class DummyClient:
        def tool_mode(self, system: str, user: str):
            return {
                "tool_calls": [
                    {"tool": "query_safe_view", "args": {"intent": "spend_sum", "bucket": "users"}}
                ]
            }

    monkeypatch.setattr(pl, "_get_llm_client", lambda: DummyClient())

    resp = pl.handle_nlq(
        NLQRequest(
            telegram_user_id=1,
            text="покажи топ категорій і мерчантів за місяць та останні 5 витрат",
            now_ts=1000,
        )
    )

    assert resp.result is not None
    assert "Не зміг безпечно виконати AI-assisted tool path" in resp.result.text


def test_handle_nlq_tool_mode_returns_safe_message_for_empty_results(monkeypatch):
    monkeypatch.setattr(pl, "route", lambda req: None)
    monkeypatch.setattr(pl, "load_memory", lambda telegram_user_id: {})
    monkeypatch.setattr(pl, "get_pending_manual_mode", lambda telegram_user_id, now_ts: None)
    monkeypatch.setattr(pl, "_llm_cooldown_ok", lambda *args, **kwargs: True)

    class DummyClient:
        def tool_mode(self, system: str, user: str):
            return {
                "tool_calls": [
                    {
                        "tool": "query_safe_view",
                        "args": {"intent": "spend_sum", "days": 30, "limit": 5},
                    }
                ]
            }

    monkeypatch.setattr(pl, "_get_llm_client", lambda: DummyClient())
    monkeypatch.setattr(
        pl,
        "execute_tool_call",
        lambda telegram_user_id, **kwargs: {"tool": "query_safe_view", "count": 0, "rows": []},
    )

    resp = pl.handle_nlq(
        NLQRequest(
            telegram_user_id=1,
            text="покажи останні 5 витрат за місяць",
            now_ts=1000,
        )
    )

    assert resp.result is not None
    assert "не знайшли достатньо даних" in resp.result.text.lower()
