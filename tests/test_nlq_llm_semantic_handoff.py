import mono_ai_budget_bot.nlq.pipeline as pl
from mono_ai_budget_bot.nlq.types import NLQIntent, NLQRequest


def test_reasoning_heavy_compare_uses_semantic_interpretation_with_safe_payload(monkeypatch):
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        pl,
        "route",
        lambda req: NLQIntent(
            name="between_entities",
            slots={
                "intent": "between_entities",
                "days": 30,
                "comparison_mode": "between_entities",
                "comparison_metric": "sum",
                "target_type": "merchant",
                "merchant_targets": ["novus", "atb"],
                "entity_kind": "spend",
            },
        ),
    )
    monkeypatch.setattr(pl, "load_memory", lambda telegram_user_id: {})
    monkeypatch.setattr(pl, "get_pending_manual_mode", lambda telegram_user_id, now_ts: None)
    monkeypatch.setattr(pl, "_llm_cooldown_ok", lambda *args, **kwargs: True)
    monkeypatch.setattr(pl, "_ai_feature_enabled_for_user", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        pl,
        "execute_tool_call",
        lambda telegram_user_id, **kwargs: {
            "tool": "query_facts",
            "period": "month",
            "facts": {
                "totals": {"real_spend_total_uah": 12000.0},
                "comparison": {"totals": {"delta_uah": 800.0}},
                "top_categories_named_real_spend": [{"name": "Маркет/Побут", "amount_uah": 4200.0}],
                "top_merchants_real_spend": [
                    {"name": "NOVUS", "amount_uah": 2600.0},
                    {"name": "ATB", "amount_uah": 1400.0},
                ],
                "coverage": {"coverage_days": 30},
            },
        },
    )
    monkeypatch.setattr(
        pl,
        "execute_intent",
        lambda telegram_user_id,
        slots: "За останні 30 днів: novus — 2600.00 грн; atb — 1400.00 грн. Різниця: 1200.00 грн.",
    )

    class DummyClient:
        def interpret_nlq(self, *, user_text: str, schema: dict, facts_payload: dict):
            captured["user_text"] = user_text
            captured["schema"] = schema
            captured["facts_payload"] = facts_payload
            return {
                "mode": "narrative_answer",
                "answer": "Зазвичай на NOVUS у тебе йде більше, ніж на ATB, і різниця виглядає стабільною, а не випадковою.",
            }

    monkeypatch.setattr(pl, "_get_llm_client", lambda: DummyClient())

    resp = pl.handle_nlq(
        NLQRequest(
            telegram_user_id=1,
            text="наскільки більше я зазвичай купую в novus ніж в atb",
            now_ts=50_000,
        )
    )

    assert resp.result is not None
    assert "більше, ніж на ATB" in resp.result.text

    facts_payload = captured["facts_payload"]
    assert isinstance(facts_payload, dict)
    assert facts_payload["slot_summary"]["merchant_targets"] == ["novus", "atb"]
    assert "deterministic_preview" in facts_payload
    assert "description" not in str(facts_payload)
    assert "account_id" not in str(facts_payload)
    assert "mono_token" not in str(facts_payload)


def test_semantic_handoff_can_return_clarify_without_planner(monkeypatch):
    monkeypatch.setattr(pl, "route", lambda req: None)
    monkeypatch.setattr(pl, "load_memory", lambda telegram_user_id: {})
    monkeypatch.setattr(pl, "get_pending_manual_mode", lambda telegram_user_id, now_ts: None)
    monkeypatch.setattr(pl, "_llm_cooldown_ok", lambda *args, **kwargs: True)
    monkeypatch.setattr(pl, "_ai_feature_enabled_for_user", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        pl,
        "execute_tool_call",
        lambda telegram_user_id, **kwargs: {
            "tool": "query_facts",
            "period": "month",
            "facts": {
                "totals": {"real_spend_total_uah": 9000.0},
                "comparison": {"totals": {"delta_uah": 200.0}},
                "coverage": {"coverage_days": 30},
            },
        },
    )

    class DummyClient:
        def plan_nlq(self, *, user_text: str, now_ts: int):
            raise AssertionError("planner must not be called before semantic clarify")

        def interpret_nlq(self, *, user_text: str, schema: dict, facts_payload: dict):
            return {
                "mode": "semantic_clarify",
                "question": "Уточни, будь ласка: тебе цікавлять бари як категорія чи конкретні заклади?",
            }

    monkeypatch.setattr(pl, "_get_llm_client", lambda: DummyClient())

    resp = pl.handle_nlq(
        NLQRequest(
            telegram_user_id=1,
            text="які в мене патерни витрат у барах",
            now_ts=60_000,
        )
    )

    assert resp.result is not None
    assert "Уточни, будь ласка" in resp.result.text
    assert "категорія чи конкретні заклади" in resp.result.text
