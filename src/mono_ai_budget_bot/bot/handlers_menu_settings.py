from __future__ import annotations

from collections.abc import Callable

from aiogram.types import CallbackQuery

from mono_ai_budget_bot.reports.config import ReportsConfig, build_reports_preset
from mono_ai_budget_bot.settings.activity import (
    get_activity_toggles,
    set_activity_mode,
    set_activity_toggle,
)
from mono_ai_budget_bot.settings.onboarding import apply_onboarding_settings

from . import templates
from .handlers_ai_settings import open_ai_features_editor, register_ai_settings_handlers
from .handlers_common import HandlerContext
from .handlers_persona import open_persona_editor, register_persona_handlers
from .menu_flow import render_menu_screen
from .ui import (
    build_activity_custom_toggles_keyboard,
    build_activity_mode_keyboard,
    build_personalization_menu_keyboard,
    build_reports_custom_blocks_menu_keyboard,
    build_reports_custom_period_menu_keyboard,
    build_reports_preset_keyboard,
    build_saved_to_root_keyboard,
    build_uncat_frequency_keyboard,
)


def register_settings_handlers(
    dp,
    *,
    ctx: HandlerContext,
    ensure_personalization_profile: Callable[[HandlerContext, int], dict],
    reports_preset_label_from_profile_or_store: Callable[[HandlerContext, int, dict], str],
    reports_preset_key_from_profile_or_store: Callable[[HandlerContext, int, dict], str],
    persona_label: Callable[[str], str],
    activity_label: Callable[[str], str],
    uncat_label: Callable[[str], str],
    ai_features_label: Callable[[dict], str],
    save_reports_preset_profile: Callable[[HandlerContext, int, dict, str], None],
) -> None:
    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data == "menu:personalization")
    async def cb_menu_personalization(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_query_or_resume(query):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        prof = ensure_personalization_profile(ctx, tg_id)
        reports_label = reports_preset_label_from_profile_or_store(ctx, tg_id, prof)

        await render_menu_screen(
            query,
            text=templates.menu_personalization_message(
                persona_label=persona_label(str(prof.get("persona") or "")),
                activity_label=activity_label(str(prof.get("activity_mode") or "")),
                reports_label=reports_label,
                uncat_label=uncat_label(str(prof.get("uncategorized_prompt_frequency") or "")),
                ai_label=ai_features_label(prof),
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

        prof = ensure_personalization_profile(ctx, tg_id)
        reports_label = reports_preset_label_from_profile_or_store(ctx, tg_id, prof)

        data = str(query.data or "")
        if data == "menu:personalization:persona":
            await open_persona_editor(
                query,
                ctx=ctx,
                ensure_personalization_profile=ensure_personalization_profile,
            )
            return
        if data == "menu:personalization:activity":
            await render_menu_screen(
                query,
                text=templates.menu_activity_mode_message(
                    activity_label(str(prof.get("activity_mode") or ""))
                ),
                reply_markup=build_activity_mode_keyboard(str(prof.get("activity_mode") or "")),
            )
            return
        if data == "menu:personalization:reports":
            preset_key = reports_preset_key_from_profile_or_store(ctx, tg_id, prof)
            await render_menu_screen(
                query,
                text=templates.menu_reports_preset_message(reports_label),
                reply_markup=build_reports_preset_keyboard(preset_key),
            )
            return
        if data == "menu:personalization:uncat":
            current_value = str(prof.get("uncategorized_prompt_frequency") or "")
            await render_menu_screen(
                query,
                text=templates.menu_uncat_frequency_message(uncat_label(current_value)),
                reply_markup=build_uncat_frequency_keyboard(current_value),
            )
            return

        await open_ai_features_editor(
            query,
            ctx=ctx,
            ensure_personalization_profile=ensure_personalization_profile,
        )

    register_persona_handlers(
        dp,
        ctx=ctx,
        ensure_personalization_profile=ensure_personalization_profile,
        reports_preset_label_from_profile_or_store=reports_preset_label_from_profile_or_store,
        persona_label=persona_label,
        activity_label=activity_label,
        uncat_label=uncat_label,
        ai_features_label=ai_features_label,
    )

    register_ai_settings_handlers(
        dp,
        ctx=ctx,
        ensure_personalization_profile=ensure_personalization_profile,
        reports_preset_label_from_profile_or_store=reports_preset_label_from_profile_or_store,
        persona_label=persona_label,
        activity_label=activity_label,
        uncat_label=uncat_label,
        ai_features_label=ai_features_label,
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
        prof = ensure_personalization_profile(ctx, tg_id)
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
            text=templates.menu_activity_mode_message(activity_label(mode)),
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
        prof = ensure_personalization_profile(ctx, tg_id)
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
        prof = ensure_personalization_profile(ctx, tg_id)
        prof = apply_onboarding_settings(prof, uncategorized_prompt_frequency=freq)
        ctx.profile_store.save(tg_id, prof)

        await render_menu_screen(
            query,
            text=templates.menu_uncat_frequency_message(uncat_label(freq)),
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

        prof = ensure_personalization_profile(ctx, tg_id)
        data = str(query.data or "")
        preset = data.rsplit(":", 1)[1]

        if preset in {"min", "max"}:
            cfg = build_reports_preset(preset)
            ctx.reports_store.save(tg_id, cfg)
            save_reports_preset_profile(ctx, tg_id, prof, preset)

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

        save_reports_preset_profile(ctx, tg_id, prof, "custom")

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

        prof = ensure_personalization_profile(ctx, tg_id)
        save_reports_preset_profile(ctx, tg_id, prof, "custom")

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
