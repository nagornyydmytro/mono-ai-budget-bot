import mono_ai_budget_bot.nlq.pipeline as pl
from mono_ai_budget_bot.nlq.types import NLQIntent, NLQRequest


def test_handle_nlq_uses_safe_narrative_mode_for_open_ended_question(monkeypatch):
    captured: dict[str, object] = {}

    monkeypatch.setattr(pl, "route", lambda req: None)
    monkeypatch.setattr(pl, "load_memory", lambda telegram_user_id: {})
    monkeypatch.setattr(pl, "get_pending_manual_mode", lambda telegram_user_id, now_ts: None)
    monkeypatch.setattr(pl, "_llm_cooldown_ok", lambda *args, **kwargs: True)

    class DummyClient:
        def plan_nlq(self, *, user_text: str, now_ts: int):
            return {"intent": "unsupported"}

        def interpret_nlq(self, *, user_text: str, schema: dict, facts_payload: dict):
            captured["user_text"] = user_text
            captured["schema"] = schema
            captured["facts_payload"] = facts_payload
            return {
                "mode": "narrative",
                "answer": "За місяць у тебе рівні, але помітно імпульсивні витрати на їжу поза домом.",
            }

    monkeypatch.setattr(pl, "_get_llm_client", lambda: DummyClient())
    monkeypatch.setattr(
        pl,
        "execute_tool_call",
        lambda telegram_user_id, **kwargs: {
            "tool": "query_facts",
            "period": "month",
            "facts": {
                "totals": {"real_spend_total_uah": 12345.0},
                "comparison": {"totals": {"delta_uah": 456.0}},
                "top_categories_named_real_spend": [
                    {"name": "Food", "amount_uah": 4500.0},
                    {"name": "Groceries", "amount_uah": 3200.0},
                ],
                "coverage": {"coverage_days": 30},
            },
        },
    )

    resp = pl.handle_nlq(
        NLQRequest(
            telegram_user_id=1,
            text="опиши мої витрати людською мовою за місяць",
            now_ts=10_000,
        )
    )

    assert resp.result is not None
    assert "людською мовою" not in resp.result.text.lower()
    assert "імпульсивні витрати" in resp.result.text
    assert resp.result.meta == {"mode": "llm_narrative", "period": "month"}

    facts_payload = captured["facts_payload"]
    assert isinstance(facts_payload, dict)
    assert "description" not in str(facts_payload)
    assert "account_id" not in str(facts_payload)
    assert "mono_token" not in str(facts_payload)


def test_handle_nlq_returns_controlled_message_when_narrative_facts_missing(monkeypatch):
    monkeypatch.setattr(pl, "route", lambda req: None)
    monkeypatch.setattr(pl, "load_memory", lambda telegram_user_id: {})
    monkeypatch.setattr(pl, "get_pending_manual_mode", lambda telegram_user_id, now_ts: None)
    monkeypatch.setattr(pl, "_llm_cooldown_ok", lambda *args, **kwargs: True)

    class DummyClient:
        def plan_nlq(self, *, user_text: str, now_ts: int):
            return {"intent": "unsupported"}

        def interpret_nlq(self, *, user_text: str, schema: dict, facts_payload: dict):
            raise AssertionError("interpret_nlq must not be called when facts are missing")

    monkeypatch.setattr(pl, "_get_llm_client", lambda: DummyClient())
    monkeypatch.setattr(
        pl,
        "execute_tool_call",
        lambda telegram_user_id, **kwargs: {
            "tool": "query_facts",
            "period": "month",
            "facts": {},
        },
    )

    resp = pl.handle_nlq(
        NLQRequest(
            telegram_user_id=1,
            text="що це говорить про мої звички витрат?",
            now_ts=20_000,
        )
    )

    assert resp.result is not None
    assert "немає підготовлених фактів" in resp.result.text
    assert "онови дані" in resp.result.text.lower()


