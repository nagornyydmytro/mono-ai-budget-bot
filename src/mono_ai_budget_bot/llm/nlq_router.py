from __future__ import annotations

import json
from typing import Any

from mono_ai_budget_bot.llm.client import get_openai_client


SYSTEM_PROMPT = """
You are a financial intent parser.

Your job is to convert a user's natural language finance question
into a structured JSON query.

You MUST return valid JSON only.
No explanations.
No markdown.
No text outside JSON.

Allowed intents:
- spend_sum
- spend_count
- top_merchants
- top_categories
- compare_periods

Fields:
- intent: string
- days: integer | null
- merchant_contains: string | null
- category: string | null

If question is unrelated to personal finance spending,
return:
{
  "intent": "unsupported"
}
"""


def parse_finance_intent(user_text: str) -> dict[str, Any]:
    client = get_openai_client()

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
    )

    content = response.choices[0].message.content

    try:
        return json.loads(content)
    except Exception:
        return {"intent": "unsupported"}