from __future__ import annotations

from collections.abc import Callable

from aiogram.types import CallbackQuery

from mono_ai_budget_bot.nlq import memory_store
from mono_ai_budget_bot.taxonomy.models import (
    apply_subcategory_migration_choice,
    delete_node,
    ensure_leaf_target,
)
from mono_ai_budget_bot.taxonomy.rules import Rule

from . import templates
from .handlers_common import HandlerContext
from .menu_flow import render_menu_screen
from .ui import (
    build_back_keyboard,
    build_categories_leaf_picker_keyboard,
    build_categories_menu_keyboard,
    build_categories_rule_delete_confirm_keyboard,
    build_categories_rule_item_actions_keyboard,
    build_categories_rules_menu_keyboard,
    build_rows_keyboard,
)


def register_categories_handlers(
    dp,
    *,
    ctx: HandlerContext,
    render_taxonomy_tree_preview: Callable[[dict | None], str],
    rules_alias_entries: Callable[[HandlerContext, int, dict | None], list[dict]],
    rules_alias_summary: Callable[[list[dict]], str],
    rules_alias_kind_label: Callable[[str], str],
    taxonomy_leaf_items: Callable[[dict | None], list[tuple[str, str]]],
    leaf_name_by_id: Callable[[dict | None, str], str],
    taxonomy_category_items: Callable[[dict | None], list[tuple[str, str]]],
    taxonomy_editable_items: Callable[[dict | None], list[tuple[str, str]]],
    categories_picker_keyboard: Callable[..., object],
    categories_manual_state_save: Callable[[int], None],
    categories_manual_state_clear: Callable[[int], None],
    rules_or_aliases_reference_leaf: Callable[[HandlerContext, int, str, dict | None], bool],
    load_alias_terms: Callable[[dict | None], dict[str, list[str]]],
    save_alias_terms: Callable[[dict, dict[str, list[str]]], dict],
) -> None:
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
        entries = rules_alias_entries(ctx, tg_id, tax)

        await render_menu_screen(
            query,
            text=templates.menu_categories_rules_message(rules_alias_summary(entries)),
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
        items = taxonomy_leaf_items(tax)
        data = str(query.data or "")
        kind = {
            "menu:categories:rules:add_merchant": "merchant_rule",
            "menu:categories:rules:add_recipient": "recipient_rule",
            "menu:categories:rules:add_alias": "alias",
        }.get(data, "merchant_rule")

        await render_menu_screen(
            query,
            text=templates.menu_categories_rule_pick_leaf_message(rules_alias_kind_label(kind)),
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

        leaf_name = leaf_name_by_id(tax, leaf_id)
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
                    rules_alias_kind_label(kind),
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
        entries = rules_alias_entries(ctx, tg_id, tax)

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
            text=templates.menu_categories_rules_message(rules_alias_summary(entries)),
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
                kind_label=rules_alias_kind_label(str(item.get("kind") or "")),
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
                    rules_alias_kind_label(str(item.get("kind") or "")),
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
        items = taxonomy_leaf_items(tax)
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
            alias_terms = load_alias_terms(tax)
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
            ctx.taxonomy_store.save(tg_id, save_alias_terms(tax, alias_terms))

        await render_menu_screen(
            query,
            text=templates.menu_categories_rule_saved_message(
                kind_label=rules_alias_kind_label(kind),
                value=value,
                leaf_name=leaf_name_by_id(tax, leaf_id),
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
                kind_label=rules_alias_kind_label(str(item.get("kind") or "")),
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
            alias_terms = load_alias_terms(tax)
            leaf_id = str(item.get("leaf_id") or "")
            vals = [x for x in alias_terms.get(leaf_id, []) if x != value]
            if vals:
                alias_terms[leaf_id] = vals
            else:
                alias_terms.pop(leaf_id, None)
            ctx.taxonomy_store.save(tg_id, save_alias_terms(tax, alias_terms))

        await render_menu_screen(
            query,
            text=templates.menu_categories_rule_deleted_message(
                kind_label=rules_alias_kind_label(kind),
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
        tree_preview = render_taxonomy_tree_preview(tax)

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
        categories_manual_state_save(
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
        items = taxonomy_category_items(tax)
        await render_menu_screen(
            query,
            text="🗂️ *Додати підкатегорію*\n\nОбери батьківську категорію.",
            reply_markup=categories_picker_keyboard(
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

        parent_name = leaf_name_by_id(tax, parent_id)
        categories_manual_state_save(
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
        categories_manual_state_clear(tg_id)
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

        categories_manual_state_clear(tg_id)
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

        items = taxonomy_editable_items(ctx.taxonomy_store.load(tg_id))
        await render_menu_screen(
            query,
            text="🗂️ *Перейменувати категорію*\n\nОбери категорію або підкатегорію.",
            reply_markup=categories_picker_keyboard(
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

        node_name = leaf_name_by_id(tax, node_id)
        categories_manual_state_save(
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

        items = taxonomy_editable_items(ctx.taxonomy_store.load(tg_id))
        await render_menu_screen(
            query,
            text="🗂️ *Видалити категорію*\n\nОбери категорію або підкатегорію.",
            reply_markup=categories_picker_keyboard(
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

        node_name = leaf_name_by_id(tax, node_id)
        try:
            if rules_or_aliases_reference_leaf(ctx, tg_id, leaf_id=node_id, tax=tax):
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

        node_name = leaf_name_by_id(tax, node_id)
        if rules_or_aliases_reference_leaf(ctx, tg_id, leaf_id=node_id, tax=tax):
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
