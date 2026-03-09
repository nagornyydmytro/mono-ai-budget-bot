from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any

from mono_ai_budget_bot.nlq.types import NLQRequest


def build_tool_mode_prompt_system() -> str:
    return (
        "Ти safe tool-router для персональної фінансової аналітики. "
        "Ти не рахуєш гроші самостійно, не пишеш у storage, не працюєш із секретами, токенами або raw транзакціями. "
        "Ти можеш повернути тільки strict JSON з полем tool_calls. "
        "Кожен tool_call має містити тільки allowlisted tool і тільки безпечні args. "
        "Якщо запит надто неоднозначний або не вкладається в allowlist, поверни мінімально достатній allowlisted tool call."
    )


def build_tool_mode_prompt_user(req: NLQRequest, schema_payload: dict[str, object]) -> str:
    return (
        f"user_text={req.text}\n"
        f"now_ts={int(req.now_ts)}\n"
        f"canonical_schema={json.dumps(schema_payload, ensure_ascii=False, sort_keys=True)}"
    )


def coerce_tool_mode_result(raw: object) -> list[tuple[str, dict[str, Any]]] | None:
    if is_dataclass(raw):
        data = asdict(raw)
    elif hasattr(raw, "model_dump") and callable(raw.model_dump):
        data = raw.model_dump()
    else:
        data = raw

    if isinstance(data, dict):
        raw_calls = data.get("tool_calls")
    else:
        raw_calls = getattr(data, "tool_calls", None)

    if not isinstance(raw_calls, list) or not raw_calls:
        return None

    out: list[tuple[str, dict[str, Any]]] = []
    for item in raw_calls:
        if is_dataclass(item):
            item_data = asdict(item)
        elif hasattr(item, "model_dump") and callable(item.model_dump):
            item_data = item.model_dump()
        elif isinstance(item, dict):
            item_data = item
        else:
            tool = getattr(item, "tool", None)
            args = getattr(item, "args", None)
            item_data = {"tool": tool, "args": args}

        tool = str(item_data.get("tool") or "").strip()
        args = item_data.get("args")
        if not isinstance(args, dict):
            return None
        out.append((tool, dict(args)))
    return out


def allowed_tool_arg_keys(tool: str) -> set[str]:
    if tool == "query_facts":
        return {"period", "keys"}
    if tool == "query_safe_view":
        return {
            "intent",
            "days",
            "start_ts",
            "end_ts",
            "category",
            "merchant_contains",
            "recipient_contains",
            "recipient_alias",
            "limit",
        }
    if tool == "query_primitive":
        return {
            "primitive",
            "intent",
            "days",
            "start_ts",
            "end_ts",
            "category",
            "merchant_contains",
            "recipient_contains",
            "recipient_alias",
            "limit",
        }
    return set()


def tool_call_is_safe(tool: str, args: dict[str, Any]) -> bool:
    allowed = allowed_tool_arg_keys(tool)
    if not allowed:
        return False
    if not set(args.keys()).issubset(allowed):
        return False

    if tool == "query_facts":
        period = str(args.get("period") or "").strip().lower()
        if period not in {"today", "week", "month"}:
            return False
        keys = args.get("keys")
        if keys is not None and not isinstance(keys, list):
            return False
        return True

    if tool == "query_safe_view":
        if "limit" in args and not isinstance(args.get("limit"), int):
            return False
        return True

    if tool == "query_primitive":
        primitive = str(args.get("primitive") or "").strip().lower()
        if primitive not in {"count", "sum", "last_time", "top_categories", "top_merchants"}:
            return False
        if "limit" in args and not isinstance(args.get("limit"), int):
            return False
        return True

    return False


def _format_tool_money(value: object) -> str:
    try:
        return f"{float(value):.2f} грн"
    except Exception:
        return "0.00 грн"


