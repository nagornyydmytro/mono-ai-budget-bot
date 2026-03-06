from __future__ import annotations

import asyncio
from datetime import datetime

from aiogram.filters import Command
from aiogram.types import Message

from mono_ai_budget_bot.nlq import memory_store

from ..monobank import MonobankClient
from . import templates
from .accounts_ui import mask_secret, render_accounts_screen
from .errors import map_monobank_error
from .handlers_common import HandlerContext
from .renderers import md_escape
from .report_flow_helpers import compute_and_cache_reports_for_user
from .ui import build_main_menu_keyboard, build_onboarding_resume_keyboard


def register_dev_handlers(dp, *, ctx: HandlerContext) -> None:
    @dp.message(Command("menu"))
    async def cmd_menu(message: Message) -> None:
        tg_id = message.from_user.id if message.from_user else None
        if tg_id is None:
            return

        ctx.sync_onboarding_progress(tg_id)
        onboarding_done = ctx.onboarding_done(tg_id)

        if not onboarding_done:
            kb = build_onboarding_resume_keyboard()
            await message.answer(
                templates.menu_finish_onboarding_message(),
                reply_markup=kb,
            )
            return

        kb = build_main_menu_keyboard(uncat_enabled=True)
        await message.answer(templates.menu_root_message(), reply_markup=kb)

    @dp.message(Command("connect"))
    async def cmd_connect(message: Message) -> None:
        parts = (message.text or "").split(maxsplit=1)

        if len(parts) < 2 or not parts[1].strip():
            await message.answer(templates.connect_instructions())
            return

        mono_token = parts[1].strip()

        if len(mono_token) < 20:
            await message.answer(templates.connect_validation_error())
            return

        tg_id = message.from_user.id if message.from_user else None
        if tg_id is None:
            await message.answer(templates.error("Не зміг визначити твій Telegram user id."))
            return

        await message.answer(templates.connect_token_validation_progress())

        try:
            mb = MonobankClient(token=mono_token)
            try:
                mb.client_info()
            finally:
                mb.close()
        except Exception as e:
            mapped = map_monobank_error(e)
            await message.answer(mapped or templates.error("Помилка перевірки токена."))
            return

        ctx.users.save(tg_id, mono_token=mono_token, selected_account_ids=[])
        ctx.sync_onboarding_progress(tg_id)

        kb = build_onboarding_resume_keyboard()
        await message.answer(templates.connect_success_confirm())
        await message.answer(templates.connect_success_next_steps(), reply_markup=kb)

    @dp.message(Command("status"))
    async def cmd_status(message: Message) -> None:
        tg_id = message.from_user.id if message.from_user else None
        cfg = ctx.users.load(tg_id) if tg_id is not None else None

        if cfg is None:
            await message.answer(templates.status_screen_not_connected())
            return

        masked = md_escape(mask_secret(cfg.mono_token)) if getattr(cfg, "mono_token", None) else "—"
        selected_cnt = len(cfg.selected_account_ids or [])

        cache_lines: dict[str, str | None] = {}
        for p in ("today", "week", "month"):
            stored = ctx.store.load(cfg.telegram_user_id, p)
            if stored is None:
                cache_lines[p] = None
            else:
                ts = datetime.fromtimestamp(stored.generated_at).isoformat(timespec="seconds")
                cache_lines[p] = md_escape(ts)

        await message.answer(
            templates.status_screen_connected(
                masked_token=masked,
                selected_cnt=selected_cnt,
                cache_lines=cache_lines,
            )
        )

    @dp.message(Command("accounts"))
    async def cmd_accounts(message: Message) -> None:
        tg_id = message.from_user.id if message.from_user else None
        if tg_id is None:
            await message.answer(templates.error("Не зміг визначити твій Telegram user id."))
            return

        cfg = ctx.users.load(tg_id)
        if cfg is None or not cfg.mono_token:
            await message.answer(templates.err_not_connected())
            return

        mb = MonobankClient(token=cfg.mono_token)
        try:
            info = mb.client_info()
        except Exception as e:
            msg = map_monobank_error(e)
            await message.answer(msg or templates.error(f"Помилка Monobank: {md_escape(str(e))}"))
            return
        finally:
            mb.close()

        accounts = [
            {"id": a.id, "currencyCode": a.currencyCode, "maskedPan": a.maskedPan}
            for a in info.accounts
        ]
        selected_ids = set(cfg.selected_account_ids or [])
        text, kb = render_accounts_screen(accounts, selected_ids)
        await message.answer(text, reply_markup=kb)

    @dp.message(Command("refresh"))
    async def cmd_refresh(message: Message) -> None:
        tg_id = message.from_user.id if message.from_user else None
        if tg_id is None:
            await message.answer(templates.error("Не зміг визначити твій Telegram user id."))
            return

        cfg = ctx.users.load(tg_id)
        if cfg is None or not cfg.mono_token:
            await message.answer(templates.err_not_connected())
            return

        account_ids = list(cfg.selected_account_ids or [])
        if not account_ids:
            await message.answer(templates.err_no_accounts_selected())
            return

        parts = (message.text or "").split()
        arg = parts[1].strip().lower() if len(parts) > 1 else "week"

        if arg not in ("today", "week", "month", "all"):
            await message.answer(templates.refresh_usage_message())
            return

        if arg == "today":
            days_back = 2
        elif arg == "week":
            days_back = 8
        elif arg == "month":
            days_back = 32
        else:
            days_back = 90

        await message.answer(templates.refresh_started_message(days_back))

        chat_id = message.chat.id
        token = cfg.mono_token

        async def job() -> None:
            try:
                async with ctx.user_locks[tg_id]:
                    from ..monobank.sync import sync_accounts_ledger

                    def _run_sync() -> object:
                        mb = MonobankClient(token=token)
                        try:
                            return sync_accounts_ledger(
                                mb=mb,
                                tx_store=ctx.tx_store,
                                telegram_user_id=tg_id,
                                account_ids=account_ids,
                                days_back=days_back,
                            )
                        finally:
                            mb.close()

                    res = await asyncio.to_thread(_run_sync)

                    await compute_and_cache_reports_for_user(tg_id, account_ids, ctx.profile_store)

                    await ctx.bot.send_message(
                        chat_id,
                        templates.refresh_done_message(
                            accounts=res.accounts,
                            fetched_requests=res.fetched_requests,
                            appended=res.appended,
                        ),
                    )
            except Exception as e:
                msg = map_monobank_error(e)
                await ctx.bot.send_message(
                    chat_id,
                    templates.error(f"Помилка оновлення: {md_escape(msg or str(e))}"),
                )

        asyncio.create_task(job())

    @dp.message(Command("aliases"))
    async def cmd_aliases(message: Message) -> None:
        tg_id = message.from_user.id if message.from_user else None
        if tg_id is None:
            await message.answer(templates.error("Не зміг визначити user id."))
            return

        mem = memory_store.load_memory(tg_id)
        merchant_aliases = mem.get("merchant_aliases", {})
        recipient_aliases = mem.get("recipient_aliases", {})

        if not merchant_aliases and not recipient_aliases:
            await message.answer(templates.aliases_empty_message())
            return

        await message.answer(templates.aliases_list_message(merchant_aliases, recipient_aliases))

    @dp.message(Command("aliases_clear"))
    async def cmd_aliases_clear(message: Message) -> None:
        tg_id = message.from_user.id if message.from_user else None
        if tg_id is None:
            await message.answer(templates.error("Не зміг визначити user id."))
            return

        memory_store.save_memory(
            tg_id,
            {"merchant_aliases": {}, "recipient_aliases": {}},
        )
        await message.answer(templates.aliases_cleared_message())

    @dp.message(Command("today"))
    async def cmd_today(message: Message) -> None:
        await ctx.send_period_report(message, "today")

    @dp.message(Command("week"))
    async def cmd_week(message: Message) -> None:
        await ctx.send_period_report(message, "week")

    @dp.message(Command("month"))
    async def cmd_month(message: Message) -> None:
        await ctx.send_period_report(message, "month")

    @dp.message(Command("autojobs"))
    async def cmd_autojobs(message: Message) -> None:
        tg_id = message.from_user.id
        cfg = ctx.users.load(tg_id)
        if cfg is None:
            await message.answer(templates.need_connect_with_hint_message())
            return

        parts = (message.text or "").split()
        action = parts[1].lower() if len(parts) > 1 else "status"

        if action == "on":
            ctx.users.save(tg_id, autojobs_enabled=True)
            await message.answer(templates.success("Автозвіти увімкнено"))
            return
        if action == "off":
            ctx.users.save(tg_id, autojobs_enabled=False)
            await message.answer(templates.success("Автозвіти вимкнено"))
            return

        cfg2 = ctx.users.load(tg_id)
        await message.answer(
            templates.autojobs_status_line(enabled=bool(cfg2 and cfg2.autojobs_enabled))
        )
