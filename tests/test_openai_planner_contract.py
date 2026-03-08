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


def test_tool_mode_accepts_json_only_allowlisted_tool_calls(monkeypatch):
    client = OpenAIClient(api_key="test", model="gpt-4o-mini", timeout_s=1.0)

    monkeypatch.setattr(
        client,
        "_post",
        lambda payload: {
            "choices": [
                {
                    "message": {
                        "content": '{"tool_calls":[{"tool":"query_facts","args":{"metric":"spend_sum","days":30}}]}'
                    }
                }
            ]
        },
    )

    try:
        result = client.tool_mode("system", "user")
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].tool == "query_facts"
        assert result.tool_calls[0].args == {"metric": "spend_sum", "days": 30}
    finally:
        client.close()


def test_tool_mode_rejects_non_json_wrapped_output(monkeypatch):
    client = OpenAIClient(api_key="test", model="gpt-4o-mini", timeout_s=1.0)

    monkeypatch.setattr(
        client,
        "_post",
        lambda payload: {
            "choices": [
                {
                    "message": {
                        "content": 'Ось результат: {"tool_calls":[{"tool":"query_facts","args":{"metric":"spend_sum"}}]}'
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


def test_tool_mode_rejects_non_allowlisted_tool(monkeypatch):
    client = OpenAIClient(api_key="test", model="gpt-4o-mini", timeout_s=1.0)

    monkeypatch.setattr(
        client,
        "_post",
        lambda payload: {
            "choices": [
                {
                    "message": {
                        "content": '{"tool_calls":[{"tool":"write_storage","args":{"bucket":"users"}}]}'
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
