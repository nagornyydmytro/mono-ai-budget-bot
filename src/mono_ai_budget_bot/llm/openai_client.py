from __future__ import annotations

import json
import re
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


@dataclass(frozen=True)
class LLMResult:
    report: LLMReportV2
    raw_text: str


def _extract_json_object(text: str) -> Optional[str]:
    """
    Best-effort JSON extraction:
    - tries to find the first {...} block that looks like a JSON object
    """
    if not text:
        return None

    s = text.strip()
    if s.startswith("{") and s.endswith("}"):
        return s

    m = re.search(r"\{.*\}", s, flags=re.DOTALL)
    if m:
        return m.group(0).strip()

    return None


def _parse_llm_json(text: str) -> dict[str, Any]:
    s = (text or "").strip()
    try:
        return json.loads(s)
    except Exception:
        extracted = _extract_json_object(s)
        if not extracted:
            raise
        return json.loads(extracted)


class OpenAIClient:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini", timeout_s: float = 30.0):
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set")
        self.api_key = api_key
        self.model = model
        self.client = httpx.Client(timeout=timeout_s)

    def close(self) -> None:
        self.client.close()

    def _chat(self, system: str, user: str, temperature: float = 0.2) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
        }

        r = self.client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload,
        )
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]

    def generate_report(self, facts: dict[str, Any], period_label: str) -> LLMResult:
        """
        Returns structured JSON report.
        Includes: parse + validation + one repair attempt.
        """
        system = (
            "Ти — помічник з фінансової грамотності.\n"
            "Ти працюєш у режимі grounded: використовуй ТІЛЬКИ дані з facts JSON.\n"
            "Не вигадуй дані і не припускай того, чого немає у facts.\n"
            "Не давай інвестиційних, кредитних або юридичних порад.\n"
            "Не обіцяй гарантованих результатів.\n\n"
            "У facts є два блоки:\n"
            "1) period_facts — поточний період\n"
            "2) user_profile — довгострокова норма користувача\n\n"
            "Якщо user_profile не порожній — ТИ ЗОБОВ'ЯЗАНИЙ використати його "
            "мінімум в 1 рекомендації або в summary.\n"
            "Якщо profile є, але ти його не використаєш — відповідь вважається неправильною.\n\n"
            "Поверни ВИКЛЮЧНО валідний JSON без markdown."
        )

        schema_hint = {
            "summary": "string (2-4 речення)",
            "changes": ["string (2-5 пунктів: що виросло/впало + цифри/%)"],
            "recs": ["string (3-7 рекомендацій, кожна прив'язана до facts)"],
            "next_step": "string (1 конкретна дія на 7 днів)",
        }

        user = (
            f"Період: {period_label}\n\n"
            "Формат вхідних даних:\n"
            "- period_facts: метрики за період (totals, top categories/merchants, comparison)\n"
            "- user_profile: довгострокова норма користувача (avg_check_uah, top_*_long_term, spend_tx_count)\n\n"
            "Завдання: згенеруй персоналізований інсайт.\n\n"
            "Вимоги до JSON:\n"
            "- summary: 2–4 речення, коротко і по цифрах.\n"
            "- changes: 2–5 пунктів. Якщо comparison має (—) або попередній період 0 — не роби висновків про %.\n"
            "- recs: 3–7 рекомендацій. Кожна рекомендація має:\n"
            "  (a) посилання на факт з period_facts (сума/категорія/мерчант)\n"
            "  (b) конкретну дію\n"
            "  (c) якщо user_profile не порожній — порівняння з 'нормою' (наприклад: вище/нижче середнього чеку, нетипова категорія, або входить/не входить у long-term топ).\n"
            "- next_step: 1 вимірювана дія на 7 днів (без 'гарантій').\n\n"
            "Правила:\n"
            "- Відсотки/частки НЕ рахуй сам. Якщо потрібні % — бери ТІЛЬКИ з category_shares_real_spend або top_merchants_shares_real_spend.\n"
            "- Якщо shares відсутні для конкретного ключа — не використовуй %.\n"
            "- Якщо comparison prev_period totals.real_spend_total_uah == 0 або відсутній — не порівнюй 'на скільки більше/менше'.\n"
            "- Не вигадуй суми/відсотки. Якщо рахуєш частку — вкажи базу (наприклад від real_spend_total_uah).\n"
            "- Не називай перекази витратами, фокусуйся на real_spend_total_uah.\n"
            "- Поверни ТІЛЬКИ JSON, без markdown.\n\n"
            f"JSON schema hint: {json.dumps(schema_hint, ensure_ascii=False)}\n\n"
            f"facts: {json.dumps(facts, ensure_ascii=False)}"
        )

        raw = self._chat(system=system, user=user, temperature=0.2)

        try:
            obj = _parse_llm_json(raw)
            rep = LLMReportV2.model_validate(obj).clean()
            if not rep.recs:
                raise ValidationError.from_exception_data("LLMReportV2", [])
            return LLMResult(report=rep, raw_text=raw)
        except Exception:
            repair_system = (
                "Ти — JSON-ремонтник. "
                "Твоя задача: перетворити текст у ВАЛІДНИЙ JSON за заданою схемою. "
                "Поверни ТІЛЬКИ JSON, без markdown."
            )
            repair_user = (
                "Виправ відповідь так, щоб це був валідний JSON об'єкт за схемою:\n"
                f"{json.dumps(schema_hint, ensure_ascii=False)}\n\n"
                "Ось проблемна відповідь (НЕ повторюй її як текст, а перетвори у JSON):\n"
                f"{raw}"
            )
            raw2 = self._chat(system=repair_system, user=repair_user, temperature=0.0)

            obj2 = _parse_llm_json(raw2)
            rep2 = LLMReportV2.model_validate(obj2).clean()
            return LLMResult(report=rep2, raw_text=raw2)