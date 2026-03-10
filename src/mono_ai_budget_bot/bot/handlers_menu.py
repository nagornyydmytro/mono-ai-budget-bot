from __future__ import annotations

from aiogram.types import CallbackQuery

from mono_ai_budget_bot.monobank import MonobankClient
from mono_ai_budget_bot.nlq import memory_store
from mono_ai_budget_bot.reports.renderer import (
    _render_anomalies_block,
    _render_trends_block,
)
from mono_ai_budget_bot.settings.activity import normalize_activity_settings
from mono_ai_budget_bot.settings.ai_features import (
    compact_ai_features_label,
    normalize_ai_features_settings,
)
from mono_ai_budget_bot.settings.persona import (
    normalize_persona_settings,
    persona_style_label,
)

from . import templates
from .formatting import format_money_uah_pretty
from .handlers_common import HandlerContext
from .handlers_menu_categories import register_categories_handlers
from .handlers_menu_data import register_data_handlers
from .handlers_menu_insights import register_insights_handlers
from .handlers_menu_settings import register_settings_handlers
from .menu_flow import render_menu_screen
from .ui import (
    build_main_menu_keyboard,
    build_reports_menu_keyboard,
    build_rows_keyboard,
)


def _reports_preset_label_from_profile_or_store(ctx: HandlerContext, tg_id: int, prof: dict) -> str:
    preset = _reports_preset_key_from_profile_or_store(ctx, tg_id, prof)
    return {"min": "Min", "max": "Max", "custom": "Custom"}.get(preset, "Min")


def _reports_preset_key_from_profile_or_store(ctx: HandlerContext, tg_id: int, prof: dict) -> str:
    preset = str(prof.get("reports_preset") or "").strip()
    if preset not in {"min", "max", "custom"}:
        cfg = ctx.reports_store.load(tg_id)
        preset = getattr(cfg, "preset", None) or (
            cfg.get("preset") if isinstance(cfg, dict) else None
        )
        if preset not in {"min", "max", "custom"}:
            preset = "min"
        prof["reports_preset"] = preset
    return preset


def _ensure_personalization_profile(ctx: HandlerContext, tg_id: int) -> dict:
    prof = ctx.profile_store.load(tg_id) or {}
    prof = normalize_activity_settings(prof)
    prof = normalize_persona_settings(prof)
    prof = normalize_ai_features_settings(prof)

    _reports_preset_label_from_profile_or_store(ctx, tg_id, prof)

    ctx.profile_store.save(tg_id, prof)
    return prof


def _persona_label(value: str) -> str:
    return persona_style_label(value)


def _activity_label(value: str) -> str:
    return {
        "loud": "Loud",
        "quiet": "Quiet",
        "custom": "Custom",
    }.get(value, "—")


def _uncat_label(value: str) -> str:
    return {
        "immediate": "Одразу",
        "daily": "Раз на день",
        "weekly": "Раз на тиждень",
        "before_report": "Перед звітом",
    }.get(value, "—")


def _ai_features_label(prof: dict) -> str:
    return compact_ai_features_label(prof)


def _save_reports_preset_profile(ctx: HandlerContext, tg_id: int, prof: dict, preset: str) -> None:
    prof["reports_preset"] = preset
    ctx.profile_store.save(tg_id, prof)


def _render_taxonomy_tree_preview(tax: dict | None) -> str:
    if not isinstance(tax, dict):
        return "• Таксономія ще не налаштована."

    roots = tax.get("roots")
    nodes = tax.get("nodes")
    if not isinstance(roots, dict) or not isinstance(nodes, dict):
        return "• Таксономія ще не налаштована."

    lines: list[str] = []

    def _append_branch(root_key: str, label: str) -> None:
        rid = roots.get(root_key)
        if not isinstance(rid, str):
            return
        root_node = nodes.get(rid)
        if not isinstance(root_node, dict):
            return

        children = root_node.get("children")
        if not isinstance(children, list):
            children = []

        lines.append(f"*{label}*")
        if not children:
            lines.append("• —")
            return

        shown_parents = 0
        for cid in children:
            if shown_parents >= 3:
                break
            node = nodes.get(cid)
            if not isinstance(node, dict):
                continue

            parent_name = str(node.get("name") or "").strip()
            if not parent_name:
                continue

            lines.append(f"• {parent_name}")
            shown_parents += 1

            sub_ids = node.get("children")
            if not isinstance(sub_ids, list):
                sub_ids = []

            shown_subs = 0
            for sid in sub_ids:
                if shown_subs >= 2:
                    break
                sub = nodes.get(sid)
                if not isinstance(sub, dict):
                    continue
                sub_name = str(sub.get("name") or "").strip()
                if not sub_name:
                    continue
                lines.append(f"  — {sub_name}")
                shown_subs += 1

            if isinstance(sub_ids, list) and len(sub_ids) > shown_subs:
                lines.append("  — …")

        if len(children) > shown_parents:
            lines.append("• …")

    _append_branch("expense", "Витрати")
    lines.append("")
    _append_branch("income", "Доходи")

    out = "\n".join([x for x in lines if x is not None]).strip()
    return out or "• Таксономія ще не налаштована."


