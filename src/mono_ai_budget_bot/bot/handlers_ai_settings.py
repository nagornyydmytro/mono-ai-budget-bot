from __future__ import annotations

from collections.abc import Callable

from aiogram.types import CallbackQuery

from mono_ai_budget_bot.nlq import memory_store
from mono_ai_budget_bot.settings.ai_features import (
    get_ai_features,
    normalize_ai_features_settings,
    render_ai_features_summary,
    reset_ai_features_settings,
    set_ai_feature,
)

from . import templates
from .handlers_common import HandlerContext
from .menu_flow import render_menu_screen
from .ui import (
    build_ai_features_editor_keyboard,
    build_back_keyboard,
    build_personalization_menu_keyboard,
)


def _ai_draft_key() -> str:
    return "ai_features_draft"


def _ai_draft_from_memory_or_profile(ctx: HandlerContext, tg_id: int, prof: dict) -> dict:
    mem = memory_store.load_memory(tg_id)
    draft = mem.get(_ai_draft_key())
    if isinstance(draft, dict):
        return dict(normalize_ai_features_settings({"ai_features": draft}).get("ai_features") or {})
    return dict(get_ai_features(prof))


def _has_ai_draft(tg_id: int) -> bool:
    mem = memory_store.load_memory(tg_id)
    return isinstance(mem.get(_ai_draft_key()), dict)


def _save_ai_draft(tg_id: int, ai_features: dict) -> dict:
    mem = memory_store.load_memory(tg_id)
    mem[_ai_draft_key()] = dict(
        normalize_ai_features_settings({"ai_features": ai_features}).get("ai_features") or {}
    )
    memory_store.save_memory(tg_id, mem)
    return dict(mem[_ai_draft_key()])


def _clear_ai_draft(tg_id: int) -> None:
    mem = memory_store.load_memory(tg_id)
    mem.pop(_ai_draft_key(), None)
    memory_store.save_memory(tg_id, mem)


def _ai_editor_text(*, prof: dict, draft: dict) -> str:
    current_value = render_ai_features_summary(prof)
    draft_value = render_ai_features_summary({"ai_features": draft})
    return templates.menu_ai_features_editor_message(
        current_value=current_value,
        draft_value=draft_value,
    )


async def open_ai_features_editor(
    query: CallbackQuery,
    *,
    ctx: HandlerContext,
    ensure_personalization_profile: Callable[[HandlerContext, int], dict],
) -> None:
    tg_id = query.from_user.id if query.from_user else None
    if tg_id is None:
        await query.answer("Немає tg id", show_alert=True)
        return

    prof = ensure_personalization_profile(ctx, tg_id)
    draft = _ai_draft_from_memory_or_profile(ctx, tg_id, prof)
    draft = _save_ai_draft(tg_id, draft)
    await render_menu_screen(
        query,
        text=_ai_editor_text(prof=prof, draft=draft),
        reply_markup=build_ai_features_editor_keyboard(draft),
    )


def register_ai_settings_handlers(
    dp,
    *,
    ctx: HandlerContext,
    ensure_personalization_profile: Callable[[HandlerContext, int], dict],
    reports_preset_label_from_profile_or_store: Callable[[HandlerContext, int, dict], str],
    persona_label: Callable[[str], str],
    activity_label: Callable[[str], str],
    uncat_label: Callable[[str], str],
    ai_features_label: Callable[[dict], str],
) -> None:
    @dp.callback_query(
        lambda c: isinstance(c.data, str) and c.data.startswith("menu:personalization:ai:toggle:")
    )
    async def cb_menu_personalization_ai_toggle(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_query_or_resume(query):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        prof = ensure_personalization_profile(ctx, tg_id)
        if not _has_ai_draft(tg_id):
            await query.answer(templates.stale_button_message(), show_alert=True)
            return

        key = str(query.data or "").rsplit(":", 1)[1]
        draft = _ai_draft_from_memory_or_profile(ctx, tg_id, prof)
        current = bool(draft.get(key, False))
        try:
            updated = set_ai_feature({"ai_features": draft}, key, (not current))
        except ValueError:
            await query.answer(templates.stale_button_message(), show_alert=True)
            return

        draft = dict(updated.get("ai_features") or {})
        _save_ai_draft(tg_id, draft)
        await render_menu_screen(
            query,
            text=_ai_editor_text(prof=prof, draft=draft),
            reply_markup=build_ai_features_editor_keyboard(draft),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str) and c.data == "menu:personalization:ai:save"
    )
    async def cb_menu_personalization_ai_save(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_query_or_resume(query):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        prof = ensure_personalization_profile(ctx, tg_id)
        if not _has_ai_draft(tg_id):
            await query.answer(templates.stale_button_message(), show_alert=True)
            return

        draft = _ai_draft_from_memory_or_profile(ctx, tg_id, prof)
        prof["ai_features"] = dict(draft)
        prof = normalize_ai_features_settings(prof)
        ctx.profile_store.save(tg_id, prof)
        _clear_ai_draft(tg_id)

        await render_menu_screen(
            query,
            text=templates.menu_ai_features_saved_message(render_ai_features_summary(prof)),
            reply_markup=build_back_keyboard("menu:personalization"),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str) and c.data == "menu:personalization:ai:reset"
    )
    async def cb_menu_personalization_ai_reset(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_query_or_resume(query):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        prof = ensure_personalization_profile(ctx, tg_id)
        draft = dict(reset_ai_features_settings(prof).get("ai_features") or {})
        _save_ai_draft(tg_id, draft)
        await render_menu_screen(
            query,
            text=_ai_editor_text(prof=prof, draft=draft),
            reply_markup=build_ai_features_editor_keyboard(draft),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str) and c.data == "menu:personalization:ai:cancel"
    )
    async def cb_menu_personalization_ai_cancel(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_query_or_resume(query):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        _clear_ai_draft(tg_id)
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
