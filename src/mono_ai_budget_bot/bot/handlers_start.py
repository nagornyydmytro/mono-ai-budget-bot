from __future__ import annotations

from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from mono_ai_budget_bot.nlq import memory_store

from . import templates
from .handlers_common import HandlerContext
from .onboarding_flow import send_start_screen
from .ui import (
    build_back_keyboard,
    build_main_menu_keyboard,
    build_start_menu_keyboard,
)


def register_start_handlers(dp, *, ctx: HandlerContext) -> None:
    @dp.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        tg_id = message.from_user.id if message.from_user else None
        if tg_id is None:
            return

        ctx.users.save(tg_id, chat_id=message.chat.id)
        cfg = ctx.users.load(tg_id)

        ctx.sync_onboarding_progress(tg_id)
        onboarding_done = ctx.onboarding_done(tg_id)

        kb = build_start_menu_keyboard()

        text = templates.start_message()
        if cfg is not None and cfg.mono_token and not onboarding_done:
            text = templates.start_message_connected()

        await message.answer(text, reply_markup=kb)

    @dp.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        tg_id = message.from_user.id if message.from_user else None
        if tg_id is None:
            return

        cfg = ctx.users.load(tg_id)
        if cfg is None or not cfg.mono_token or not cfg.selected_account_ids:
            kb = build_back_keyboard("onb_back_main")
            await message.answer(templates.help_message(), reply_markup=kb)
            return

        kb = build_main_menu_keyboard(uncat_enabled=True)
        await message.answer(templates.help_message(), reply_markup=kb)

    @dp.callback_query(lambda c: c.data == "onb_back_main")
    async def cb_onb_back_main(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if query.message and tg_id is not None:
            memory_store.pop_pending_manual_mode(tg_id)
            await send_start_screen(
                query.message,
                users=ctx.users,
                tg_id=tg_id,
                start_text=templates.start_message(),
                connected_text=templates.start_message_connected(),
                reply_markup=build_start_menu_keyboard(),
            )
        await query.answer()

    @dp.callback_query(lambda c: c.data == "onb_resume")
    async def cb_onb_resume(query: CallbackQuery) -> None:
        await query.answer()
        await ctx.send_onboarding_next(query)

    @dp.callback_query(lambda c: c.data == "menu:currency")
    async def cb_menu_currency(query: CallbackQuery) -> None:
        if query.message:
            await ctx.send_currency_screen(query.message, force_refresh=False)
        await query.answer()

    @dp.callback_query(lambda c: c.data == "currency_refresh")
    async def cb_currency_refresh(query: CallbackQuery) -> None:
        if query.message:
            await query.message.answer(templates.currency_refresh_progress_message())
            await ctx.send_currency_screen(query.message, force_refresh=True)
        await query.answer("Оновлено")

    @dp.callback_query(lambda c: c.data == "currency_back")
    async def cb_currency_back(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer()
            return

        ctx.sync_onboarding_progress(tg_id)
        onboarding_done = ctx.onboarding_done(tg_id)

        if query.message:
            if not onboarding_done:
                kb = build_start_menu_keyboard()
                text = templates.start_message()
                cfg = ctx.users.load(tg_id)
                if cfg is not None and cfg.mono_token:
                    text = templates.start_message_connected()
                await query.message.answer(text, reply_markup=kb)
            else:
                kb = build_main_menu_keyboard(uncat_enabled=True)
                await query.message.answer(templates.menu_root_message(), reply_markup=kb)

        await query.answer()

    @dp.callback_query(lambda c: c.data == "menu:help")
    async def cb_menu_help(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer()
            return

        if query.message:
            ctx.sync_onboarding_progress(tg_id)
            onboarding_done = ctx.onboarding_done(tg_id)

            if not onboarding_done:
                kb = build_back_keyboard("onb_back_main")
                await query.message.answer(templates.help_message(), reply_markup=kb)
            else:
                kb = build_main_menu_keyboard(uncat_enabled=True)
                await query.message.answer(templates.help_message(), reply_markup=kb)

        await query.answer()