def _categories_action_label(data: str) -> str:
    return {
        "menu:categories:add": "додати категорію",
        "menu:categories:add_subcategory": "додати підкатегорію",
        "menu:categories:rename": "перейменувати категорію",
        "menu:categories:delete": "видалити категорію",
        "menu:categories:rules": "rules / aliases",
    }.get(data, "ця дія")


def _taxonomy_leaf_items(tax: dict | None) -> list[tuple[str, str]]:
    if not isinstance(tax, dict):
        return []

    roots = tax.get("roots")
    nodes = tax.get("nodes")
    if not isinstance(roots, dict) or not isinstance(nodes, dict):
        return []

    out: list[tuple[str, str]] = []

    for root_kind in ("expense", "income"):
        rid = roots.get(root_kind)
        if not isinstance(rid, str):
            continue
        root = nodes.get(rid)
        if not isinstance(root, dict):
            continue

        for cid in list(root.get("children") or []):
            node = nodes.get(cid)
            if not isinstance(node, dict):
                continue
            name = str(node.get("name") or "").strip()
            children = list(node.get("children") or [])
            if not children:
                out.append((cid, name))
                continue

            for sid in children:
                sub = nodes.get(sid)
                if not isinstance(sub, dict):
                    continue
                sub_name = str(sub.get("name") or "").strip()
                if not sub_name:
                    continue
                out.append((sid, f"{name} → {sub_name}"))

    return out


def _leaf_name_by_id(tax: dict | None, leaf_id: str) -> str:
    if not isinstance(tax, dict):
        return leaf_id
    nodes = tax.get("nodes")
    if not isinstance(nodes, dict):
        return leaf_id
    node = nodes.get(leaf_id)
    if not isinstance(node, dict):
        return leaf_id
    name = str(node.get("name") or "").strip()
    if not name:
        return leaf_id
    pid = node.get("parent_id")
    if not isinstance(pid, str):
        return name
    parent = nodes.get(pid)
    if not isinstance(parent, dict) or bool(parent.get("is_root")):
        return name
    parent_name = str(parent.get("name") or "").strip()
    return f"{parent_name} → {name}" if parent_name else name


def _taxonomy_category_items(tax: dict | None) -> list[tuple[str, str]]:
    if not isinstance(tax, dict):
        return []

    roots = tax.get("roots")
    nodes = tax.get("nodes")
    if not isinstance(roots, dict) or not isinstance(nodes, dict):
        return []

    out: list[tuple[str, str]] = []
    for root_kind, root_label in (("expense", "Витрати"), ("income", "Доходи")):
        rid = roots.get(root_kind)
        if not isinstance(rid, str):
            continue
        root = nodes.get(rid)
        if not isinstance(root, dict):
            continue
        for cid in list(root.get("children") or []):
            node = nodes.get(cid)
            if not isinstance(node, dict):
                continue
            name = str(node.get("name") or "").strip()
            if not name:
                continue
            out.append((cid, f"{root_label} → {name}"))
    return out


