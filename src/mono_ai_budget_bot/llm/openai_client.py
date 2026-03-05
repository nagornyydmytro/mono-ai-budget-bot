from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

import httpx
from pydantic import BaseModel, Field, ValidationError


class LLMReportV2(BaseModel):
    """
    Structured LLM output for spending insights.

    - summary: 2–4 речення
    - changes: 2–5 пунктів про зміни (по можливості з цифрами/відсотками)
    - recs: 3–7 рекомендацій (кожна прив'язана до facts)
    - next_step: 1 конкретна дія на 7 днів
    """

    summary: str = Field(min_length=1)
    changes: list[str] = Field(default_factory=list)
    recs: list[str] = Field(default_factory=list)
    next_step: str = Field(min_length=1)

    def clean(self) -> "LLMReportV2":
        self.summary = self.summary.strip()
        self.next_step = self.next_step.strip()

        self.changes = [str(x).strip() for x in self.changes if str(x).strip()][:5]
        self.recs = [str(x).strip() for x in self.recs if str(x).strip()][:7]

        if not self.changes:
            self.changes = []
        if not self.recs:
            self.recs = []

        return self


class NLQPlanV1(BaseModel):
    model_config = {"extra": "forbid"}

    intent: str = Field(min_length=1)
    period: Optional[dict[str, Any]] = None
    filters: Optional[dict[str, Any]] = None
    compare: Optional[dict[str, Any]] = None
    ask_user: Optional[dict[str, Any]] = None


@dataclass(frozen=True)
class ToolModeResult:
    tool: str
    args: dict[str, Any]


def _extract_json_object(text: str) -> str | None:
    s = text or ""
    start = s.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(s)):
        ch = s[i]

        if in_string:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]

    return None


def _parse_llm_json(text: str) -> dict[str, Any]:
    s = (text or "").strip()
    try:
        data = json.loads(s)
    except Exception:
        extracted = _extract_json_object(s)
        if not extracted:
            raise
        data = json.loads(extracted)

    if not isinstance(data, dict):
        raise TypeError("LLM JSON must be an object")
    return data


def _parse_llm_json_strict(raw: str, model: type[BaseModel]) -> BaseModel:
    s = (raw or "").strip()
    if not (s.startswith("{") and s.endswith("}")):
        raise ValidationError.from_exception_data(model.__name__, [])
    try:
        data = json.loads(s)
    except Exception as err:
        raise ValidationError.from_exception_data(model.__name__, []) from err
    if not isinstance(data, dict):
        raise ValidationError.from_exception_data(model.__name__, [])
    return model.model_validate(data)


class OpenAIClient:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini", timeout_s: float = 30.0):
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set")
        self.api_key = api_key
        self.model = model
        self.client = httpx.Client(timeout=timeout_s)

    def close(self) -> None:
        self.client.close()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        r = self.client.post(
            "https://api.openai.com/v1/chat/completions",
            headers=self._headers(),
            json=payload,
        )
        r.raise_for_status()
        return r.json()

    def _extract_text(self, resp: dict[str, Any]) -> str:
        try:
            return str(resp["choices"][0]["message"]["content"] or "")
        except Exception:
            return ""

    def generate_report_v2(self, system: str, user: str, *, max_tokens: int = 700) -> LLMReportV2:
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }
        resp = self._post(payload)
        raw = self._extract_text(resp)
        data = _parse_llm_json(raw)
        model = LLMReportV2.model_validate(data)
        return model.clean()

    def plan_nlq(self, system: str, user: str, *, max_tokens: int = 450) -> NLQPlanV1:
        payload = {
            "model": self.model,
            "temperature": 0.0,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }
        resp = self._post(payload)
        raw = self._extract_text(resp)
        plan = _parse_llm_json_strict(raw, NLQPlanV1)
        return plan

    def tool_mode(self, system: str, user: str, *, max_tokens: int = 450) -> ToolModeResult:
        payload = {
            "model": self.model,
            "temperature": 0.0,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }
        resp = self._post(payload)
        raw = self._extract_text(resp)
        data = _parse_llm_json(raw)
        tool = str(data.get("tool") or "").strip()
        args = data.get("args") or {}
        if not tool or not isinstance(args, dict):
            raise ValidationError.from_exception_data("ToolMode", [])
        return ToolModeResult(tool=tool, args=args)
