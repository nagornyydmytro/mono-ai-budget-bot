from __future__ import annotations

import time

from aiogram.types import CallbackQuery

from mono_ai_budget_bot.nlq import memory_store
from mono_ai_budget_bot.nlq.types import NLQRequest

from . import templates
from .clarify import validate_ok_or_alert
from .handlers_common import HandlerContext


def register_report_handlers(dp, *, ctx: HandlerContext) -> None:
    @dp.callback_query(lambda c: c.data == "menu_week")
    async def cb_menu_week(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_query_or_resume(query):
            return
        if query.message and query.from_user:
            await ctx.send_period_report(query.message, "week", tg_id_override=query.from_user.id)
        await query.answer()

    @dp.callback_query(lambda c: c.data == "menu_month")
    async def cb_menu_month(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_query_or_resume(query):
            return
        if query.message and query.from_user:
            await ctx.send_period_report(query.message, "month", tg_id_override=query.from_user.id)
        await query.answer()

    @dp.callback_query(lambda c: bool(c.data) and str(c.data).startswith("cov_sync:"))
    async def cb_cov_sync(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає user id", show_alert=True)
            return

        raw = (query.data or "").strip()
        parts = raw.split(":", 1)
        if len(parts) != 2 or parts[0] != "cov_sync":
            await query.answer("Некоректно", show_alert=True)
            return

        pid = parts[1].strip()
        ok = memory_store.validate_and_consume_pending(
            tg_id, pending_id=pid, now_ts=int(time.time())
        )
        if not await validate_ok_or_alert(query, ok):
            return

        mem = memory_store.load_memory(tg_id)
        payload = mem.get("pending_intent")
        days_back_raw = payload.get("days_back") if isinstance(payload, dict) else None
        nlq_text = payload.get("nlq_text") if isinstance(payload, dict) else None

        try:
            days_back = int(days_back_raw)
        except Exception:
            days_back = 30
        days_back = max(1, min(days_back, 93))

        cfg = ctx.users.load(tg_id)
        if cfg is None or not cfg.mono_token or not cfg.selected_account_ids:
            if query.message:
                await query.message.answer(templates.need_connect_and_accounts_message())
            memory_store.pop_pending_action(tg_id)
            await query.answer()
            return

        if query.message:
            await query.message.edit_reply_markup(reply_markup=None)
            await query.message.answer(templates.ledger_refresh_progress_message())

        try:
            await ctx.sync_user_ledger(tg_id, cfg, days_back=days_back)
        except Exception:
            memory_store.pop_pending_action(tg_id)
            if query.message:
                await query.message.answer(templates.monobank_generic_error_message())
            await query.answer("Помилка", show_alert=True)
            return

        memory_store.pop_pending_action(tg_id)

        if query.message:
            await query.message.answer(templates.coverage_sync_done_message())

        text = str(nlq_text or "").strip()
        if text and query.message:
            resp = ctx.handle_nlq_fn(
                NLQRequest(
                    telegram_user_id=tg_id,
                    text=text,
                    now_ts=int(time.time()),
                )
            )
            if resp.result:
                await query.message.answer(resp.result.text)

        await query.answer("Ок")

    @dp.callback_query(lambda c: bool(c.data) and str(c.data).startswith("cov_cancel:"))
    async def cb_cov_cancel(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає user id", show_alert=True)
            return

        raw = (query.data or "").strip()
        parts = raw.split(":", 1)
        if len(parts) != 2 or parts[0] != "cov_cancel":
            await query.answer("Некоректно", show_alert=True)
            return

        pid = parts[1].strip()
        ok = memory_store.validate_and_consume_pending(
            tg_id, pending_id=pid, now_ts=int(time.time())
        )
        if not await validate_ok_or_alert(query, ok):
            return

        memory_store.pop_pending_action(tg_id)
        if query.message:
            await query.message.edit_reply_markup(reply_markup=None)
        await query.answer("Скасовано")
