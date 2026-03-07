from __future__ import annotations

from aiogram.types import CallbackQuery

from mono_ai_budget_bot.monobank import MonobankClient
from mono_ai_budget_bot.nlq import memory_store
from mono_ai_budget_bot.reports.config import ReportsConfig, build_reports_preset
from mono_ai_budget_bot.settings.activity import (
    get_activity_toggles,
    normalize_activity_settings,
    set_activity_mode,
    set_activity_toggle,
)
from mono_ai_budget_bot.storage.wipe import wipe_user_financial_cache

from . import templates
from .accounts_ui import render_accounts_screen
from .handlers_common import HandlerContext
from .menu_flow import render_menu_screen, render_placeholder_screen
from .onboarding_flow import begin_manual_token_entry, open_accounts_picker, show_data_status
from .ui import (
    build_activity_custom_toggles_keyboard,
    build_activity_mode_keyboard,
    build_back_keyboard,
    build_bootstrap_history_keyboard,
    build_categories_menu_keyboard,
    build_data_menu_keyboard,
    build_main_menu_keyboard,
    build_personalization_menu_keyboard,
    build_reports_custom_blocks_menu_keyboard,
    build_reports_custom_period_menu_keyboard,
    build_reports_menu_keyboard,
    build_reports_preset_keyboard,
    build_rows_keyboard,
)


def _reports_preset_label_from_profile_or_store(ctx: HandlerContext, tg_id: int, prof: dict) -> str:
    preset = str(prof.get("reports_preset") or "").strip()
    if preset not in {"min", "max", "custom"}:
        cfg = ctx.reports_store.load(tg_id)
        preset = getattr(cfg, "preset", None) or (
            cfg.get("preset") if isinstance(cfg, dict) else None
        )
        if preset not in {"min", "max", "custom"}:
            preset = "min"
        prof["reports_preset"] = preset
    return {"min": "Min", "max": "Max", "custom": "Custom"}.get(preset, "Min")


def _ensure_personalization_profile(ctx: HandlerContext, tg_id: int) -> dict:
    prof = ctx.profile_store.load(tg_id) or {}
    prof = normalize_activity_settings(prof)

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
    return {
        "supportive": "Supportive",
        "rational": "Rational",
        "motivator": "Motivator",
    }.get(value, "—")


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

    @dp.callback_query(
        lambda c: isinstance(c.data, str) and c.data in {"menu:ask", "menu:insights"}
    )
    async def cb_menu_placeholder_sections(query: CallbackQuery) -> None:
        data = str(query.data or "")
        if not await ctx.gate_menu_dependencies(
            query,
            require_token=True,
            require_accounts=True,
            require_ledger=True,
        ):
            return

        title_map = {
            "menu:ask": "💬 *Ask*",
            "menu:insights": "✨ *Insights*",
        }

        await render_placeholder_screen(
            query,
            text=templates.menu_section_placeholder_message(title_map.get(data, "🚧 *Розділ*")),
            reply_markup=build_back_keyboard("menu:root"),
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
            title = "🧑 *Persona*"
            current_value = _persona_label(str(prof.get("persona") or ""))
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
            await render_menu_screen(
                query,
                text=templates.menu_reports_preset_message(reports_label),
                reply_markup=build_reports_preset_keyboard(),
            )
            return
        elif data == "menu:personalization:uncat":
            title = "🧾 *Uncategorized prompts*"
            current_value = _uncat_label(str(prof.get("uncategorized_prompt_frequency") or ""))
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
                reply_markup=build_reports_preset_keyboard(),
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

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data == "menu:categories")
    async def cb_menu_categories(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(
            query,
            require_token=True,
            require_accounts=True,
        ):
            return
        await render_menu_screen(
            query,
            text=templates.menu_categories_message(),
            reply_markup=build_categories_menu_keyboard(),
        )

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data.startswith("menu:categories:"))
    async def cb_menu_categories_placeholders(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(
            query,
            require_token=True,
            require_accounts=True,
        ):
            return
        await render_placeholder_screen(
            query,
            text=templates.menu_categories_action_placeholder_message(),
            reply_markup=build_back_keyboard("menu:categories"),
        )