def _taxonomy_editable_items(tax: dict | None) -> list[tuple[str, str]]:
    if not isinstance(tax, dict):
        return []

    roots = tax.get("roots")
    nodes = tax.get("nodes")
    if not isinstance(roots, dict) or not isinstance(nodes, dict):
        return []

    out: list[tuple[str, str]] = []
    for root_kind, root_label in (("expense", "Витрати"), ("income", "Доходи")):
        rid = roots.get(root_kind)
        if not isinstance(rid, str):
            continue
        root = nodes.get(rid)
        if not isinstance(root, dict):
            continue
        for cid in list(root.get("children") or []):
            node = nodes.get(cid)
            if not isinstance(node, dict):
                continue
            name = str(node.get("name") or "").strip()
            if not name:
                continue
            out.append((cid, f"{root_label} → {name}"))
            for sid in list(node.get("children") or []):
                sub = nodes.get(sid)
                if not isinstance(sub, dict):
                    continue
                sub_name = str(sub.get("name") or "").strip()
                if not sub_name:
                    continue
                out.append((sid, f"{root_label} → {name} → {sub_name}"))
    return out


def _categories_picker_keyboard(
    items: list[tuple[str, str]], *, callback_prefix: str, back_callback: str
):
    rows = [[(label, f"{callback_prefix}:{node_id}")] for node_id, label in items]
    rows.append([("⬅️ Назад", back_callback)])
    return build_rows_keyboard(rows)


def _categories_manual_state_save(tg_id: int, *, state: dict) -> None:
    mem = memory_store.load_memory(tg_id)
    mem["categories_ui"] = dict(state)
    memory_store.save_memory(tg_id, mem)


def _categories_manual_state_clear(tg_id: int) -> None:
    mem = memory_store.load_memory(tg_id)
    mem.pop("categories_ui", None)
    memory_store.save_memory(tg_id, mem)


def _rules_or_aliases_reference_leaf(
    ctx: HandlerContext, tg_id: int, *, leaf_id: str, tax: dict | None
) -> bool:
    for rule in ctx.rules_store.load(tg_id):
        if str(getattr(rule, "leaf_id", "") or "").strip() == leaf_id:
            return True
    alias_terms = _load_alias_terms(tax)
    return bool(alias_terms.get(leaf_id))


def _has_ready_insights_data(ctx: HandlerContext, tg_id: int) -> bool:
    stored = ctx.store.load(tg_id, "month")
    if stored is None:
        return False
    facts = getattr(stored, "facts", None)
    return isinstance(facts, dict) and bool(facts)


def _load_month_facts(ctx: HandlerContext, tg_id: int) -> dict | None:
    stored = ctx.store.load(tg_id, "month")
    if stored is None:
        return None
    facts = getattr(stored, "facts", None)
    return facts if isinstance(facts, dict) else None


def _render_insight_body(section_key: str, facts: dict) -> str | None:
    if section_key == "menu:insights:trends":
        return _render_trends_block(facts.get("trends") or {})
    if section_key == "menu:insights:anomalies":
        return _render_anomalies_block(facts)
    return None


def _render_whatif_pct_body(facts: dict, pct: int) -> str | None:
    whatifs = facts.get("whatif_suggestions") or []
    if not isinstance(whatifs, list) or not whatifs:
        return None

    lines: list[str] = []
    lines.append("*What-if (можлива економія):*")

    added = 0
    for item in whatifs[:3]:
        scenarios = item.get("scenarios") or []
        if not isinstance(scenarios, list):
            continue
        match = next((s for s in scenarios if int(s.get("pct", 0)) == int(pct)), None)
        if not isinstance(match, dict):
            continue

        title = str(item.get("title") or "—").strip() or "—"
        base = float(item.get("monthly_spend_uah") or 0.0)
        projected = float(match.get("projected_monthly_uah") or 0.0)
        savings = float(match.get("monthly_savings_uah") or 0.0)

        lines.append(
            f"• {title}: зараз ~{format_money_uah_pretty(base)}/міс → "
            f"при -{int(pct)}% буде ~{format_money_uah_pretty(projected)}/міс, "
            f"економія ~{format_money_uah_pretty(savings)}/міс"
        )
        added += 1

    if added == 0:
        return None

    return "\n".join(lines).strip()


