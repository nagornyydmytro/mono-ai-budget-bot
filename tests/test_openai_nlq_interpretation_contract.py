from pydantic import ValidationError

from mono_ai_budget_bot.llm.openai_client import OpenAIClient


def test_interpret_nlq_returns_strict_narrative_dict(monkeypatch):
    client = OpenAIClient(api_key="test", model="gpt-4o-mini", timeout_s=1.0)

    monkeypatch.setattr(
        client,
        "_post",
        lambda payload: {
            "choices": [
                {
                    "message": {
                        "content": '{"mode":"narrative","answer":"У тебе стабільні витрати з піками на їжу поза домом."}'
                    }
                }
            ]
        },
    )

    try:
        data = client.interpret_nlq(
            user_text="опиши мої витрати людською мовою",
            schema={
                "facts_scope": "summary",
                "entity_scope": "spend",
                "period": {"days": 30},
                "comparison_mode": "none",
                "output_mode": "summary",
                "tone_style": "human",
            },
            facts_payload={
                "tool": "query_facts",
                "period": "month",
                "facts": {"totals": {"real_spend_total_uah": 12000.0}},
            },
        )
        assert data == {
            "mode": "narrative",
            "answer": "У тебе стабільні витрати з піками на їжу поза домом.",
        }
    finally:
        client.close()


def test_interpret_nlq_rejects_non_json_wrapped_output(monkeypatch):
    client = OpenAIClient(api_key="test", model="gpt-4o-mini", timeout_s=1.0)

    monkeypatch.setattr(
        client,
        "_post",
        lambda payload: {
            "choices": [
                {"message": {"content": 'Ось відповідь: {"mode":"narrative","answer":"текст"}'}}
            ]
        },
    )

    try:
        try:
            client.interpret_nlq(
                user_text="що це говорить про мої звички?",
                schema={
                    "facts_scope": "summary",
                    "entity_scope": "spend",
                    "period": {"days": 30},
                    "comparison_mode": "none",
                    "output_mode": "summary",
                    "tone_style": "coach",
                },
                facts_payload={
                    "tool": "query_facts",
                    "period": "month",
                    "facts": {"totals": {"real_spend_total_uah": 12000.0}},
                },
            )
            raise AssertionError("ValidationError was expected")
        except ValidationError:
            pass
    finally:
        client.close()