def test_ambiguous_deterministic_match_falls_through_to_safe_narrative(monkeypatch):
    monkeypatch.setattr(pl, "load_memory", lambda telegram_user_id: {})
    monkeypatch.setattr(pl, "get_pending_manual_mode", lambda telegram_user_id, now_ts: None)
    monkeypatch.setattr(
        pl,
        "route",
        lambda req: NLQIntent(
            name="spend_sum",
            slots={"intent": "spend_sum", "days": 30, "merchant_contains": "мак"},
        ),
    )
    monkeypatch.setattr(pl, "_llm_cooldown_ok", lambda *args, **kwargs: True)

    class DummyClient:
        def plan_nlq(self, *, user_text: str, now_ts: int):
            return {"intent": "unsupported"}

        def interpret_nlq(self, *, user_text: str, schema: dict, facts_payload: dict):
            return {
                "mode": "narrative",
                "answer": "За місяць у тебе помітна концентрація витрат на fast food.",
            }

    monkeypatch.setattr(pl, "_get_llm_client", lambda: DummyClient())
    monkeypatch.setattr(
        pl,
        "execute_tool_call",
        lambda telegram_user_id, **kwargs: {
            "tool": "query_facts",
            "period": "month",
            "facts": {
                "totals": {"real_spend_total_uah": 5200.0},
                "comparison": {"totals": {"delta_uah": 300.0}},
            },
        },
    )

    resp = pl.handle_nlq(
        NLQRequest(
            telegram_user_id=1,
            text="скільки я витратив на мак за місяць і що це говорить про мої звички?",
            now_ts=30_000,
        )
    )

    assert resp.result is not None
    assert resp.result.text == "За місяць у тебе помітна концентрація витрат на fast food."


def test_handle_nlq_returns_clarification_for_too_ambiguous_open_question(monkeypatch):
    monkeypatch.setattr(pl, "route", lambda req: None)
    monkeypatch.setattr(pl, "load_memory", lambda telegram_user_id: {})
    monkeypatch.setattr(pl, "get_pending_manual_mode", lambda telegram_user_id, now_ts: None)

    class DummyClient:
        def plan_nlq(self, *, user_text: str, now_ts: int):
            raise AssertionError("plan_nlq must not be called for clarification-first policy")

        def interpret_nlq(self, *, user_text: str, schema: dict, facts_payload: dict):
            raise AssertionError("interpret_nlq must not be called for clarification-first policy")

    monkeypatch.setattr(pl, "_get_llm_client", lambda: DummyClient())

    resp = pl.handle_nlq(
        NLQRequest(
            telegram_user_id=1,
            text="поясни як коуч",
            now_ts=40_000,
        )
    )

    assert resp.result is not None
    assert "Уточни, будь ласка" in resp.result.text
    assert "витрати, доходи чи перекази" in resp.result.text


def test_handle_nlq_uses_safe_narrative_mode_for_where_money_goes_question(monkeypatch):
    monkeypatch.setattr(pl, "route", lambda req: None)
    monkeypatch.setattr(pl, "load_memory", lambda telegram_user_id: {})
    monkeypatch.setattr(pl, "get_pending_manual_mode", lambda telegram_user_id, now_ts: None)
    monkeypatch.setattr(pl, "_llm_cooldown_ok", lambda *args, **kwargs: True)

    class DummyClient:
        def plan_nlq(self, *, user_text: str, now_ts: int):
            return {"intent": "unsupported"}

        def interpret_nlq(self, *, user_text: str, schema: dict, facts_payload: dict):
            return {
                "mode": "narrative",
                "answer": "За місяць у тебе гроші в основному йдуть на маркет/побут, кафе та транспорт.",
            }

    monkeypatch.setattr(pl, "_get_llm_client", lambda: DummyClient())
    monkeypatch.setattr(
        pl,
        "execute_tool_call",
        lambda telegram_user_id, **kwargs: {
            "tool": "query_facts",
            "period": "month",
            "facts": {
                "totals": {"real_spend_total_uah": 12345.0},
                "comparison": {"totals": {"delta_uah": 456.0}},
                "top_categories_named_real_spend": [
                    {"name": "Маркет/Побут", "amount_uah": 4500.0},
                    {"name": "Кафе/Ресторани", "amount_uah": 3200.0},
                ],
                "coverage": {"coverage_days": 30},
            },
        },
    )

    resp = pl.handle_nlq(
        NLQRequest(
            telegram_user_id=1,
            text="куди в мене за місяць в основному йдуть гроші",
            now_ts=50_000,
        )
    )

    assert resp.result is not None
    assert "в основному йдуть на маркет/побут" in resp.result.text.lower()


def test_open_ended_budget_advice_request_handoffs_over_wrong_deterministic_match():
    req = NLQRequest(
        telegram_user_id=1,
        text=(
            "Якщо дивитися на мої витрати за місяць, який один найреалістичніший крок "
            "допоміг би мені скоротити витрати без сильного дискомфорту?"
        ),
        now_ts=60_000,
    )
    deterministic = NLQIntent(
        name="spend_sum",
        slots={"intent": "spend_sum", "days": 30},
    )

    assert pl._select_answer_policy(req, deterministic) == "safe_llm"
    assert pl._select_execution_route(req, deterministic) == "planner"