def _render_forecast_projection_body(facts: dict, metric: str) -> str | None:
    totals = facts.get("totals") or {}
    if not isinstance(totals, dict):
        return None

    if metric == "income":
        label = "Надходження"
        value = float(totals.get("income_total_uah") or 0.0)
    else:
        label = "Реальні витрати"
        value = float(totals.get("real_spend_total_uah") or 0.0)

    if value <= 0:
        return None

    return "\n".join(
        [
            "*Forecast (deterministic projection):*",
            f"• База: останні 30 днів = {label.lower()} {format_money_uah_pretty(value)}",
            f"• Якщо поточний темп збережеться, наступні 30 днів ≈ {format_money_uah_pretty(value)}",
            "• Це не prediction magic і не ML-прогноз, а механічна проєкція з уже підготовленого 30-денного вікна.",
        ]
    ).strip()


def _render_explain_body(facts: dict) -> str | None:
    trends = facts.get("trends") or {}
    anomalies_raw = facts.get("anomalies")
    anomalies: list[dict] = []

    if isinstance(anomalies_raw, list):
        anomalies = [x for x in anomalies_raw if isinstance(x, dict)]
    elif isinstance(anomalies_raw, dict):
        items = anomalies_raw.get("items")
        if isinstance(items, list):
            anomalies = [x for x in items if isinstance(x, dict)]

    growing = trends.get("growing") or []
    declining = trends.get("declining") or []

    lines: list[str] = []
    lines.append("*Explain (на базі вже порахованих facts):*")

    added = 0

    if isinstance(growing, list) and growing:
        item = next((x for x in growing if isinstance(x, dict)), None)
        if isinstance(item, dict):
            label = str(item.get("label") or "—").strip() or "—"
            delta = float(item.get("delta_uah") or 0.0)
            pct = item.get("pct")
            pct_part = f" ({int(pct)}%)" if isinstance(pct, (int, float)) else ""
            lines.append(
                f"• Найсильніше зростання: {label} — +{format_money_uah_pretty(delta)}{pct_part} проти попереднього вікна."
            )
            added += 1

    if isinstance(declining, list) and declining:
        item = next((x for x in declining if isinstance(x, dict)), None)
        if isinstance(item, dict):
            label = str(item.get("label") or "—").strip() or "—"
            delta = abs(float(item.get("delta_uah") or 0.0))
            pct = item.get("pct")
            pct_part = f" ({abs(int(pct))}%)" if isinstance(pct, (int, float)) else ""
            lines.append(
                f"• Найсильніше падіння: {label} — -{format_money_uah_pretty(delta)}{pct_part} проти попереднього вікна."
            )
            added += 1

    if anomalies:
        item = anomalies[0]
        label = str(item.get("label") or "—").strip() or "—"
        last_uah = float(item.get("last_day_uah") or 0.0)
        base_uah = float(item.get("baseline_median_uah") or 0.0)
        reason = str(item.get("reason") or "").strip()

        reason_map = {
            "first_time_large": "це перша велика поява за період",
            "spike_vs_median": "це сплеск відносно типової медіани",
        }
        reason_text = reason_map.get(reason, "це нетипове відхилення від базового патерну")
        lines.append(
            f"• Аномалія: {label} — факт {format_money_uah_pretty(last_uah)} при звичному рівні ~{format_money_uah_pretty(base_uah)}; {reason_text}."
        )
        added += 1

    if added == 0:
        return None

    lines.append("")
    lines.append(
        "Пояснення побудоване тільки з already computed trends/anomalies facts без нових розрахунків."
    )
    return "\n".join(lines).strip()


def _load_alias_terms(tax: dict | None) -> dict[str, list[str]]:
    if not isinstance(tax, dict):
        return {}
    raw = tax.get("alias_terms")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, list[str]] = {}
    for leaf_id, terms in raw.items():
        if not isinstance(leaf_id, str):
            continue
        if not isinstance(terms, list):
            continue
        cleaned = [str(x).strip() for x in terms if isinstance(x, str) and str(x).strip()]
        if cleaned:
            out[leaf_id] = cleaned
    return out


def _save_alias_terms(tax: dict, alias_terms: dict[str, list[str]]) -> dict:
    tax["alias_terms"] = {
        str(k): [str(x).strip() for x in v if isinstance(x, str) and str(x).strip()]
        for k, v in alias_terms.items()
        if isinstance(k, str)
    }
    return tax


