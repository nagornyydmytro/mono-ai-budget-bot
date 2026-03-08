from pydantic import ValidationError

from mono_ai_budget_bot.llm.openai_client import OpenAIClient


def test_tool_mode_rejects_planner_like_payload(monkeypatch):
    client = OpenAIClient(api_key="test", model="gpt-4o-mini", timeout_s=1.0)

    monkeypatch.setattr(
        client,
        "_post",
        lambda payload: {
            "choices": [
                {
                    "message": {
                        "content": '{"intent":"spend_sum","days":30,"merchant_contains":"мак"}'
                    }
                }
            ]
        },
    )

    try:
        try:
            client.tool_mode("system", "user")
            raise AssertionError("ValidationError was expected")
        except ValidationError:
            pass
    finally:
        client.close()


def test_plan_nlq_returns_routing_dict(monkeypatch):
    client = OpenAIClient(api_key="test", model="gpt-4o-mini", timeout_s=1.0)

    monkeypatch.setattr(
        client,
        "_post",
        lambda payload: {
            "choices": [
                {
                    "message": {
                        "content": '{"intent":"spend_sum","days":30,"merchant_contains":"мак"}'
                    }
                }
            ]
        },
    )

    try:
        data = client.plan_nlq(user_text="скільки я витратив на мак?", now_ts=2000)
        assert isinstance(data, dict)
        assert data == {"intent": "spend_sum", "days": 30, "merchant_contains": "мак"}
    finally:
        client.close()
