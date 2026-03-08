import mono_ai_budget_bot.nlq.pipeline as pl
from mono_ai_budget_bot.nlq.types import NLQIntent, NLQRequest


def test_select_execution_route_prefers_deterministic_when_router_matched():
    req = NLQRequest(telegram_user_id=1, text="скільки я витратив на мак за 7 днів?", now_ts=1000)
    deterministic = NLQIntent(name="spend_sum", slots={"intent": "spend_sum", "days": 7})
    assert pl._select_execution_route(req, deterministic) == "deterministic"


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