def _rules_alias_entries(ctx: HandlerContext, tg_id: int, tax: dict | None) -> list[dict]:
    entries: list[dict] = []

    for r in ctx.rules_store.load(tg_id):
        term = str(r.merchant_contains or r.recipient_contains or "").strip()
        if not term:
            continue
        kind = "merchant_rule" if r.merchant_contains else "recipient_rule"
        entries.append(
            {
                "kind": kind,
                "id": r.id,
                "value": term,
                "leaf_id": r.leaf_id,
                "leaf_name": _leaf_name_by_id(tax, r.leaf_id),
            }
        )

    alias_terms = _load_alias_terms(tax)
    for leaf_id, terms in alias_terms.items():
        for term in terms:
            entries.append(
                {
                    "kind": "alias",
                    "id": f"{leaf_id}|{term}",
                    "value": term,
                    "leaf_id": leaf_id,
                    "leaf_name": _leaf_name_by_id(tax, leaf_id),
                }
            )

    return entries


def _rules_alias_kind_label(kind: str) -> str:
    return {
        "merchant_rule": "Merchant rule",
        "recipient_rule": "Recipient rule",
        "alias": "Alias mapping",
    }.get(kind, "Rule")


def _rules_alias_summary(entries: list[dict]) -> str:
    if not entries:
        return "• Поки що немає правил або alias mappings."

    lines: list[str] = []
    for idx, item in enumerate(entries[:8], start=1):
        lines.append(
            f"{idx}. {_rules_alias_kind_label(str(item.get('kind') or ''))}: "
            f"`{str(item.get('value') or '').strip()}` → {str(item.get('leaf_name') or '').strip()}"
        )
    if len(entries) > 8:
        lines.append("…")
    return "\n".join(lines).strip()


def register_menu_handlers(dp, *, ctx: HandlerContext) -> None:
    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data == "menu:reports")
    async def cb_menu_reports(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(
            query,
            require_token=True,
            require_accounts=True,
            require_ledger=True,
        ):
            return
        await render_menu_screen(
            query,
            text=templates.menu_reports_message(),
            reply_markup=build_reports_menu_keyboard(),
        )

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data == "menu:root")
    async def cb_menu_root(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_query_or_resume(query):
            return
        if query.message:
            await query.message.answer(
                templates.menu_root_message(),
                reply_markup=build_main_menu_keyboard(),
            )
        await query.answer()

    register_insights_handlers(
        dp,
        ctx=ctx,
        load_month_facts=_load_month_facts,
        render_insight_body=_render_insight_body,
        render_whatif_pct_body=_render_whatif_pct_body,
        render_forecast_projection_body=_render_forecast_projection_body,
        render_explain_body=_render_explain_body,
    )

    register_data_handlers(
        dp,
        ctx=ctx,
        monobank_client_cls_factory=lambda: MonobankClient,
    )

    register_settings_handlers(
        dp,
        ctx=ctx,
        ensure_personalization_profile=_ensure_personalization_profile,
        reports_preset_label_from_profile_or_store=_reports_preset_label_from_profile_or_store,
        reports_preset_key_from_profile_or_store=_reports_preset_key_from_profile_or_store,
        persona_label=_persona_label,
        activity_label=_activity_label,
        uncat_label=_uncat_label,
        ai_features_label=_ai_features_label,
        save_reports_preset_profile=_save_reports_preset_profile,
    )

    register_categories_handlers(
        dp,
        ctx=ctx,
        render_taxonomy_tree_preview=_render_taxonomy_tree_preview,
        rules_alias_entries=_rules_alias_entries,
        rules_alias_summary=_rules_alias_summary,
        rules_alias_kind_label=_rules_alias_kind_label,
        taxonomy_leaf_items=_taxonomy_leaf_items,
        leaf_name_by_id=_leaf_name_by_id,
        taxonomy_category_items=_taxonomy_category_items,
        taxonomy_editable_items=_taxonomy_editable_items,
        categories_picker_keyboard=_categories_picker_keyboard,
        categories_manual_state_save=_categories_manual_state_save,
        categories_manual_state_clear=_categories_manual_state_clear,
        rules_or_aliases_reference_leaf=_rules_or_aliases_reference_leaf,
        load_alias_terms=_load_alias_terms,
        save_alias_terms=_save_alias_terms,
    )
