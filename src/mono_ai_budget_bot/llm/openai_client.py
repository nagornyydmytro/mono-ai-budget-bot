from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal, Optional

import httpx
from pydantic import BaseModel, Field, ValidationError

from .tooling import ALLOWED_TOOL_NAMES


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
    days: Optional[int] = None
    start_ts: Optional[int] = None
    end_ts: Optional[int] = None
    merchant_contains: Optional[str] = None
    recipient_alias: Optional[str] = None
    period_label: Optional[str] = None
    category: Optional[str] = None
    entity_kind: Optional[str] = None
    threshold_uah: Optional[float] = None


class ToolCallV1(BaseModel):
    model_config = {"extra": "forbid"}

    tool: str = Field(min_length=1)
    args: dict[str, Any] = Field(default_factory=dict)


class ToolModeEnvelopeV1(BaseModel):
    model_config = {"extra": "forbid"}

    tool_calls: list[ToolCallV1] = Field(min_length=1)


@dataclass(frozen=True)
class ToolCall:
    tool: str
    args: dict[str, Any]


@dataclass(frozen=True)
class ToolModeResult:
    tool_calls: list[ToolCall]


class NLQInterpretationV1(BaseModel):
    model_config = {"extra": "forbid"}

    mode: Literal["narrative", "clarify", "unsupported"]
    answer: Optional[str] = None
    question: Optional[str] = None

    def clean(self) -> "NLQInterpretationV1":
        if self.answer is not None:
            self.answer = self.answer.strip()
        if self.question is not None:
            self.question = self.question.strip()
        return self


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


def _is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool))


def _scalar_to_text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip()


def _report_item_to_text(item: Any, *, key_hint: str | None = None) -> str:
    if _is_scalar(item):
        text = _scalar_to_text(item)
        if key_hint and text:
            return f"{key_hint}: {text}"
        return text

    if isinstance(item, dict):
        label = ""
        for field in (
            "text",
            "summary",
            "title",
            "label",
            "name",
            "message",
            "body",
            "description",
        ):
            value = item.get(field)
            if _is_scalar(value) and _scalar_to_text(value):
                label = _scalar_to_text(value)
                break

        parts: list[str] = []
        for key, value in item.items():
            if key in {
                "text",
                "summary",
                "title",
                "label",
                "name",
                "message",
                "body",
                "description",
            }:
                continue
            if _is_scalar(value):
                text = _scalar_to_text(value)
                if text:
                    parts.append(f"{key}={text}")
            elif isinstance(value, dict):
                nested_parts: list[str] = []
                for nested_key, nested_value in value.items():
                    if _is_scalar(nested_value):
                        nested_text = _scalar_to_text(nested_value)
                        if nested_text:
                            nested_parts.append(f"{nested_key}={nested_text}")
                if nested_parts:
                    parts.append(f"{key}: " + ", ".join(nested_parts))

        prefix = label or (str(key_hint).strip() if key_hint else "")
        if prefix and parts:
            return f"{prefix}: " + "; ".join(parts)
        if prefix:
            return prefix
        if parts:
            return "; ".join(parts)
        return ""

    if isinstance(item, list):
        parts = [_report_item_to_text(x) for x in item]
        parts = [p for p in parts if p]
        return "; ".join(parts)

    text = str(item).strip()
    if key_hint and text:
        return f"{key_hint}: {text}"
    return text


def _normalize_report_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = [_report_item_to_text(item) for item in value]
        return [item for item in items if item]
    if isinstance(value, dict):
        items = [_report_item_to_text(item, key_hint=str(key)) for key, item in value.items()]
        return [item for item in items if item]
    text = _report_item_to_text(value)
    return [text] if text else []


def _normalize_report_payload(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": _report_item_to_text(data.get("summary")),
        "changes": _normalize_report_list(data.get("changes")),
        "recs": _normalize_report_list(data.get("recs")),
        "next_step": _report_item_to_text(data.get("next_step")),
    }


_TECHNICAL_REPORT_RE = re.compile(
    r"(?:\b[a-z][a-z0-9_]{2,}\s*=)|(?:\b(?:transactions_count|total_income|total_spend|real_spend|real_spend_total_uah|spend_total_uah|income_total_uah|transfer_in|transfer_out|pct_change|delta)\b)",
    re.IGNORECASE,
)


def _looks_technical_report_text(text: str) -> bool:
    s = str(text or "").strip()
    if not s:
        return False
    return _TECHNICAL_REPORT_RE.search(s) is not None