def render_tool_payload(payload: dict[str, Any]) -> list[str]:
    tool = str(payload.get("tool") or "").strip()
    if tool == "query_facts":
        facts = payload.get("facts") if isinstance(payload.get("facts"), dict) else {}
        lines: list[str] = []
        period = str(payload.get("period") or "").strip()
        if period:
            lines.append(f"• query_facts / period={period}")
        requested = facts.get("requested_period_label")
        if isinstance(requested, str) and requested.strip():
            lines.append(f"Період: {requested.strip()}")
        totals = facts.get("totals")
        if isinstance(totals, dict) and "real_spend_total_uah" in totals:
            lines.append(f"Витрати: {_format_tool_money(totals.get('real_spend_total_uah'))}")
        if isinstance(facts.get("transactions_count"), int):
            lines.append(f"Транзакцій: {facts['transactions_count']}")
        top_categories = facts.get("top_categories_named_real_spend")
        if isinstance(top_categories, list) and top_categories:
            parts = []
            for item in top_categories[:3]:
                if isinstance(item, dict):
                    name = str(item.get("name") or "—")
                    parts.append(f"{name} {_format_tool_money(item.get('amount_uah'))}")
            if parts:
                lines.append("Топ категорії: " + "; ".join(parts))
        top_merchants = facts.get("top_merchants_real_spend")
        if isinstance(top_merchants, list) and top_merchants:
            parts = []
            for item in top_merchants[:3]:
                if isinstance(item, dict):
                    name = str(item.get("counterparty_hint") or item.get("name") or "—")
                    parts.append(f"{name} {_format_tool_money(item.get('amount_uah'))}")
            if parts:
                lines.append("Топ мерчанти: " + "; ".join(parts))
        return lines

    if tool == "query_safe_view":
        rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
        lines = [f"• query_safe_view / знайдено: {int(payload.get('count') or 0)}"]
        for row in rows[:5]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- {row.get('date') or '—'} · {row.get('counterparty_hint') or '—'} · {row.get('category') or '—'} · {_format_tool_money(row.get('amount_uah'))}"
            )
        return lines

    if tool == "query_primitive":
        primitive = str(payload.get("primitive") or "").strip()
        lines = [f"• query_primitive / {primitive}"]
        if primitive == "count":
            lines.append(f"Кількість: {int(payload.get('count') or 0)}")
        elif primitive == "sum":
            lines.append(f"Сума: {_format_tool_money(payload.get('amount_uah'))}")
        elif primitive == "last_time":
            match = payload.get("match") if isinstance(payload.get("match"), dict) else None
            if match is None:
                lines.append("Нічого не знайдено")
            else:
                lines.append(
                    f"Остання подія: {match.get('date') or '—'} · {match.get('counterparty_hint') or '—'} · {_format_tool_money(match.get('amount_uah'))}"
                )
        else:
            items = payload.get("items") if isinstance(payload.get("items"), list) else []
            for item in items[:5]:
                if not isinstance(item, dict):
                    continue
                name = item.get("category") or item.get("counterparty_hint") or "—"
                lines.append(f"- {name} · {_format_tool_money(item.get('amount_uah'))}")
        return lines

    return []


def tool_payload_has_data(payload: dict[str, Any]) -> bool:
    tool = str(payload.get("tool") or "").strip()
    if tool == "query_facts":
        facts = payload.get("facts")
        return isinstance(facts, dict) and bool(facts)
    if tool == "query_safe_view":
        return bool(payload.get("rows"))
    if tool == "query_primitive":
        primitive = str(payload.get("primitive") or "").strip()
        if primitive == "count":
            return int(payload.get("count") or 0) > 0
        if primitive == "sum":
            return float(payload.get("amount_uah") or 0.0) > 0
        if primitive == "last_time":
            return isinstance(payload.get("match"), dict)
        return bool(payload.get("items"))
    return False


def tool_mode_invalid_text() -> str:
    return (
        "Не зміг безпечно виконати AI-assisted tool path для цього запиту. "
        "Спробуй переформулювати запит простіше або явно вкажи період / сутність / тип зрізу."
    )


def tool_mode_empty_text() -> str:
    return (
        "Я спробував safe AI-assisted tool path, але дозволені інструменти не знайшли достатньо даних. "
        "Уточни період або спочатку онови дані / підготуй звіт за потрібний період."
    )
