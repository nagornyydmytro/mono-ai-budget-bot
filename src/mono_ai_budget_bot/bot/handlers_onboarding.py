from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from aiogram.types import CallbackQuery

from mono_ai_budget_bot.nlq import memory_store
from mono_ai_budget_bot.reports.config import ReportsConfig, build_reports_preset
from mono_ai_budget_bot.settings.onboarding import apply_onboarding_settings
from mono_ai_budget_bot.storage.wipe import wipe_user_financial_cache
from mono_ai_budget_bot.taxonomy.presets import build_taxonomy_preset

from ..monobank import MonobankClient
from . import templates
from .accounts_ui import render_accounts_screen, save_selected_accounts
from .errors import map_monobank_error
from .handlers_common import HandlerContext
from .onboarding_flow import begin_manual_token_entry
from .renderers import md_escape
from .report_flow_helpers import compute_and_cache_reports_for_user
from .ui import (
    build_back_keyboard,
    build_bootstrap_picker_keyboard,
    build_reports_custom_blocks_keyboard,
    build_reports_custom_period_keyboard,
    build_vertical_options_keyboard,
)

if TYPE_CHECKING:
    pass


def register_onboarding_handlers(dp, *, ctx: HandlerContext) -> None:
    @dp.callback_query(lambda c: c.data and c.data.startswith("acc_toggle:"))
    async def cb_toggle_account(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Помилка: нема user id", show_alert=True)
            return

        cfg = ctx.users.load(tg_id)
        if cfg is None:
            await query.answer("Спочатку підключи Monobank.", show_alert=True)
            return

        acc_id = (query.data or "").split("acc_toggle:", 1)[1].strip()
        selected = set(cfg.selected_account_ids or [])

        if acc_id in selected:
            selected.remove(acc_id)
        else:
            selected.add(acc_id)

        save_selected_accounts(ctx.users, tg_id, sorted(selected))

        prof = ctx.profile_store.load(tg_id) or {}
        onb = prof.get("onboarding")
        if not isinstance(onb, dict):
            onb = {}
        onb["accounts_confirmed"] = False
        prof["onboarding"] = onb
        ctx.profile_store.save(tg_id, prof)

        ctx.sync_onboarding_progress(tg_id)

        mb = MonobankClient(token=cfg.mono_token)
        try:
            info = mb.client_info()
        except Exception as e:
            msg = map_monobank_error(e)
            await query.answer(msg or "Помилка Monobank", show_alert=True)
            return
        finally:
            mb.close()

        accounts = [
            {"id": a.id, "currencyCode": a.currencyCode, "maskedPan": a.maskedPan}
            for a in info.accounts
        ]
        text, kb = render_accounts_screen(accounts, set(selected))

        if query.message:
            prefix = f"{templates.connect_success_confirm()}\n\n"
            await query.message.edit_text(f"{prefix}{text}", reply_markup=kb)
        await query.answer()

    @dp.callback_query(lambda c: c.data == "acc_clear")
    async def cb_clear_accounts(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Помилка: нема user id", show_alert=True)
            return

        cfg = ctx.users.load(tg_id)
        if cfg is None:
            await query.answer("Спочатку підключи Monobank.", show_alert=True)
            return

        selected_ids = set(cfg.selected_account_ids or [])
        if not selected_ids:
            await query.answer("Нічого очищати")
            return

        save_selected_accounts(ctx.users, tg_id, [])

        prof = ctx.profile_store.load(tg_id) or {}
        onb = prof.get("onboarding")
        if not isinstance(onb, dict):
            onb = {}
        onb["accounts_confirmed"] = False
        prof["onboarding"] = onb
        ctx.profile_store.save(tg_id, prof)

        ctx.sync_onboarding_progress(tg_id)

        mb = MonobankClient(token=cfg.mono_token)
        try:
            info = mb.client_info()
        finally:
            mb.close()

        accounts = [
            {"id": a.id, "currencyCode": a.currencyCode, "maskedPan": a.maskedPan}
            for a in info.accounts
        ]
        text, kb = render_accounts_screen(accounts, set())

        if query.message:
            prefix = f"{templates.connect_success_confirm()}\n\n"
            await query.message.edit_text(f"{prefix}{text}", reply_markup=kb)

        await query.answer()

    @dp.callback_query(lambda c: c.data == "acc_done")
    async def cb_done_accounts(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        cfg = ctx.users.load(tg_id) if tg_id is not None else None

        count = len(cfg.selected_account_ids) if cfg else 0
        if count <= 0:
            await query.answer("Спочатку вибери хоча б 1 картку", show_alert=True)
            return

        ctx.sync_onboarding_progress(tg_id)
        onboarding_done = ctx.onboarding_done(tg_id)

        mem = memory_store.load_memory(tg_id) if tg_id is not None else {}
        picker = mem.get("accounts_picker") if isinstance(mem, dict) else None
        source = picker.get("source") if isinstance(picker, dict) else None
        prev_selected = picker.get("prev_selected") if isinstance(picker, dict) else None
        prev_set = set(prev_selected) if isinstance(prev_selected, list) else None
        cur_set = set(cfg.selected_account_ids or []) if cfg else set()
        changed = bool(source == "data_menu" and prev_set is not None and prev_set != cur_set)

        if changed and tg_id is not None:
            wipe_user_financial_cache(
                tg_id,
                tx_store=ctx.tx_store,
                report_store=ctx.store,
                rules_store=ctx.rules_store,
                uncat_store=ctx.uncat_store,
                uncat_pending_store=ctx.uncat_pending_store,
            )

        if isinstance(mem, dict):
            mem.pop("accounts_picker", None)
            memory_store.save_memory(tg_id, mem)

        prof = ctx.profile_store.load(tg_id) or {}
        onb = prof.get("onboarding")
        if not isinstance(onb, dict):
            onb = {}
        onb["accounts_confirmed"] = True
        prof["onboarding"] = onb
        ctx.profile_store.save(tg_id, prof)

        kb = build_bootstrap_picker_keyboard(include_skip=(onboarding_done and not changed))

        if query.message:
            await query.message.edit_text(
                templates.accounts_after_done_with_count(count),
                reply_markup=kb,
            )
        await query.answer()

    @dp.callback_query(lambda c: c.data == "menu_connect")
    async def cb_menu_connect(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer()
            return

        ctx.sync_onboarding_progress(tg_id)
        cfg = ctx.users.load(tg_id)
        onboarding_done = ctx.onboarding_done(tg_id)

        if cfg is not None and cfg.mono_token and not onboarding_done:
            await query.answer()
            await ctx.send_onboarding_next(query)
            return

        if query.message:
            kb = build_vertical_options_keyboard(
                [("✅ Ввести токен", "onb_token"), ("⬅️ Назад", "onb_back_main")]
            )
            await query.message.edit_text(templates.connect_instructions(), reply_markup=kb)
        await query.answer()

    @dp.callback_query(lambda c: c.data == "onb_token")
    async def cb_onb_token(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        await begin_manual_token_entry(
            query,
            tg_id=tg_id,
            set_pending_manual_mode=memory_store.set_pending_manual_mode,
            hint=templates.token_paste_hint_connect(),
            source="onboarding",
            prompt_text=templates.onboarding_token_paste_prompt(),
            reply_markup=build_back_keyboard("onb_back_main"),
            answer_text="Ок",
        )

    @dp.callback_query(
        lambda c: c.data in ("boot_30", "boot_90", "boot_180", "boot_365", "boot_skip")
    )
    async def cb_bootstrap(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        cfg = ctx.users.load(tg_id)
        if cfg is None or not cfg.mono_token:
            await query.answer("Спочатку підключи Monobank.", show_alert=True)
            return

        account_ids = list(cfg.selected_account_ids or [])
        if not account_ids:
            await query.answer("Спочатку вибери картки.", show_alert=True)
            return

        if query.data == "boot_skip":
            ctx.sync_onboarding_progress(tg_id)
            onboarding_done = ctx.onboarding_done(tg_id)
            if not onboarding_done:
                await query.answer("На онбордингу пропуск недоступний.", show_alert=True)
                return

            if query.message:
                await query.message.edit_text("Ок.")

            await query.answer("Пропущено")
            return

        days_map = {"boot_30": 30, "boot_90": 90, "boot_180": 180, "boot_365": 365}
        days = int(days_map[str(query.data)])

        prof = ctx.profile_store.load(tg_id) or {}
        onb = prof.get("onboarding")
        if not isinstance(onb, dict):
            onb = {}
        onb["bootstrap_requested"] = True
        onb["bootstrap_days"] = days
        prof["onboarding"] = onb
        ctx.profile_store.save(tg_id, prof)

        if query.message:
            await query.message.edit_text(templates.bootstrap_started_message(days))
        await query.answer("Старт")

        kb2 = build_vertical_options_keyboard(
            [
                ("⚡ Мінімальний", "tax_preset_min"),
                ("🧠 Максимальний (детально)", "tax_preset_max"),
                ("🛠️ Custom — налаштую потім", "tax_preset_custom"),
            ]
        )

        if query.message:
            await query.message.answer(
                templates.taxonomy_preset_prompt(),
                reply_markup=kb2,
            )

        chat_id = query.message.chat.id if query.message else None
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
                                days_back=days,
                            )
                        finally:
                            mb.close()

                    res = await asyncio.to_thread(_run_sync)

                    await compute_and_cache_reports_for_user(
                        tg_id,
                        account_ids,
                        ctx.profile_store,
                    )

                    if chat_id is not None:
                        ctx.sync_onboarding_progress(tg_id)
                        onboarding_done = ctx.onboarding_done(tg_id)

                        if onboarding_done:
                            text = templates.bootstrap_done_message(
                                accounts=res.accounts,
                                fetched_requests=res.fetched_requests,
                                appended=res.appended,
                            )
                        else:
                            text = templates.bootstrap_done_onboarding_message()

                        await ctx.bot.send_message(chat_id, text)

            except Exception as e:
                if chat_id is not None:
                    msg = map_monobank_error(e)
                    await ctx.bot.send_message(
                        chat_id,
                        templates.error(f"Помилка bootstrap: {md_escape(msg or str(e))}"),
                    )

        asyncio.create_task(job())

    @dp.callback_query(
        lambda c: c.data in ("tax_preset_min", "tax_preset_max", "tax_preset_custom")
    )
    async def cb_tax_preset(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        preset_map = {
            "tax_preset_min": "min",
            "tax_preset_max": "max",
            "tax_preset_custom": "custom",
        }
        preset = preset_map[str(query.data)]
        tax = build_taxonomy_preset(preset)
        ctx.taxonomy_store.save(tg_id, tax)

        prof = ctx.profile_store.load(tg_id) or {}
        onb = prof.get("onboarding")
        if not isinstance(onb, dict):
            onb = {}
        onb["taxonomy_configured"] = True
        prof["onboarding"] = onb
        ctx.profile_store.save(tg_id, prof)

        ctx.sync_onboarding_progress(tg_id)

        kb = build_vertical_options_keyboard(
            [
                ("⚡ Мінімальний", "rep_preset_min"),
                ("🧠 Максимальний", "rep_preset_max"),
                ("🛠️ Custom (пізніше)", "rep_preset_custom"),
            ]
        )

        await query.message.answer(
            templates.reports_preset_prompt(),
            reply_markup=kb,
        )
        await query.answer()

    @dp.callback_query(
        lambda c: c.data in ("rep_preset_min", "rep_preset_max", "rep_preset_custom")
    )
    async def cb_rep_preset(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        preset_map = {
            "rep_preset_min": "min",
            "rep_preset_max": "max",
            "rep_preset_custom": "custom",
        }
        preset = preset_map[str(query.data)]
        cfg = build_reports_preset(preset)
        ctx.reports_store.save(tg_id, cfg)

        prof = ctx.profile_store.load(tg_id) or {}
        onb = prof.get("onboarding")
        if not isinstance(onb, dict):
            onb = {}
        onb["reports_configured"] = True
        prof["onboarding"] = onb
        ctx.profile_store.save(tg_id, prof)

        ctx.sync_onboarding_progress(tg_id)

        if preset == "custom":
            cfg_base = build_reports_preset("max")
            cfg_custom = ReportsConfig(
                preset="custom",
                daily=dict(cfg_base.daily),
                weekly=dict(cfg_base.weekly),
                monthly=dict(cfg_base.monthly),
            )
            ctx.reports_store.save(tg_id, cfg_custom)
            ctx.sync_onboarding_progress(tg_id)

            kb0 = build_reports_custom_period_keyboard()
            await query.message.answer(templates.reports_custom_period_prompt(), reply_markup=kb0)
            await query.answer("Custom")
            return

        kb = build_vertical_options_keyboard(
            [
                ("🔊 Loud", "act_loud"),
                ("🔕 Quiet", "act_quiet"),
                ("🛠️ Custom", "act_custom"),
            ]
        )

        await query.message.answer(
            templates.activity_mode_prompt(),
            reply_markup=kb,
        )

        await query.answer()

    @dp.callback_query(
        lambda c: isinstance(c.data, str) and c.data.startswith("rep_custom_period:")
    )
    async def cb_rep_custom_period(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        period = str(query.data).split(":", 1)[1]
        cfg = ctx.reports_store.load(tg_id)

        enabled_map = {"daily": cfg.daily, "weekly": cfg.weekly, "monthly": cfg.monthly}.get(
            period, {}
        )
        kb = build_reports_custom_blocks_keyboard(period, enabled_map)

        if query.message:
            await query.message.answer(
                templates.reports_custom_blocks_prompt(period),
                reply_markup=kb,
            )
        await query.answer("OK")

    @dp.callback_query(
        lambda c: isinstance(c.data, str) and c.data.startswith("rep_custom_toggle:")
    )
    async def cb_rep_custom_toggle(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        _, period, key = str(query.data).split(":", 2)
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
        ctx.sync_onboarding_progress(tg_id)

        enabled_map = {"daily": daily, "weekly": weekly, "monthly": monthly}.get(period, {})
        kb = build_reports_custom_blocks_keyboard(period, enabled_map)

        if query.message:
            await query.message.answer(
                templates.reports_custom_blocks_prompt(period),
                reply_markup=kb,
            )
        await query.answer()

    @dp.callback_query(lambda c: c.data == "rep_custom_back")
    async def cb_rep_custom_back(query: CallbackQuery) -> None:
        kb = build_reports_custom_period_keyboard()
        if query.message:
            await query.message.answer(
                templates.reports_custom_period_prompt(),
                reply_markup=kb,
            )
        await query.answer("Back")

    @dp.callback_query(lambda c: c.data == "rep_custom_done")
    async def cb_rep_custom_done(query: CallbackQuery) -> None:
        kb = build_vertical_options_keyboard(
            [
                ("🔊 Loud", "act_loud"),
                ("🔕 Quiet", "act_quiet"),
                ("🛠️ Custom", "act_custom"),
            ]
        )
        if query.message:
            await query.message.answer(
                templates.activity_mode_prompt(),
                reply_markup=kb,
            )
        await query.answer()

    @dp.callback_query(lambda c: c.data in ("act_loud", "act_quiet", "act_custom"))
    async def cb_activity_mode(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        mode_map = {"act_loud": "loud", "act_quiet": "quiet", "act_custom": "custom"}
        mode = mode_map[str(query.data)]

        prof = ctx.profile_store.load(tg_id) or {}
        prof = apply_onboarding_settings(prof, activity_mode=mode)
        ctx.profile_store.save(tg_id, prof)
        ctx.sync_onboarding_progress(tg_id)

        if query.message:
            kb = build_vertical_options_keyboard(
                [
                    ("⚡ Одразу (кожне)", "uncat_immediate"),
                    ("🗓️ Раз на день", "uncat_daily"),
                    ("📅 Раз на тиждень", "uncat_weekly"),
                    ("🧾 Перед звітом", "uncat_before_report"),
                ]
            )

            await query.message.answer(
                templates.uncat_frequency_prompt(),
                reply_markup=kb,
            )

        await query.answer()

    @dp.callback_query(
        lambda c: (
            c.data in ("uncat_immediate", "uncat_daily", "uncat_weekly", "uncat_before_report")
        )
    )
    async def cb_uncat_frequency(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        freq_map = {
            "uncat_immediate": "immediate",
            "uncat_daily": "daily",
            "uncat_weekly": "weekly",
            "uncat_before_report": "before_report",
        }
        freq = freq_map[str(query.data)]

        prof = ctx.profile_store.load(tg_id) or {}
        prof = apply_onboarding_settings(prof, uncategorized_prompt_frequency=freq)
        ctx.profile_store.save(tg_id, prof)
        ctx.sync_onboarding_progress(tg_id)

        if query.message:
            kb = build_vertical_options_keyboard(
                [
                    ("🤝 Supportive", "persona_supportive"),
                    ("🧠 Rational", "persona_rational"),
                    ("🔥 Motivator", "persona_motivator"),
                ]
            )

            await query.message.answer(
                templates.persona_prompt(),
                reply_markup=kb,
            )

        await query.answer()

    @dp.callback_query(
        lambda c: c.data in ("persona_supportive", "persona_rational", "persona_motivator")
    )
    async def cb_persona(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        persona_map = {
            "persona_supportive": "supportive",
            "persona_rational": "rational",
            "persona_motivator": "motivator",
        }
        persona = persona_map[str(query.data)]

        prof = ctx.profile_store.load(tg_id) or {}
        prof = apply_onboarding_settings(prof, persona=persona)
        ctx.profile_store.save(tg_id, prof)
        ctx.sync_onboarding_progress(tg_id)

        if query.message:
            await query.message.answer(templates.onboarding_finished_message())
        await query.answer()
