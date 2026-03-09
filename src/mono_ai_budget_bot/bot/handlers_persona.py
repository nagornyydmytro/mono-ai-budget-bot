from __future__ import annotations

from collections.abc import Callable

from aiogram.types import CallbackQuery

from mono_ai_budget_bot.nlq import memory_store
from mono_ai_budget_bot.settings.persona import (
    normalize_persona_settings,
    render_persona_summary,
    reset_persona_settings,
    set_persona_field,
)

from . import templates
from .handlers_common import HandlerContext
from .menu_flow import render_menu_screen
from .ui import (
    build_back_keyboard,
    build_persona_editor_keyboard,
    build_persona_preview_keyboard,
    build_personalization_menu_keyboard,
)


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


def _save_persona_draft(tg_id: int, persona_profile: dict) -> dict:
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


async def open_persona_editor(
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
    draft = _persona_draft_from_memory_or_profile(ctx, tg_id, prof)
    draft = _save_persona_draft(tg_id, draft)
    await render_menu_screen(
        query,
        text=_persona_editor_text(prof=prof, draft=draft),
        reply_markup=build_persona_editor_keyboard(draft),
    )


def register_persona_handlers(
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
        prof = ensure_personalization_profile(ctx, tg_id)
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

        _save_persona_draft(tg_id, draft)
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

        prof = ensure_personalization_profile(ctx, tg_id)
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

        prof = ensure_personalization_profile(ctx, tg_id)
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

        prof = ensure_personalization_profile(ctx, tg_id)
        draft = dict(reset_persona_settings(prof).get("persona_profile") or {})
        _save_persona_draft(tg_id, draft)
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
