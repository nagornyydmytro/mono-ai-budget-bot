from __future__ import annotations

from aiogram.types import CallbackQuery

from mono_ai_budget_bot.monobank import MonobankClient
from mono_ai_budget_bot.nlq import memory_store
from mono_ai_budget_bot.storage.wipe import wipe_user_financial_cache

from . import templates
from .accounts_ui import render_accounts_screen
from .handlers_common import HandlerContext
from .menu_flow import render_menu_screen, render_placeholder_screen
from .onboarding_flow import begin_manual_token_entry, open_accounts_picker, show_data_status
from .ui import (
    build_back_keyboard,
    build_bootstrap_history_keyboard,
    build_categories_menu_keyboard,
    build_data_menu_keyboard,
    build_main_menu_keyboard,
    build_reports_menu_keyboard,
    build_rows_keyboard,
)


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
        lambda c: isinstance(c.data, str)
        and c.data in {"menu:ask", "menu:insights", "menu:personalization"}
    )
    async def cb_menu_placeholder_sections(query: CallbackQuery) -> None:
        data = str(query.data or "")
        if data in {"menu:ask", "menu:insights"}:
            if not await ctx.gate_menu_dependencies(
                query,
                require_token=True,
                require_accounts=True,
                require_ledger=True,
            ):
                return
        else:
            if not await ctx.gate_menu_query_or_resume(query):
                return

        title_map = {
            "menu:ask": "💬 *Ask*",
            "menu:insights": "✨ *Insights*",
            "menu:personalization": "🎛️ *Персоналізація*",
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
