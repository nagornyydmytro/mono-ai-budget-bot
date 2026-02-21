from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class LLMResult:
    summary: str
    insights: list[str]
    next_step: str


class OpenAIClient:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini", timeout_s: float = 30.0):
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set")
        self.api_key = api_key
        self.model = model
        self.client = httpx.Client(timeout=timeout_s)

    def close(self) -> None:
        self.client.close()

    def generate_report(self, facts: dict[str, Any], period_label: str) -> LLMResult:
        system = (
            "Ти — помічник з фінансової грамотності. "
            "Ти аналізуєш ТІЛЬКИ надані цифри (facts JSON). "
            "Не вигадуй дані та не припускай того, чого немає у facts. "
            "Не давай інвестиційних, медичних або юридичних порад. "
            "Не обіцяй гарантованих результатів."
        )

        schema = {
            "summary": "string (2-4 речення)",
            "insights": ["string (3-7 пунктів, кожен має містити конкретну цифру/відсоток із facts)"],
            "next_step": "string (1 конкретна дія на 7 днів)",
        }

        user = (
            f"Період: {period_label}\n"
            "Згенеруй короткий аналіз витрат та конкретні рекомендації.\n"
            "Поверни ВИКЛЮЧНО валідний JSON (без markdown).\n"
            f"JSON schema: {json.dumps(schema, ensure_ascii=False)}\n\n"
            f"facts: {json.dumps(facts, ensure_ascii=False)}"
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
        }

        r = self.client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload,
        )
        r.raise_for_status()
        data = r.json()
        content = data["choices"][0]["message"]["content"]

        try:
            obj = json.loads(content)
        except Exception as e:
            raise RuntimeError(f"LLM returned non-JSON output: {content[:300]}") from e

        summary = str(obj.get("summary", "")).strip()
        insights = obj.get("insights", [])
        next_step = str(obj.get("next_step", "")).strip()

        if not summary or not isinstance(insights, list) or not next_step:
            raise RuntimeError(f"LLM JSON missing fields: {obj}")

        insights_str = [str(x).strip() for x in insights if str(x).strip()]
        if not insights_str:
            raise RuntimeError("LLM returned empty insights list")

        return LLMResult(summary=summary, insights=insights_str, next_step=next_step)