def _report_needs_repair(report: LLMReportV2) -> bool:
    if _looks_technical_report_text(report.summary):
        return True

    technical_items = 0
    total_items = 0

    for item in [*report.changes, *report.recs]:
        total_items += 1
        if _looks_technical_report_text(item):
            technical_items += 1

    if report.recs and all(_looks_technical_report_text(x) for x in report.recs):
        return True

    if total_items >= 3 and technical_items >= 2:
        return True

    return False


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

    def _generate_report_v2_once(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 700,
        temperature: float = 0.2,
    ) -> LLMReportV2:
        payload = {
            "model": self.model,
            "temperature": temperature,
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
        normalized = _normalize_report_payload(data)
        model = LLMReportV2.model_validate(normalized)
        return model.clean()

    def generate_report_v2(self, system: str, user: str, *, max_tokens: int = 700) -> LLMReportV2:
        model = self._generate_report_v2_once(system, user, max_tokens=max_tokens, temperature=0.2)
        if not _report_needs_repair(model):
            return model

        repair_system = (
            "Ти редактор AI-блоку для персональної фінансової аналітики. "
            "Перепиши невдалу чернетку у КОРИСНИЙ користувацький JSON. "
            "Пиши українською, природно і коротко. "
            "Не використовуй technical keys, snake_case, key=value, JSON-like fragments. "
            "Не дублюй блок 'Факти' і не переписуй всі totals без нового висновку. "
            "Додай лише нові інсайти: драйвери змін, нетипові патерни, концентрацію витрат, controllable actions. "
            "Якщо великі transfer_in/transfer_out, чітко відрізняй 'всі списання' від 'реальних витрат'. "
            "Якщо суттєва частина real spend є uncategorized, прямо скажи, що категорійна картина неповна. "
            "Поверни тільки JSON з полями summary, changes, recs, next_step."
        )
        repair_user = (
            f"Оригінальний system prompt:\n{system}\n\n"
            f"Контекст і facts:\n{user}\n\n"
            f"Невдала чернетка:\n{json.dumps(model.model_dump(), ensure_ascii=False)}"
        )
        return self._generate_report_v2_once(
            repair_system,
            repair_user,
            max_tokens=max_tokens,
            temperature=0.0,
        )

    def plan_nlq(self, *, user_text: str, now_ts: int, max_tokens: int = 450) -> dict[str, Any]:
        system = (
            "Ти planner для персональної фінансової аналітики. "
            "Ти не рахуєш гроші, не пишеш у storage, не викликаєш tools, не повертаєш tool/args, "
            "не працюєш із секретами, токенами або сирими транзакціями. "
            "Твоя задача — або маршрутизувати запит у детермінований intent, або повернути "
            "intent='unsupported'. "
            "Поверни тільки JSON-об'єкт строго за схемою NLQPlanV1 без зайвих полів."
        )
        user = f"now_ts={int(now_ts)}\n" f"user_text={user_text}"
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
        return plan.model_dump(exclude_none=True)

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
        envelope = _parse_llm_json_strict(raw, ToolModeEnvelopeV1)

        tool_calls: list[ToolCall] = []
        for item in envelope.tool_calls:
            tool = str(item.tool or "").strip()
            if tool not in ALLOWED_TOOL_NAMES:
                raise ValidationError.from_exception_data("ToolMode", [])
            args = item.args if isinstance(item.args, dict) else {}
            tool_calls.append(ToolCall(tool=tool, args=args))

        if not tool_calls:
            raise ValidationError.from_exception_data("ToolMode", [])

        return ToolModeResult(tool_calls=tool_calls)

    def interpret_nlq(
        self,
        *,
        user_text: str,
        schema: dict[str, Any],
        facts_payload: dict[str, Any],
        max_tokens: int = 500,
    ) -> dict[str, Any]:
        system = (
            "Ти safe interpreter для персональної фінансової аналітики. "
            "Ти не рахуєш гроші самостійно, не вигадуєш факти, не працюєш з raw storage, "
            "не повертаєш tool calls, не пишеш у storage і не працюєш із секретами. "
            "Тобі дають тільки user_text, canonical query schema і safe facts payload. "
            "Якщо фактів достатньо для м'якого персонального пояснення — поверни mode='narrative'. "
            "Якщо фактів не вистачає або треба уточнення — поверни mode='clarify'. "
            "Якщо запит поза межами персональної фінансової аналітики — поверни mode='unsupported'. "
            "Поверни тільки JSON-об'єкт строго за схемою NLQInterpretationV1 без зайвих полів."
            "Для open-ended personal finance questions ти можеш повернути route='narrative'. "
            "Якщо question просить пояснення, інтерпретацію, pattern analysis або reasoning — "
            "не редукуй це до count/sum. "
            "answer має бути user-facing українською, коротко і змістовно."
        )
        user = (
            f"user_text={user_text}\n"
            f"schema_json={json.dumps(schema, ensure_ascii=False, sort_keys=True)}\n"
            f"facts_json={json.dumps(facts_payload, ensure_ascii=False, sort_keys=True)}"
        )
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
        interpreted = _parse_llm_json_strict(raw, NLQInterpretationV1)
        return interpreted.clean().model_dump(exclude_none=True)
