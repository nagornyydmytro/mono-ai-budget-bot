import mono_ai_budget_bot.nlq.pipeline as pl
from mono_ai_budget_bot.bot import templates
from mono_ai_budget_bot.nlq.types import NLQIntent, NLQRequest


def test_answer_style_clarification_message_is_human():
    assert templates.nlq_clarify_scope_message() == (
        "Уточни, будь ласка, що саме проаналізувати: витрати, доходи чи перекази. "
        "Можеш також додати період, наприклад за місяць або за 7 днів."
    )


def test_answer_style_deterministic_templates_are_product_facing():
    assert (
        templates.nlq_last_time_line(
            when_text="1970-02-08 15:00",
            description="NOVUS",
            amount="150.00 грн",
        )
        == "Остання операція була 1970-02-08 15:00: NOVUS — 150.00 грн."
    )

    assert (
        templates.nlq_recurrence_line(
            prefix="За останні 30 днів",
            operations=2,
            active_days=2,
            median_gap_days=3,
        )
        == "За останні 30 днів: 2 операцій у 2 активних днях. Медіанний інтервал — 3 дн."
    )

    assert (
        templates.nlq_share_line(
            prefix="За останні 30 днів",
            label="novus",
            amount="250.00 грн",
            share_percent="54.35",
        )
        == "За останні 30 днів: novus — 250.00 грн, це 54.35% від усіх витрат."
    )


def test_answer_style_llm_narrative_strips_debug_like_text(monkeypatch):
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
            "facts": {"totals": {"real_spend_total_uah": 12000.0}},
        },
    )

    class DummyClient:
        def interpret_nlq(self, *, user_text: str, schema: dict, facts_payload: dict):
            return {
                "mode": "narrative_answer",
                "answer": (
                    "schema_json={...}\n"
                    "slot_summary={'merchant_targets':['novus','atb']}\n"
                    "У тебе витрати на NOVUS виглядають стабільнішими, а різницю з ATB дає не один випадковий чек. "
                    "Спробуй окремо відстежити великі покупки в маркеті."
                ),
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
    assert "schema_json" not in resp.result.text
    assert "slot_summary" not in resp.result.text
    assert "Спробуй окремо відстежити" in resp.result.text


def test_answer_style_llm_total_only_answer_is_not_passed_as_final(monkeypatch):
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
            "facts": {"totals": {"real_spend_total_uah": 12000.0}},
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
            return {
                "mode": "narrative_answer",
                "answer": "За останні 30 днів: novus — 2600.00 грн; atb — 1400.00 грн. Різниця: 1200.00 грн.",
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
    assert "Бачу базовий підсумок по цифрах" in resp.result.text


def test_answer_style_llm_clarify_question_is_human(monkeypatch):
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
            "facts": {"totals": {"real_spend_total_uah": 9000.0}},
        },
    )

    class DummyClient:
        def interpret_nlq(self, *, user_text: str, schema: dict, facts_payload: dict):
            return {
                "mode": "semantic_clarify",
                "question": "schema_json={...}\nТебе цікавлять бари як категорія чи конкретні заклади",
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
    assert "schema_json" not in resp.result.text
    assert resp.result.text.endswith("?")
    assert "категорія чи конкретні заклади" in resp.result.text
