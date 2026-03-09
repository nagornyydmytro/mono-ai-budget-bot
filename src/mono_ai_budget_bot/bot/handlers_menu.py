from __future__ import annotations

from aiogram.types import CallbackQuery

from mono_ai_budget_bot.monobank import MonobankClient
from mono_ai_budget_bot.nlq import memory_store
from mono_ai_budget_bot.reports.config import ReportsConfig, build_reports_preset
from mono_ai_budget_bot.reports.renderer import (
    _render_anomalies_block,
    _render_trends_block,
)
from mono_ai_budget_bot.settings.activity import (
    get_activity_toggles,
    normalize_activity_settings,
    set_activity_mode,
    set_activity_toggle,
)
from mono_ai_budget_bot.settings.onboarding import apply_onboarding_settings
from mono_ai_budget_bot.settings.persona import (
    normalize_persona_settings,
    persona_style_label,
    render_persona_summary,
    reset_persona_settings,
    set_persona_field,
)
from mono_ai_budget_bot.storage.wipe import wipe_user_financial_cache
from mono_ai_budget_bot.taxonomy.models import (
    apply_subcategory_migration_choice,
    delete_node,
    ensure_leaf_target,
)
from mono_ai_budget_bot.taxonomy.rules import Rule

from . import templates
from .accounts_ui import render_accounts_screen
from .formatting import format_money_uah_pretty
from .handlers_common import HandlerContext
from .menu_flow import render_menu_screen, render_placeholder_screen
from .onboarding_flow import begin_manual_token_entry, open_accounts_picker, show_data_status
from .ui import (
    build_activity_custom_toggles_keyboard,
    build_activity_mode_keyboard,
    build_back_keyboard,
    build_bootstrap_history_keyboard,
    build_categories_leaf_picker_keyboard,
    build_categories_menu_keyboard,
    build_categories_rule_delete_confirm_keyboard,
    build_categories_rule_item_actions_keyboard,
    build_categories_rules_menu_keyboard,
    build_data_menu_keyboard,
    build_insights_forecast_keyboard,
    build_insights_guidance_keyboard,
    build_insights_menu_keyboard,
    build_insights_whatif_keyboard,
    build_main_menu_keyboard,
    build_persona_editor_keyboard,
    build_persona_preview_keyboard,
    build_personalization_menu_keyboard,
    build_reports_custom_blocks_menu_keyboard,
    build_reports_custom_period_menu_keyboard,
    build_reports_menu_keyboard,
    build_reports_preset_keyboard,
    build_rows_keyboard,
    build_saved_to_root_keyboard,
    build_uncat_frequency_keyboard,
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

    ai_features = prof.get("ai_features")
    if not isinstance(ai_features, dict):
        ai_features = {}
    if "report_explanations" not in ai_features:
        ai_features["report_explanations"] = True
    prof["ai_features"] = ai_features

    _reports_preset_label_from_profile_or_store(ctx, tg_id, prof)

    ctx.profile_store.save(tg_id, prof)
    return prof


def _persona_label(value: str) -> str:
    return persona_style_label(value)


def _persona_draft_key() -> str:
    return "persona_draft"


def _persona_draft_from_memory_or_profile(ctx: HandlerContext, tg_id: int, prof: dict) -> dict:
    mem = memory_store.load_memory(tg_id)
    draft = mem.get(_persona_draft_key())
    if isinstance(draft, dict):
        return normalize_persona_settings({"persona_profile": draft}).get("persona_profile") or {}
    return dict(normalize_persona_settings(prof).get("persona_profile") or {})


def _has_persona_draft(tg_id: int) -> bool:
    mem = memory_store.load_memory(tg_id)
    return isinstance(mem.get(_persona_draft_key()), dict)


def _save_persona_draft(ctx: HandlerContext, tg_id: int, persona_profile: dict) -> dict:
    mem = memory_store.load_memory(tg_id)
    mem[_persona_draft_key()] = dict(
        normalize_persona_settings({"persona_profile": persona_profile}).get("persona_profile")
        or {}
    )
    memory_store.save_memory(tg_id, mem)
    return dict(mem[_persona_draft_key()])


def _clear_persona_draft(tg_id: int) -> None:
    mem = memory_store.load_memory(tg_id)
    mem.pop(_persona_draft_key(), None)
    memory_store.save_memory(tg_id, mem)


def _persona_editor_text(*, prof: dict, draft: dict) -> str:
    current_value = render_persona_summary(prof)
    draft_value = render_persona_summary({"persona_profile": draft})
    return templates.menu_persona_editor_message(
        current_value=current_value,
        draft_value=draft_value,
    )


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
    ai_features = prof.get("ai_features")
    enabled = bool(isinstance(ai_features, dict) and ai_features.get("report_explanations", True))
    return "AI explanations ON" if enabled else "AI explanations OFF"


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
        await render_menu_screen(
            query,
            text=templates.menu_root_message(),
            reply_markup=build_main_menu_keyboard(),
        )

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data == "menu:insights")
    async def cb_menu_insights(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(
            query,
            require_token=True,
            require_accounts=True,
            require_ledger=True,
        ):
            return

        await render_menu_screen(
            query,
            text=templates.menu_insights_message(),
            reply_markup=build_insights_menu_keyboard(),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str)
        and c.data
        in {
            "menu:insights:trends",
            "menu:insights:anomalies",
            "menu:insights:whatif",
            "menu:insights:forecast",
            "menu:insights:explain",
        }
    )
    async def cb_menu_insight_sections(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(
            query,
            require_token=True,
            require_accounts=True,
            require_ledger=True,
        ):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        label_map = {
            "menu:insights:trends": "📈 *Trends*",
            "menu:insights:anomalies": "🚨 *Anomalies*",
            "menu:insights:whatif": "🧮 *What-if*",
            "menu:insights:forecast": "🔮 *Forecast*",
            "menu:insights:explain": "🧠 *Explain*",
        }
        section_label = label_map.get(str(query.data or ""), "✨ *Insights*")

        facts = _load_month_facts(ctx, tg_id)
        if not isinstance(facts, dict) or not facts:
            await render_menu_screen(
                query,
                text=templates.menu_insights_needs_data_message(section_label),
                reply_markup=build_insights_guidance_keyboard(),
            )
            return

        insight_key = str(query.data or "")

        if insight_key == "menu:insights:whatif":
            await render_menu_screen(
                query,
                text=templates.menu_insights_whatif_message(),
                reply_markup=build_insights_whatif_keyboard(),
            )
            return

        if insight_key == "menu:insights:forecast":
            await render_menu_screen(
                query,
                text=templates.menu_insights_forecast_message(),
                reply_markup=build_insights_forecast_keyboard(),
            )
            return

        if insight_key == "menu:insights:explain":
            body = _render_explain_body(facts)
            if not body:
                await render_menu_screen(
                    query,
                    text=templates.menu_insights_needs_data_message("🧠 *Explain*"),
                    reply_markup=build_insights_guidance_keyboard(),
                )
                return

            await render_menu_screen(
                query,
                text=templates.menu_insight_result_message(
                    "🧠 *Explain*",
                    "Пояснення росту/падіння на основі вже підготовлених deterministic facts.",
                    body,
                ),
                reply_markup=build_back_keyboard("menu:insights"),
            )
            return

        rendered = _render_insight_body(insight_key, facts)
        if rendered:
            intro_map = {
                "menu:insights:trends": "Детермінований зріз на основі вже підготовлених trends facts за місячним контекстом.",
                "menu:insights:anomalies": "Детермінований зріз на основі вже підготовлених anomaly facts без вигадування нових даних.",
            }
            await render_menu_screen(
                query,
                text=templates.menu_insight_result_message(
                    section_label,
                    intro_map.get(str(query.data or ""), "Детермінований insights-зріз."),
                    rendered,
                ),
                reply_markup=build_back_keyboard("menu:insights"),
            )
            return

        if str(query.data or "") in {"menu:insights:trends", "menu:insights:anomalies"}:
            await render_menu_screen(
                query,
                text=templates.menu_insights_needs_data_message(section_label),
                reply_markup=build_insights_guidance_keyboard(),
            )
            return

        await render_placeholder_screen(
            query,
            text=templates.menu_insight_placeholder_message(section_label),
            reply_markup=build_back_keyboard("menu:insights"),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str)
        and c.data in {"menu:insights:whatif:pct:10", "menu:insights:whatif:pct:20"}
    )
    async def cb_menu_insight_whatif_variants(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(
            query,
            require_token=True,
            require_accounts=True,
            require_ledger=True,
        ):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        facts = _load_month_facts(ctx, tg_id)
        if not isinstance(facts, dict) or not facts:
            await render_menu_screen(
                query,
                text=templates.menu_insights_needs_data_message("🧮 *What-if*"),
                reply_markup=build_insights_guidance_keyboard(),
            )
            return

        pct = 10 if str(query.data or "").endswith(":10") else 20
        body = _render_whatif_pct_body(facts, pct)
        if not body:
            await render_menu_screen(
                query,
                text=templates.menu_insights_needs_data_message("🧮 *What-if*"),
                reply_markup=build_insights_guidance_keyboard(),
            )
            return

        await render_menu_screen(
            query,
            text=templates.menu_insight_result_message(
                "🧮 *What-if*",
                f"Сценарій -{pct}% на основі вже порахованих what-if facts.",
                body,
            ),
            reply_markup=build_back_keyboard("menu:insights:whatif"),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str)
        and c.data in {"menu:insights:forecast:view:spend", "menu:insights:forecast:view:income"}
    )
    async def cb_menu_insight_forecast_variants(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(
            query,
            require_token=True,
            require_accounts=True,
            require_ledger=True,
        ):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        facts = _load_month_facts(ctx, tg_id)
        if not isinstance(facts, dict) or not facts:
            await render_menu_screen(
                query,
                text=templates.menu_insights_needs_data_message("🔮 *Forecast*"),
                reply_markup=build_insights_guidance_keyboard(),
            )
            return

        metric = "income" if str(query.data or "").endswith(":income") else "spend"
        body = _render_forecast_projection_body(facts, metric)
        if not body:
            await render_menu_screen(
                query,
                text=templates.menu_insights_needs_data_message("🔮 *Forecast*"),
                reply_markup=build_insights_guidance_keyboard(),
            )
            return

        intro = (
            "Детермінована проєкція доходів на основі вже підготовлених totals facts."
            if metric == "income"
            else "Детермінована проєкція витрат на основі вже підготовлених totals facts."
        )
        await render_menu_screen(
            query,
            text=templates.menu_insight_result_message("🔮 *Forecast*", intro, body),
            reply_markup=build_back_keyboard("menu:insights:forecast"),
        )

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data in {"menu:data", "menu:mydata"})
    async def cb_menu_data(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_query_or_resume(query):
            return
        await render_menu_screen(
            query,
            text=templates.menu_data_message(),
            reply_markup=build_data_menu_keyboard(),
        )

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data == "menu:personalization")
    async def cb_menu_personalization(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_query_or_resume(query):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        prof = _ensure_personalization_profile(ctx, tg_id)
        reports_label = _reports_preset_label_from_profile_or_store(ctx, tg_id, prof)

        await render_menu_screen(
            query,
            text=templates.menu_personalization_message(
                persona_label=_persona_label(str(prof.get("persona") or "")),
                activity_label=_activity_label(str(prof.get("activity_mode") or "")),
                reports_label=reports_label,
                uncat_label=_uncat_label(str(prof.get("uncategorized_prompt_frequency") or "")),
                ai_label=_ai_features_label(prof),
            ),
            reply_markup=build_personalization_menu_keyboard(),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str)
        and c.data
        in {
            "menu:personalization:persona",
            "menu:personalization:activity",
            "menu:personalization:reports",
            "menu:personalization:uncat",
            "menu:personalization:ai",
        }
    )
    async def cb_menu_personalization_items(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_query_or_resume(query):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        prof = _ensure_personalization_profile(ctx, tg_id)
        reports_label = _reports_preset_label_from_profile_or_store(ctx, tg_id, prof)

        data = str(query.data or "")
        if data == "menu:personalization:persona":
            draft = _persona_draft_from_memory_or_profile(ctx, tg_id, prof)
            draft = _save_persona_draft(ctx, tg_id, draft)
            await render_menu_screen(
                query,
                text=_persona_editor_text(prof=prof, draft=draft),
                reply_markup=build_persona_editor_keyboard(draft),
            )
            return
        elif data == "menu:personalization:activity":
            await render_menu_screen(
                query,
                text=templates.menu_activity_mode_message(
                    _activity_label(str(prof.get("activity_mode") or ""))
                ),
                reply_markup=build_activity_mode_keyboard(str(prof.get("activity_mode") or "")),
            )
            return
        elif data == "menu:personalization:reports":
            preset_key = _reports_preset_key_from_profile_or_store(ctx, tg_id, prof)
            await render_menu_screen(
                query,
                text=templates.menu_reports_preset_message(reports_label),
                reply_markup=build_reports_preset_keyboard(preset_key),
            )
            return
        elif data == "menu:personalization:uncat":
            current_value = str(prof.get("uncategorized_prompt_frequency") or "")
            await render_menu_screen(
                query,
                text=templates.menu_uncat_frequency_message(_uncat_label(current_value)),
                reply_markup=build_uncat_frequency_keyboard(current_value),
            )
            return
        else:
            title = "🤖 *AI features*"
            current_value = _ai_features_label(prof)

        await render_placeholder_screen(
            query,
            text=templates.menu_personalization_item_message(
                title=title,
                current_value=current_value,
            ),
            reply_markup=build_back_keyboard("menu:personalization"),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str)
        and (
            c.data.startswith("menu:personalization:persona:style:")
            or c.data.startswith("menu:personalization:persona:verbosity:")
            or c.data.startswith("menu:personalization:persona:motivation:")
            or c.data.startswith("menu:personalization:persona:emoji:")
        )
    )
    async def cb_menu_personalization_persona_update(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_query_or_resume(query):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        parts = str(query.data or "").split(":")
        if len(parts) != 5:
            await query.answer(templates.stale_button_message(), show_alert=True)
            return

        field = parts[3]
        value = parts[4]
        prof = _ensure_personalization_profile(ctx, tg_id)
        if not _has_persona_draft(tg_id):
            await query.answer(templates.stale_button_message(), show_alert=True)
            return
        draft = _persona_draft_from_memory_or_profile(ctx, tg_id, prof)
        try:
            draft = dict(
                set_persona_field({"persona_profile": draft}, field=field, value=value).get(
                    "persona_profile"
                )
                or {}
            )
        except ValueError:
            await query.answer(templates.stale_button_message(), show_alert=True)
            return

        _save_persona_draft(ctx, tg_id, draft)
        await render_menu_screen(
            query,
            text=_persona_editor_text(prof=prof, draft=draft),
            reply_markup=build_persona_editor_keyboard(draft),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str) and c.data == "menu:personalization:persona:preview"
    )
    async def cb_menu_personalization_persona_preview(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_query_or_resume(query):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        prof = _ensure_personalization_profile(ctx, tg_id)
        if not _has_persona_draft(tg_id):
            await query.answer(templates.stale_button_message(), show_alert=True)
            return
        draft = _persona_draft_from_memory_or_profile(ctx, tg_id, prof)
        await render_menu_screen(
            query,
            text=templates.menu_persona_preview_message(
                render_persona_summary({"persona_profile": draft})
            ),
            reply_markup=build_persona_preview_keyboard(),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str) and c.data == "menu:personalization:persona:save"
    )
    async def cb_menu_personalization_persona_save(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_query_or_resume(query):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        prof = _ensure_personalization_profile(ctx, tg_id)
        if not _has_persona_draft(tg_id):
            await query.answer(templates.stale_button_message(), show_alert=True)
            return
        draft = _persona_draft_from_memory_or_profile(ctx, tg_id, prof)
        prof["persona_profile"] = dict(draft)
        prof = normalize_persona_settings(prof)
        ctx.profile_store.save(tg_id, prof)
        _clear_persona_draft(tg_id)

        await render_menu_screen(
            query,
            text=templates.menu_persona_saved_message(render_persona_summary(prof)),
            reply_markup=build_back_keyboard("menu:personalization"),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str) and c.data == "menu:personalization:persona:reset"
    )
    async def cb_menu_personalization_persona_reset(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_query_or_resume(query):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        prof = _ensure_personalization_profile(ctx, tg_id)
        draft = dict(reset_persona_settings(prof).get("persona_profile") or {})
        _save_persona_draft(ctx, tg_id, draft)
        await render_menu_screen(
            query,
            text=_persona_editor_text(prof=prof, draft=draft),
            reply_markup=build_persona_editor_keyboard(draft),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str) and c.data == "menu:personalization:persona:cancel"
    )
    async def cb_menu_personalization_persona_cancel(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_query_or_resume(query):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        _clear_persona_draft(tg_id)
        prof = _ensure_personalization_profile(ctx, tg_id)
        reports_label = _reports_preset_label_from_profile_or_store(ctx, tg_id, prof)
        await render_menu_screen(
            query,
            text=templates.menu_personalization_message(
                persona_label=_persona_label(str(prof.get("persona") or "")),
                activity_label=_activity_label(str(prof.get("activity_mode") or "")),
                reports_label=reports_label,
                uncat_label=_uncat_label(str(prof.get("uncategorized_prompt_frequency") or "")),
                ai_label=_ai_features_label(prof),
            ),
            reply_markup=build_personalization_menu_keyboard(),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str)
        and c.data
        in {
            "menu:personalization:activity:loud",
            "menu:personalization:activity:quiet",
            "menu:personalization:activity:custom",
        }
    )
    async def cb_menu_personalization_activity_mode(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_query_or_resume(query):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        mode = str(query.data or "").rsplit(":", 1)[1]
        prof = _ensure_personalization_profile(ctx, tg_id)
        prof = set_activity_mode(prof, mode)
        ctx.profile_store.save(tg_id, prof)

        if mode == "custom":
            await render_menu_screen(
                query,
                text=templates.menu_activity_custom_message(),
                reply_markup=build_activity_custom_toggles_keyboard(get_activity_toggles(prof)),
            )
            return

        await render_menu_screen(
            query,
            text=templates.menu_activity_mode_message(_activity_label(mode)),
            reply_markup=build_activity_mode_keyboard(mode),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str)
        and c.data.startswith("menu:personalization:activity:toggle:")
    )
    async def cb_menu_personalization_activity_toggle(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_query_or_resume(query):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        key = str(query.data or "").rsplit(":", 1)[1]
        prof = _ensure_personalization_profile(ctx, tg_id)
        enabled = get_activity_toggles(prof)
        next_value = not bool(enabled.get(key, False))
        prof = set_activity_toggle(prof, key, next_value)
        ctx.profile_store.save(tg_id, prof)

        await render_menu_screen(
            query,
            text=templates.menu_activity_custom_message(),
            reply_markup=build_activity_custom_toggles_keyboard(get_activity_toggles(prof)),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str)
        and c.data
        in {
            "menu:personalization:uncat:immediate",
            "menu:personalization:uncat:daily",
            "menu:personalization:uncat:weekly",
            "menu:personalization:uncat:before_report",
        }
    )
    async def cb_menu_personalization_uncat_frequency(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_query_or_resume(query):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        freq = str(query.data or "").rsplit(":", 1)[1]
        prof = _ensure_personalization_profile(ctx, tg_id)
        prof = apply_onboarding_settings(prof, uncategorized_prompt_frequency=freq)
        ctx.profile_store.save(tg_id, prof)

        await render_menu_screen(
            query,
            text=templates.menu_uncat_frequency_message(_uncat_label(freq)),
            reply_markup=build_uncat_frequency_keyboard(freq),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str)
        and c.data
        in {
            "menu:personalization:reports:min",
            "menu:personalization:reports:max",
            "menu:personalization:reports:custom",
        }
    )
    async def cb_menu_personalization_reports_preset(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_query_or_resume(query):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        prof = _ensure_personalization_profile(ctx, tg_id)
        data = str(query.data or "")
        preset = data.rsplit(":", 1)[1]

        if preset in {"min", "max"}:
            cfg = build_reports_preset(preset)
            ctx.reports_store.save(tg_id, cfg)
            _save_reports_preset_profile(ctx, tg_id, prof, preset)

            await render_menu_screen(
                query,
                text=templates.menu_reports_preset_message(
                    {"min": "Min", "max": "Max"}.get(preset, "Min")
                ),
                reply_markup=build_reports_preset_keyboard(preset),
            )
            return

        cfg_existing = ctx.reports_store.load(tg_id)
        if getattr(cfg_existing, "preset", None) != "custom":
            cfg_base = build_reports_preset("max")
            cfg_custom = ReportsConfig(
                preset="custom",
                daily=dict(cfg_base.daily),
                weekly=dict(cfg_base.weekly),
                monthly=dict(cfg_base.monthly),
            )
            ctx.reports_store.save(tg_id, cfg_custom)

        _save_reports_preset_profile(ctx, tg_id, prof, "custom")

        await render_menu_screen(
            query,
            text=templates.menu_reports_custom_period_message(),
            reply_markup=build_reports_custom_period_menu_keyboard(),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str)
        and c.data
        in {
            "menu:personalization:reports:period:daily",
            "menu:personalization:reports:period:weekly",
            "menu:personalization:reports:period:monthly",
        }
    )
    async def cb_menu_personalization_reports_period(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_query_or_resume(query):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        cfg = ctx.reports_store.load(tg_id)
        period = str(query.data or "").rsplit(":", 1)[1]
        enabled_map = {"daily": cfg.daily, "weekly": cfg.weekly, "monthly": cfg.monthly}.get(
            period, {}
        )

        await render_menu_screen(
            query,
            text=templates.menu_reports_custom_blocks_message(period),
            reply_markup=build_reports_custom_blocks_menu_keyboard(period, enabled_map),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str)
        and c.data.startswith("menu:personalization:reports:toggle:")
    )
    async def cb_menu_personalization_reports_toggle(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_query_or_resume(query):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        parts = str(query.data or "").split(":")
        if len(parts) != 6:
            await query.answer("Некоректно", show_alert=True)
            return

        period = parts[4]
        key = parts[5]

        cfg = ctx.reports_store.load(tg_id)
        daily = dict(cfg.daily)
        weekly = dict(cfg.weekly)
        monthly = dict(cfg.monthly)

        target = {"daily": daily, "weekly": weekly, "monthly": monthly}.get(period)
        if target is None or key not in target:
            await query.answer("Невідомий блок", show_alert=True)
            return

        target[key] = not bool(target[key])

        cfg2 = ReportsConfig(preset="custom", daily=daily, weekly=weekly, monthly=monthly)
        ctx.reports_store.save(tg_id, cfg2)

        prof = _ensure_personalization_profile(ctx, tg_id)
        _save_reports_preset_profile(ctx, tg_id, prof, "custom")

        enabled_map = {"daily": daily, "weekly": weekly, "monthly": monthly}.get(period, {})
        await render_menu_screen(
            query,
            text=templates.menu_reports_custom_blocks_message(period),
            reply_markup=build_reports_custom_blocks_menu_keyboard(period, enabled_map),
        )

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data == "menu:personalization:done")
    async def cb_menu_personalization_done(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_query_or_resume(query):
            return

        await render_menu_screen(
            query,
            text=templates.menu_settings_saved_message(),
            reply_markup=build_saved_to_root_keyboard(),
        )

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data == "menu:data:new_token")
    async def cb_data_new_token(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_query_or_resume(query):
            return
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        await begin_manual_token_entry(
            query,
            tg_id=tg_id,
            set_pending_manual_mode=memory_store.set_pending_manual_mode,
            hint=templates.token_paste_hint_new_token(),
            source="data_menu",
            prompt_text=templates.token_paste_prompt_new_token(),
            reply_markup=build_back_keyboard("menu:mydata"),
        )

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data == "menu:data:accounts")
    async def cb_data_accounts(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_query_or_resume(query):
            return
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        await open_accounts_picker(
            query,
            tg_id=tg_id,
            users=ctx.users,
            monobank_client_cls=MonobankClient,
            render_accounts_screen=render_accounts_screen,
            load_memory=memory_store.load_memory,
            save_memory=memory_store.save_memory,
        )

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data == "menu:data:refresh")
    async def cb_data_refresh(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        ok, cfg = await ctx.gate_refresh_dependencies(query)
        if not ok or cfg is None:
            return

        if query.message:
            await query.message.answer(templates.ledger_refresh_progress_message())

        import asyncio

        asyncio.create_task(ctx.sync_user_ledger(tg_id, cfg, days_back=30))
        await query.answer()

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data == "menu:data:status")
    async def cb_data_status(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_query_or_resume(query):
            return
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        await show_data_status(
            query,
            tg_id=tg_id,
            users=ctx.users,
            tx_store=ctx.tx_store,
            status_message_builder=templates.status_message,
            reply_markup=build_back_keyboard("menu:mydata"),
        )

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data == "menu:data:bootstrap")
    async def cb_data_bootstrap(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(
            query,
            require_token=True,
            require_accounts=True,
        ):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        mem = memory_store.load_memory(tg_id) or {}
        mem["bootstrap_flow"] = {"source": "data_menu"}
        memory_store.save_memory(tg_id, mem)

        await render_menu_screen(
            query,
            text=templates.menu_data_bootstrap_message(),
            reply_markup=build_bootstrap_history_keyboard(),
        )

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data == "menu:data:wipe")
    async def cb_data_wipe(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_query_or_resume(query):
            return
        await render_menu_screen(
            query,
            text=templates.menu_data_wipe_confirm_message(),
            reply_markup=build_rows_keyboard(
                [
                    [("✅ Підтвердити", "menu:data:wipe:confirm")],
                    [("❌ Скасувати", "menu:data:wipe:cancel")],
                ]
            ),
        )

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data == "menu:data:wipe:confirm")
    async def cb_data_wipe_confirm(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_query_or_resume(query):
            return
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        wipe_user_financial_cache(
            tg_id,
            tx_store=ctx.tx_store,
            report_store=ctx.store,
            rules_store=ctx.rules_store,
            uncat_store=ctx.uncat_store,
            uncat_pending_store=ctx.uncat_pending_store,
        )

        await render_menu_screen(
            query,
            text=templates.menu_data_wipe_done_message(),
            reply_markup=build_back_keyboard("menu:mydata"),
        )

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data == "menu:data:wipe:cancel")
    async def cb_data_wipe_cancel(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_query_or_resume(query):
            return
        await render_menu_screen(
            query,
            text=templates.menu_data_message(),
            reply_markup=build_data_menu_keyboard(),
        )

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data == "menu:categories:rules")
    async def cb_menu_categories_rules(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(
            query,
            require_token=True,
            require_accounts=True,
        ):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        tax = ctx.taxonomy_store.load(tg_id)
        entries = _rules_alias_entries(ctx, tg_id, tax)

        await render_menu_screen(
            query,
            text=templates.menu_categories_rules_message(_rules_alias_summary(entries)),
            reply_markup=build_categories_rules_menu_keyboard(),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str)
        and c.data
        in {
            "menu:categories:rules:add_merchant",
            "menu:categories:rules:add_recipient",
            "menu:categories:rules:add_alias",
        }
    )
    async def cb_menu_categories_rules_new(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(
            query,
            require_token=True,
            require_accounts=True,
        ):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        tax = ctx.taxonomy_store.load(tg_id)
        items = _taxonomy_leaf_items(tax)
        data = str(query.data or "")
        kind = {
            "menu:categories:rules:add_merchant": "merchant_rule",
            "menu:categories:rules:add_recipient": "recipient_rule",
            "menu:categories:rules:add_alias": "alias",
        }.get(data, "merchant_rule")

        await render_menu_screen(
            query,
            text=templates.menu_categories_rule_pick_leaf_message(_rules_alias_kind_label(kind)),
            reply_markup=build_categories_leaf_picker_keyboard(
                items,
                callback_prefix=f"menu:categories:rules:new:{kind}",
                back_callback="menu:categories:rules",
            ),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str) and c.data.startswith("menu:categories:rules:new:")
    )
    async def cb_menu_categories_rules_new_leaf(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(
            query,
            require_token=True,
            require_accounts=True,
        ):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        raw = str(query.data or "")
        parts = raw.split(":")
        if len(parts) != 6:
            await query.answer("Некоректно", show_alert=True)
            return

        kind = parts[4]
        leaf_id = parts[5]

        tax = ctx.taxonomy_store.load(tg_id)
        try:
            ensure_leaf_target(tax or {}, node_id=leaf_id)
        except Exception:
            await query.answer("Потрібно обрати leaf category", show_alert=True)
            return

        leaf_name = _leaf_name_by_id(tax, leaf_id)
        mem = memory_store.load_memory(tg_id)
        mem["categories_rules_ui"] = {
            "mode": "create",
            "kind": kind,
            "leaf_id": leaf_id,
            "leaf_name": leaf_name,
        }
        memory_store.save_memory(tg_id, mem)
        memory_store.set_pending_manual_mode(
            tg_id,
            expected="categories_rules_term",
            hint="введи фразу",
            source="categories_rules",
            ttl_sec=900,
        )

        if query.message:
            await query.message.answer(
                templates.menu_categories_rule_enter_value_message(
                    _rules_alias_kind_label(kind),
                    leaf_name,
                ),
                reply_markup=build_back_keyboard("menu:categories:rules"),
            )
        await query.answer()

    @dp.callback_query(
        lambda c: isinstance(c.data, str)
        and c.data in {"menu:categories:rules:edit", "menu:categories:rules:delete"}
    )
    async def cb_menu_categories_rules_pick_existing(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(
            query,
            require_token=True,
            require_accounts=True,
        ):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        action = "edit" if str(query.data or "").endswith(":edit") else "delete"
        tax = ctx.taxonomy_store.load(tg_id)
        entries = _rules_alias_entries(ctx, tg_id, tax)

        mem = memory_store.load_memory(tg_id)
        mem["categories_rules_ui"] = {"mode": action, "entries": entries}
        memory_store.save_memory(tg_id, mem)

        rows = [
            [
                (
                    f"{idx + 1}) {str(item.get('value') or '').strip()}",
                    f"menu:categories:rules:{action}pick:{idx}",
                )
            ]
            for idx, item in enumerate(entries[:12])
        ]
        rows.append([("⬅️ Назад", "menu:categories:rules")])

        await render_menu_screen(
            query,
            text=templates.menu_categories_rules_message(_rules_alias_summary(entries)),
            reply_markup=build_rows_keyboard(rows),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str) and c.data.startswith("menu:categories:rules:editpick:")
    )
    async def cb_menu_categories_rules_edit_pick(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(
            query,
            require_token=True,
            require_accounts=True,
        ):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        idx_raw = str(query.data or "").rsplit(":", 1)[1]
        if not idx_raw.isdigit():
            await query.answer("Некоректно", show_alert=True)
            return

        mem = memory_store.load_memory(tg_id)
        state = mem.get("categories_rules_ui")
        entries = state.get("entries") if isinstance(state, dict) else None
        idx = int(idx_raw)
        if not isinstance(entries, list) or idx < 0 or idx >= len(entries):
            await query.answer("Немає елемента", show_alert=True)
            return

        item = entries[idx]
        await render_menu_screen(
            query,
            text=templates.menu_categories_rule_item_message(
                kind_label=_rules_alias_kind_label(str(item.get("kind") or "")),
                current_value=str(item.get("value") or ""),
                leaf_name=str(item.get("leaf_name") or ""),
            ),
            reply_markup=build_categories_rule_item_actions_keyboard(idx),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str) and c.data.startswith("menu:categories:rules:edit:term:")
    )
    async def cb_menu_categories_rules_edit_term(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(
            query,
            require_token=True,
            require_accounts=True,
        ):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        idx_raw = str(query.data or "").rsplit(":", 1)[1]
        if not idx_raw.isdigit():
            await query.answer("Некоректно", show_alert=True)
            return

        mem = memory_store.load_memory(tg_id)
        state = mem.get("categories_rules_ui")
        entries = state.get("entries") if isinstance(state, dict) else None
        idx = int(idx_raw)
        if not isinstance(entries, list) or idx < 0 or idx >= len(entries):
            await query.answer("Немає елемента", show_alert=True)
            return

        item = entries[idx]
        mem["categories_rules_ui"] = {
            "mode": "edit_term",
            "kind": item.get("kind"),
            "entry_id": item.get("id"),
            "value": item.get("value"),
            "leaf_id": item.get("leaf_id"),
            "leaf_name": item.get("leaf_name"),
        }
        memory_store.save_memory(tg_id, mem)
        memory_store.set_pending_manual_mode(
            tg_id,
            expected="categories_rules_term",
            hint="введи нову фразу",
            source="categories_rules",
            ttl_sec=900,
        )

        if query.message:
            await query.message.answer(
                templates.menu_categories_rule_enter_value_message(
                    _rules_alias_kind_label(str(item.get("kind") or "")),
                    str(item.get("leaf_name") or ""),
                ),
                reply_markup=build_back_keyboard("menu:categories:rules"),
            )
        await query.answer()

    @dp.callback_query(
        lambda c: isinstance(c.data, str) and c.data.startswith("menu:categories:rules:edit:leaf:")
    )
    async def cb_menu_categories_rules_edit_leaf(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(
            query,
            require_token=True,
            require_accounts=True,
        ):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        idx_raw = str(query.data or "").rsplit(":", 1)[1]
        if not idx_raw.isdigit():
            await query.answer("Некоректно", show_alert=True)
            return

        mem = memory_store.load_memory(tg_id)
        state = mem.get("categories_rules_ui")
        entries = state.get("entries") if isinstance(state, dict) else None
        idx = int(idx_raw)
        if not isinstance(entries, list) or idx < 0 or idx >= len(entries):
            await query.answer("Немає елемента", show_alert=True)
            return

        tax = ctx.taxonomy_store.load(tg_id)
        items = _taxonomy_leaf_items(tax)
        await render_menu_screen(
            query,
            text=templates.menu_categories_rule_pick_leaf_message("Change leaf"),
            reply_markup=build_categories_leaf_picker_keyboard(
                items,
                callback_prefix=f"menu:categories:rules:setleaf:{idx}",
                back_callback="menu:categories:rules:edit",
            ),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str) and c.data.startswith("menu:categories:rules:setleaf:")
    )
    async def cb_menu_categories_rules_set_leaf(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(
            query,
            require_token=True,
            require_accounts=True,
        ):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        parts = str(query.data or "").split(":")
        if len(parts) != 7:
            await query.answer("Некоректно", show_alert=True)
            return

        idx_raw = parts[5]
        leaf_id = parts[6]
        if not idx_raw.isdigit():
            await query.answer("Некоректно", show_alert=True)
            return

        mem = memory_store.load_memory(tg_id)
        state = mem.get("categories_rules_ui")
        entries = state.get("entries") if isinstance(state, dict) else None
        idx = int(idx_raw)
        if not isinstance(entries, list) or idx < 0 or idx >= len(entries):
            await query.answer("Немає елемента", show_alert=True)
            return

        tax = ctx.taxonomy_store.load(tg_id) or {}
        try:
            ensure_leaf_target(tax, node_id=leaf_id)
        except Exception:
            await query.answer("Потрібно обрати leaf category", show_alert=True)
            return

        item = entries[idx]
        kind = str(item.get("kind") or "")
        value = str(item.get("value") or "").strip()

        if kind in {"merchant_rule", "recipient_rule"}:
            rules = ctx.rules_store.load(tg_id)
            new_rules: list[Rule] = []
            for r in rules:
                if r.id != item.get("id"):
                    new_rules.append(r)
                    continue
                new_rules.append(
                    Rule(
                        id=r.id,
                        leaf_id=leaf_id,
                        merchant_contains=r.merchant_contains,
                        recipient_contains=r.recipient_contains,
                        mcc_in=r.mcc_in,
                        tx_kinds=r.tx_kinds,
                    )
                )
            ctx.rules_store.save(tg_id, new_rules)
        else:
            alias_terms = _load_alias_terms(tax)
            old_leaf_id = str(item.get("leaf_id") or "")
            vals = [x for x in alias_terms.get(old_leaf_id, []) if x != value]
            if vals:
                alias_terms[old_leaf_id] = vals
            elif old_leaf_id in alias_terms:
                alias_terms.pop(old_leaf_id, None)
            leaf_vals = alias_terms.get(leaf_id, [])
            if value not in leaf_vals:
                leaf_vals.append(value)
            alias_terms[leaf_id] = leaf_vals
            ctx.taxonomy_store.save(tg_id, _save_alias_terms(tax, alias_terms))

        await render_menu_screen(
            query,
            text=templates.menu_categories_rule_saved_message(
                kind_label=_rules_alias_kind_label(kind),
                value=value,
                leaf_name=_leaf_name_by_id(tax, leaf_id),
            ),
            reply_markup=build_back_keyboard("menu:categories:rules"),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str) and c.data.startswith("menu:categories:rules:deletepick:")
    )
    async def cb_menu_categories_rules_delete_pick(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(
            query,
            require_token=True,
            require_accounts=True,
        ):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        idx_raw = str(query.data or "").rsplit(":", 1)[1]
        if not idx_raw.isdigit():
            await query.answer("Некоректно", show_alert=True)
            return

        mem = memory_store.load_memory(tg_id)
        state = mem.get("categories_rules_ui")
        entries = state.get("entries") if isinstance(state, dict) else None
        idx = int(idx_raw)
        if not isinstance(entries, list) or idx < 0 or idx >= len(entries):
            await query.answer("Немає елемента", show_alert=True)
            return

        item = entries[idx]
        await render_menu_screen(
            query,
            text=templates.menu_categories_rule_item_message(
                kind_label=_rules_alias_kind_label(str(item.get("kind") or "")),
                current_value=str(item.get("value") or ""),
                leaf_name=str(item.get("leaf_name") or ""),
            ),
            reply_markup=build_categories_rule_delete_confirm_keyboard(idx),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str)
        and c.data.startswith("menu:categories:rules:delete:confirm:")
    )
    async def cb_menu_categories_rules_delete_confirm(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(
            query,
            require_token=True,
            require_accounts=True,
        ):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        idx_raw = str(query.data or "").rsplit(":", 1)[1]
        if not idx_raw.isdigit():
            await query.answer("Некоректно", show_alert=True)
            return

        mem = memory_store.load_memory(tg_id)
        state = mem.get("categories_rules_ui")
        entries = state.get("entries") if isinstance(state, dict) else None
        idx = int(idx_raw)
        if not isinstance(entries, list) or idx < 0 or idx >= len(entries):
            await query.answer("Немає елемента", show_alert=True)
            return

        item = entries[idx]
        kind = str(item.get("kind") or "")
        value = str(item.get("value") or "").strip()

        if kind in {"merchant_rule", "recipient_rule"}:
            rules = [r for r in ctx.rules_store.load(tg_id) if r.id != item.get("id")]
            ctx.rules_store.save(tg_id, rules)
        else:
            tax = ctx.taxonomy_store.load(tg_id) or {}
            alias_terms = _load_alias_terms(tax)
            leaf_id = str(item.get("leaf_id") or "")
            vals = [x for x in alias_terms.get(leaf_id, []) if x != value]
            if vals:
                alias_terms[leaf_id] = vals
            else:
                alias_terms.pop(leaf_id, None)
            ctx.taxonomy_store.save(tg_id, _save_alias_terms(tax, alias_terms))

        await render_menu_screen(
            query,
            text=templates.menu_categories_rule_deleted_message(
                kind_label=_rules_alias_kind_label(kind),
                value=value,
            ),
            reply_markup=build_back_keyboard("menu:categories:rules"),
        )

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data == "menu:categories")
    async def cb_menu_categories(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(
            query,
            require_token=True,
            require_accounts=True,
        ):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        tax = ctx.taxonomy_store.load(tg_id)
        tree_preview = _render_taxonomy_tree_preview(tax)

        await render_menu_screen(
            query,
            text=templates.menu_categories_message(tree_preview),
            reply_markup=build_categories_menu_keyboard(),
        )

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data == "menu:categories:add")
    async def cb_menu_categories_add(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(query, require_token=True, require_accounts=True):
            return
        await render_menu_screen(
            query,
            text="🗂️ *Додати категорію*\n\nОбери розділ.",
            reply_markup=build_rows_keyboard(
                [
                    [("💸 Витрати", "menu:categories:addpick:expense")],
                    [("💰 Доходи", "menu:categories:addpick:income")],
                    [("⬅️ Назад", "menu:categories")],
                ]
            ),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str)
        and c.data in {"menu:categories:addpick:expense", "menu:categories:addpick:income"}
    )
    async def cb_menu_categories_add_pick(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(query, require_token=True, require_accounts=True):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        root_kind = str(query.data or "").rsplit(":", 1)[1]
        _categories_manual_state_save(
            tg_id,
            state={"mode": "add_category", "root_kind": root_kind},
        )
        memory_store.set_pending_manual_mode(
            tg_id,
            expected="categories_name",
            hint="Введи назву категорії (1–60 символів).",
            source="categories",
        )
        await render_menu_screen(
            query,
            text="🗂️ *Додати категорію*\n\nВведи назву нової категорії вручну.",
            reply_markup=build_back_keyboard("menu:categories"),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str) and c.data == "menu:categories:add_subcategory"
    )
    async def cb_menu_categories_add_subcategory(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(query, require_token=True, require_accounts=True):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        tax = ctx.taxonomy_store.load(tg_id)
        items = _taxonomy_category_items(tax)
        await render_menu_screen(
            query,
            text="🗂️ *Додати підкатегорію*\n\nОбери батьківську категорію.",
            reply_markup=_categories_picker_keyboard(
                items,
                callback_prefix="menu:categories:add_subcategory:pick",
                back_callback="menu:categories",
            ),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str)
        and c.data.startswith("menu:categories:add_subcategory:pick:")
    )
    async def cb_menu_categories_add_subcategory_pick(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(query, require_token=True, require_accounts=True):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        parent_id = str(query.data or "").rsplit(":", 1)[1]
        tax = ctx.taxonomy_store.load(tg_id)
        if not isinstance(tax, dict):
            await query.answer("Таксономія ще не налаштована", show_alert=True)
            return

        parent_name = _leaf_name_by_id(tax, parent_id)
        _categories_manual_state_save(
            tg_id,
            state={
                "mode": "add_subcategory",
                "parent_id": parent_id,
                "parent_name": parent_name,
            },
        )
        memory_store.set_pending_manual_mode(
            tg_id,
            expected="categories_name",
            hint="Введи назву підкатегорії (1–60 символів).",
            source="categories",
        )
        await render_menu_screen(
            query,
            text=f"🗂️ *Додати підкатегорію*\n\nБатьківська категорія: *{parent_name}*\n\nВведи назву підкатегорії вручну.",
            reply_markup=build_back_keyboard("menu:categories"),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str)
        and c.data == "menu:categories:add_subcategory:migrate:apply"
    )
    async def cb_menu_categories_add_subcategory_migrate_apply(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(query, require_token=True, require_accounts=True):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        mem = memory_store.load_memory(tg_id)
        state = mem.get("categories_ui")
        if (
            not isinstance(state, dict)
            or str(state.get("mode") or "") != "add_subcategory_migration"
        ):
            await query.answer("Немає активної міграції", show_alert=True)
            return

        tax = ctx.taxonomy_store.load(tg_id)
        if not isinstance(tax, dict):
            await query.answer("Таксономія ще не налаштована", show_alert=True)
            return

        parent_id = str(state.get("parent_id") or "").strip()
        parent_name = str(state.get("parent_name") or "").strip() or parent_id
        new_name = str(state.get("new_subcategory_name") or "").strip()
        migrate_to_leaf_id = str(state.get("migrate_to_leaf_id") or "").strip()

        try:
            new_leaf_id, decision = apply_subcategory_migration_choice(
                tax,
                parent_id=parent_id,
                name=new_name,
                migrate_to_leaf_id=migrate_to_leaf_id,
            )
        except Exception as exc:
            await query.answer(str(exc), show_alert=True)
            return

        if decision is not None:
            rules = ctx.rules_store.load(tg_id)
            updated_rules = []
            changed = False
            for rule in rules:
                if str(getattr(rule, "leaf_id", "") or "").strip() == decision.source_leaf_id:
                    updated_rules.append(
                        Rule(
                            id=rule.id,
                            leaf_id=decision.target_leaf_id,
                            merchant_contains=rule.merchant_contains,
                            recipient_contains=rule.recipient_contains,
                        )
                    )
                    changed = True
                else:
                    updated_rules.append(rule)
            if changed:
                ctx.rules_store.save(tg_id, updated_rules)

            alias_terms = tax.get("alias_terms")
            if not isinstance(alias_terms, dict):
                alias_terms = {}
            moved_terms = list(alias_terms.get(decision.source_leaf_id) or [])
            if moved_terms:
                current = [
                    str(x).strip()
                    for x in alias_terms.get(decision.target_leaf_id, [])
                    if isinstance(x, str) and str(x).strip()
                ]
                for term in moved_terms:
                    if term not in current:
                        current.append(term)
                alias_terms[decision.target_leaf_id] = current
                alias_terms.pop(decision.source_leaf_id, None)
                tax["alias_terms"] = alias_terms

        ctx.taxonomy_store.save(tg_id, tax)
        _categories_manual_state_clear(tg_id)
        memory_store.pop_pending_manual_mode(tg_id)

        lines = []
        if decision is not None:
            lines.append(
                templates.taxonomy_migration_applied_message(
                    source_name=decision.source_leaf_name,
                    target_name=decision.target_leaf_name,
                )
            )
            lines.append("")
        lines.append(f"✅ Підкатегорію збережено: *{parent_name} → {new_name}*")

        await render_menu_screen(
            query,
            text="\n".join(lines),
            reply_markup=build_back_keyboard("menu:categories"),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str)
        and c.data == "menu:categories:add_subcategory:migrate:cancel"
    )
    async def cb_menu_categories_add_subcategory_migrate_cancel(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(query, require_token=True, require_accounts=True):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        _categories_manual_state_clear(tg_id)
        memory_store.pop_pending_manual_mode(tg_id)

        await render_menu_screen(
            query,
            text="Ок, міграцію скасовано.",
            reply_markup=build_back_keyboard("menu:categories"),
        )

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data == "menu:categories:rename")
    async def cb_menu_categories_rename(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(query, require_token=True, require_accounts=True):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        items = _taxonomy_editable_items(ctx.taxonomy_store.load(tg_id))
        await render_menu_screen(
            query,
            text="🗂️ *Перейменувати категорію*\n\nОбери категорію або підкатегорію.",
            reply_markup=_categories_picker_keyboard(
                items,
                callback_prefix="menu:categories:rename:pick",
                back_callback="menu:categories",
            ),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str) and c.data.startswith("menu:categories:rename:pick:")
    )
    async def cb_menu_categories_rename_pick(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(query, require_token=True, require_accounts=True):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        node_id = str(query.data or "").rsplit(":", 1)[1]
        tax = ctx.taxonomy_store.load(tg_id)
        if not isinstance(tax, dict):
            await query.answer("Таксономія ще не налаштована", show_alert=True)
            return

        node_name = _leaf_name_by_id(tax, node_id)
        _categories_manual_state_save(
            tg_id,
            state={"mode": "rename", "node_id": node_id, "node_name": node_name},
        )
        memory_store.set_pending_manual_mode(
            tg_id,
            expected="categories_name",
            hint="Введи нову назву (1–60 символів).",
            source="categories",
        )
        await render_menu_screen(
            query,
            text=f"🗂️ *Перейменувати категорію*\n\nПоточна категорія: *{node_name}*\n\nВведи нову назву вручну.",
            reply_markup=build_back_keyboard("menu:categories"),
        )

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data == "menu:categories:delete")
    async def cb_menu_categories_delete(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(query, require_token=True, require_accounts=True):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        items = _taxonomy_editable_items(ctx.taxonomy_store.load(tg_id))
        await render_menu_screen(
            query,
            text="🗂️ *Видалити категорію*\n\nОбери категорію або підкатегорію.",
            reply_markup=_categories_picker_keyboard(
                items,
                callback_prefix="menu:categories:delete:pick",
                back_callback="menu:categories",
            ),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str) and c.data.startswith("menu:categories:delete:pick:")
    )
    async def cb_menu_categories_delete_pick(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(query, require_token=True, require_accounts=True):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        node_id = str(query.data or "").rsplit(":", 1)[1]
        tax = ctx.taxonomy_store.load(tg_id)
        if not isinstance(tax, dict):
            await query.answer("Таксономія ще не налаштована", show_alert=True)
            return

        node_name = _leaf_name_by_id(tax, node_id)
        try:
            if _rules_or_aliases_reference_leaf(ctx, tg_id, leaf_id=node_id, tax=tax):
                raise ValueError("Категорія використовується в rules / aliases")
            delete_node({**tax, "nodes": dict(tax.get("nodes") or {})}, node_id=node_id)
        except Exception as exc:
            await query.answer(str(exc), show_alert=True)
            return

        await render_menu_screen(
            query,
            text=f"🗂️ *Видалити категорію*\n\nПідтвердити видалення: *{node_name}*?",
            reply_markup=build_rows_keyboard(
                [
                    [("✅ Видалити", f"menu:categories:delete:confirm:{node_id}")],
                    [("❌ Скасувати", "menu:categories:delete")],
                ]
            ),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str) and c.data.startswith("menu:categories:delete:confirm:")
    )
    async def cb_menu_categories_delete_confirm(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(query, require_token=True, require_accounts=True):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        node_id = str(query.data or "").rsplit(":", 1)[1]
        tax = ctx.taxonomy_store.load(tg_id)
        if not isinstance(tax, dict):
            await query.answer("Таксономія ще не налаштована", show_alert=True)
            return

        node_name = _leaf_name_by_id(tax, node_id)
        if _rules_or_aliases_reference_leaf(ctx, tg_id, leaf_id=node_id, tax=tax):
            await query.answer("Категорія використовується в rules / aliases", show_alert=True)
            return

        try:
            delete_node(tax, node_id=node_id)
        except Exception as exc:
            await query.answer(str(exc), show_alert=True)
            return

        ctx.taxonomy_store.save(tg_id, tax)
        await render_menu_screen(
            query,
            text=f"✅ Категорію видалено: *{node_name}*",
            reply_markup=build_back_keyboard("menu:categories"),
        )
