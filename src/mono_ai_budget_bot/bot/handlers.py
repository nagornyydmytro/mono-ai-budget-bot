from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING

from aiogram import F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from mono_ai_budget_bot.currency import MonobankPublicClient
from mono_ai_budget_bot.monobank import MonobankClient
from mono_ai_budget_bot.nlq import memory_store
from mono_ai_budget_bot.nlq.pipeline import handle_nlq
from mono_ai_budget_bot.nlq.types import NLQRequest
from mono_ai_budget_bot.reports.config import ReportsConfig, build_reports_preset
from mono_ai_budget_bot.settings.onboarding import apply_onboarding_settings
from mono_ai_budget_bot.storage.wipe import wipe_user_financial_cache
from mono_ai_budget_bot.taxonomy.models import add_category
from mono_ai_budget_bot.taxonomy.presets import build_taxonomy_preset
from mono_ai_budget_bot.taxonomy.rules import Rule
from mono_ai_budget_bot.uncat.ui import list_leaf_options

from . import templates
from .app import (
    _compute_and_cache_reports_for_user,
    _currency_screen_keyboard,
    _map_llm_error,
    _map_monobank_error,
    _mask_secret,
    _render_currency_screen_text,
    _save_selected_accounts,
    build_ai_block,
    md_escape,
    render_accounts_screen,
)
from .clarify import validate_ok_or_alert, validate_uncat_pending_or_alert
from .formatting import format_money_grn
from .ui import (
    build_back_keyboard,
    build_bootstrap_picker_keyboard,
    build_categories_menu_keyboard,
    build_data_menu_keyboard,
    build_main_menu_keyboard,
    build_nlq_clarify_keyboard,
    build_onboarding_resume_keyboard,
    build_reports_custom_blocks_keyboard,
    build_reports_custom_period_keyboard,
    build_reports_menu_keyboard,
    build_start_menu_keyboard,
    build_uncat_leaf_picker_keyboard,
    build_vertical_options_keyboard,
)

if TYPE_CHECKING:
    from aiogram import Bot, Dispatcher
    from aiogram.types import Message

    from ..config import Settings
    from ..storage.profile_store import ProfileStore
    from ..storage.report_store import ReportStore
    from ..storage.reports_store import ReportsStore
    from ..storage.rules_store import RulesStore
    from ..storage.taxonomy_store import TaxonomyStore
    from ..storage.tx_store import TxStore
    from ..storage.uncat_store import UncatStore
    from ..storage.user_store import UserStore
    from ..uncat.pending import UncatPendingStore


def register_handlers(
    dp: "Dispatcher",
    *,
    bot: "Bot",
    settings: "Settings",
    users: "UserStore",
    store: "ReportStore",
    tx_store: "TxStore",
    profile_store: "ProfileStore",
    taxonomy_store: "TaxonomyStore",
    reports_store: "ReportsStore",
    uncat_store: "UncatStore",
    rules_store: "RulesStore",
    uncat_pending_store: "UncatPendingStore",
    user_locks: dict[int, asyncio.Lock],
    logger: logging.Logger,
    sync_user_ledger,
    render_report_for_user,
) -> None:
    def _sync_onboarding_progress(tg_id: int) -> dict[str, bool]:
        cfg = users.load(tg_id)
        prof = profile_store.load(tg_id) or {}

        token_done = bool(cfg is not None and cfg.mono_token)
        accounts_done = bool(cfg is not None and (cfg.selected_account_ids or []))
        taxonomy_done = taxonomy_store.load(tg_id) is not None
        reports_done = reports_store.load(tg_id) is not None
        activity_done = bool(prof.get("activity_mode"))
        uncat_done = bool(prof.get("uncategorized_prompt_frequency"))
        persona_done = bool(prof.get("persona"))

        completed = bool(
            token_done
            and accounts_done
            and taxonomy_done
            and reports_done
            and activity_done
            and uncat_done
            and persona_done
        )

        onb = prof.get("onboarding")
        if not isinstance(onb, dict):
            onb = {}

        onb.update(
            {
                "token": token_done,
                "accounts": accounts_done,
                "taxonomy": taxonomy_done,
                "reports": reports_done,
                "activity_mode": activity_done,
                "uncat_frequency": uncat_done,
                "persona": persona_done,
                "completed": completed,
            }
        )

        prof["onboarding"] = onb
        prof["onboarding_completed"] = completed
        profile_store.save(tg_id, prof)

        return {
            "token": token_done,
            "accounts": accounts_done,
            "taxonomy": taxonomy_done,
            "reports": reports_done,
            "activity_mode": activity_done,
            "uncat_frequency": uncat_done,
            "persona": persona_done,
            "completed": completed,
        }

    def _onboarding_done(tg_id: int) -> bool:
        _sync_onboarding_progress(tg_id)
        prof = profile_store.load(tg_id) or {}
        return bool(prof.get("onboarding_completed"))

    async def _prompt_finish_onboarding(message: Message, *, text: str | None = None) -> None:
        kb = build_onboarding_resume_keyboard()
        await message.answer(
            text or templates.onboarding_finish_prompt_message(),
            reply_markup=kb,
        )

    async def _send_onboarding_next(chat: Message | CallbackQuery) -> None:
        if isinstance(chat, CallbackQuery):
            tg_id = chat.from_user.id if chat.from_user else None
            msg = chat.message
        else:
            tg_id = chat.from_user.id if chat.from_user else None
            msg = chat

        if tg_id is None or msg is None:
            return

        cfg = users.load(tg_id)
        prof = profile_store.load(tg_id) or {}

        if cfg is None or not cfg.mono_token:
            kb = build_start_menu_keyboard()
            await msg.answer(templates.start_message(), reply_markup=kb)
            return

        if not cfg.selected_account_ids:
            mb = MonobankClient(token=cfg.mono_token)
            try:
                info = mb.client_info()
            finally:
                mb.close()

            accounts = [
                {"id": a.id, "currencyCode": a.currencyCode, "maskedPan": a.maskedPan}
                for a in info.accounts
            ]
            selected_ids = set(cfg.selected_account_ids or [])
            text, kb = render_accounts_screen(accounts, selected_ids)
            await msg.answer(f"{templates.connect_success_confirm()}\n\n{text}", reply_markup=kb)
            return

        if taxonomy_store.load(tg_id) is None:
            count = len(cfg.selected_account_ids)
            kb = build_bootstrap_picker_keyboard(include_skip=False)
            await msg.answer(
                templates.accounts_after_done_with_count(count),
                reply_markup=kb,
            )
            return

        if reports_store.load(tg_id) is None:
            l1, l2, l3 = templates.reports_preset_labels()
            kb = build_vertical_options_keyboard(
                [
                    (l1, "rep_preset_min"),
                    (l2, "rep_preset_max"),
                    (l3, "rep_preset_custom"),
                ]
            )
            await msg.answer(templates.reports_preset_prompt(), reply_markup=kb)
            return

        if not prof.get("activity_mode"):
            l1, l2, l3 = templates.activity_mode_labels()
            kb = build_vertical_options_keyboard(
                [
                    (l1, "act_loud"),
                    (l2, "act_quiet"),
                    (l3, "act_custom"),
                ]
            )
            await msg.answer(templates.activity_mode_prompt(), reply_markup=kb)
            return

        if not prof.get("uncategorized_prompt_frequency"):
            l1, l2, l3, l4 = templates.uncat_frequency_labels()
            kb = build_vertical_options_keyboard(
                [
                    (l1, "uncat_immediate"),
                    (l2, "uncat_daily"),
                    (l3, "uncat_weekly"),
                    (l4, "uncat_before_report"),
                ]
            )
            await msg.answer(templates.uncat_frequency_prompt(), reply_markup=kb)
            return

        if not prof.get("persona"):
            l1, l2, l3 = templates.persona_labels()
            kb = build_vertical_options_keyboard(
                [
                    (l1, "persona_supportive"),
                    (l2, "persona_rational"),
                    (l3, "persona_motivator"),
                ]
            )
            await msg.answer(templates.persona_prompt(), reply_markup=kb)
            return

        kb = build_main_menu_keyboard(uncat_enabled=True)
        await msg.answer(templates.menu_root_message(), reply_markup=kb)

    @dp.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        tg_id = message.from_user.id if message.from_user else None
        if tg_id is None:
            return

        users.save(tg_id, chat_id=message.chat.id)
        cfg = users.load(tg_id)

        kb = build_start_menu_keyboard()

        text = templates.start_message()
        if cfg is not None and cfg.mono_token:
            text = templates.start_message_connected()

        await message.answer(text, reply_markup=kb)

    @dp.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        tg_id = message.from_user.id if message.from_user else None
        if tg_id is None:
            return

        cfg = users.load(tg_id)
        if cfg is None or not cfg.mono_token or not cfg.selected_account_ids:
            kb = build_back_keyboard("onb_back_main")
            await message.answer(templates.help_message(), reply_markup=kb)
            return

        kb = build_main_menu_keyboard(uncat_enabled=True)
        await message.answer(templates.help_message(), reply_markup=kb)

    @dp.message(Command("menu"))
    async def cmd_menu(message: Message) -> None:
        tg_id = message.from_user.id if message.from_user else None
        if tg_id is None:
            return

        _sync_onboarding_progress(tg_id)
        onboarding_done = _onboarding_done(tg_id)

        if not onboarding_done:
            kb = build_main_menu_keyboard(uncat_enabled=True)
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
            mapped = _map_monobank_error(e)
            await message.answer(mapped or templates.error("Помилка перевірки токена."))
            return

        users.save(tg_id, mono_token=mono_token, selected_account_ids=[])
        _sync_onboarding_progress(tg_id)

        kb = build_main_menu_keyboard(uncat_enabled=True)
        await message.answer(templates.connect_success_confirm())
        await message.answer(templates.connect_success_next_steps(), reply_markup=kb)

    @dp.message(Command("status"))
    async def cmd_status(message: Message) -> None:
        tg_id = message.from_user.id if message.from_user else None
        cfg = users.load(tg_id) if tg_id is not None else None

        if cfg is None:
            await message.answer(templates.status_screen_not_connected())
            return

        masked = (
            md_escape(_mask_secret(cfg.mono_token)) if getattr(cfg, "mono_token", None) else "—"
        )
        selected_cnt = len(cfg.selected_account_ids or [])

        cache_lines: dict[str, str | None] = {}
        for p in ("today", "week", "month"):
            stored = store.load(cfg.telegram_user_id, p)
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

        cfg = users.load(tg_id)
        if cfg is None or not cfg.mono_token:
            await message.answer(templates.err_not_connected())
            return

        mb = MonobankClient(token=cfg.mono_token)
        try:
            info = mb.client_info()
        except Exception as e:
            msg = _map_monobank_error(e)
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

    @dp.callback_query(lambda c: c.data and c.data.startswith("acc_toggle:"))
    async def cb_toggle_account(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Помилка: нема user id", show_alert=True)
            return

        cfg = users.load(tg_id)
        if cfg is None:
            await query.answer("Спочатку /connect", show_alert=True)
            return

        acc_id = (query.data or "").split("acc_toggle:", 1)[1].strip()
        selected = set(cfg.selected_account_ids or [])

        if acc_id in selected:
            selected.remove(acc_id)
        else:
            selected.add(acc_id)

        _save_selected_accounts(users, tg_id, sorted(selected))
        _sync_onboarding_progress(tg_id)

        mb = MonobankClient(token=cfg.mono_token)
        try:
            info = mb.client_info()
        except Exception as e:
            msg = _map_monobank_error(e)
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

        cfg = users.load(tg_id)
        if cfg is None:
            await query.answer("Спочатку підключи /connect", show_alert=True)
            return

        selected_ids = set(cfg.selected_account_ids or [])
        if not selected_ids:
            await query.answer("Нічого очищати")
            return

        _save_selected_accounts(users, tg_id, [])
        _sync_onboarding_progress(tg_id)

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
        cfg = users.load(tg_id) if tg_id is not None else None

        count = len(cfg.selected_account_ids) if cfg else 0
        if count <= 0:
            await query.answer("Спочатку вибери хоча б 1 картку", show_alert=True)
            return

        _sync_onboarding_progress(tg_id)
        onboarding_done = _onboarding_done(tg_id)

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
                tx_store=tx_store,
                report_store=store,
                rules_store=rules_store,
                uncat_store=uncat_store,
                uncat_pending_store=uncat_pending_store,
            )

        if isinstance(mem, dict):
            mem.pop("accounts_picker", None)
            memory_store.save_memory(tg_id, mem)

        kb = build_bootstrap_picker_keyboard(include_skip=(onboarding_done and not changed))

        if query.message:
            await query.message.edit_text(
                templates.accounts_after_done_with_count(count),
                reply_markup=kb,
            )
        await query.answer()

    @dp.callback_query(lambda c: c.data == "menu_connect")
    async def cb_menu_connect(query: CallbackQuery) -> None:
        if query.message:
            kb = build_vertical_options_keyboard(
                [("✅ Ввести токен", "onb_token"), ("⬅️ Назад", "onb_back_main")]
            )
            await query.message.answer(templates.connect_instructions(), reply_markup=kb)
        await query.answer()

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data == "menu:root")
    async def cb_menu_root(query: CallbackQuery) -> None:
        if query.message:
            await query.message.edit_text(
                templates.menu_root_message(),
                reply_markup=build_main_menu_keyboard(uncat_enabled=True),
            )
        await query.answer()

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data == "menu:reports")
    async def cb_menu_reports(query: CallbackQuery) -> None:
        if query.message:
            await query.message.edit_text(
                templates.menu_reports_message(),
                reply_markup=build_reports_menu_keyboard(),
            )
        await query.answer()

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data == "menu:data")
    async def cb_menu_data(query: CallbackQuery) -> None:
        if query.message:
            await query.message.edit_text(
                templates.menu_data_message(),
                reply_markup=build_data_menu_keyboard(),
            )
        await query.answer()

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data == "menu:data:new_token")
    async def cb_data_new_token(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        memory_store.set_pending_manual_mode(
            tg_id,
            expected="mono_token",
            hint=templates.token_paste_hint_new_token(),
            source="data_menu",
            ttl_sec=900,
        )

        if query.message:
            await query.message.answer(
                templates.token_paste_prompt_new_token(),
                reply_markup=build_back_keyboard("menu:data"),
            )
        await query.answer()

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data == "menu:data:accounts")
    async def cb_data_accounts(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        cfg = users.load(tg_id)
        if cfg is None or not cfg.mono_token:
            await query.answer("Monobank не підключено", show_alert=True)
            return

        mb = MonobankClient(token=cfg.mono_token)
        try:
            info = mb.client_info()
        finally:
            mb.close()

        accounts = [
            {"id": a.id, "currencyCode": a.currencyCode, "maskedPan": a.maskedPan}
            for a in info.accounts
        ]
        selected_ids = set(cfg.selected_account_ids or [])
        mem = memory_store.load_memory(tg_id)
        mem["accounts_picker"] = {
            "source": "data_menu",
            "prev_selected": sorted(selected_ids),
        }
        memory_store.save_memory(tg_id, mem)
        text, kb = render_accounts_screen(accounts, selected_ids)

        if query.message:
            await query.message.edit_text(text, reply_markup=kb)
        await query.answer()

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data == "menu:data:refresh")
    async def cb_data_refresh(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        cfg = users.load(tg_id)
        if cfg is None or not cfg.mono_token or not cfg.selected_account_ids:
            await query.message.answer(templates.need_connect_and_accounts_message())
            return

        if query.message:
            await query.message.answer(templates.ledger_refresh_progress_message())

        asyncio.create_task(sync_user_ledger(tg_id, cfg, days_back=30))
        await query.answer()

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data == "menu:data:status")
    async def cb_data_status(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        cfg = users.load(tg_id)
        if cfg is None or not cfg.mono_token:
            await query.answer("Monobank не підключено", show_alert=True)
            return

        acc_n = len(cfg.selected_account_ids or [])
        _sync_onboarding_progress(tg_id)
        onboarding_done = _onboarding_done(tg_id)

        text = templates.status_message(accounts_selected=acc_n, onboarding_done=onboarding_done)

        if query.message:
            await query.message.answer(text)
        await query.answer()

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data == "menu:categories")
    async def cb_menu_categories(query: CallbackQuery) -> None:
        if query.message:
            await query.message.edit_text(
                templates.menu_categories_message(),
                reply_markup=build_categories_menu_keyboard(),
            )
        await query.answer()

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data.startswith("menu:categories:"))
    async def cb_menu_categories_placeholders(query: CallbackQuery) -> None:
        await query.answer(templates.coming_soon_message(), show_alert=True)

    @dp.callback_query(lambda c: c.data == "onb_token")
    async def cb_onb_token(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        memory_store.set_pending_manual_mode(
            tg_id,
            expected="mono_token",
            hint=templates.token_paste_hint_connect(),
            source="onboarding",
            ttl_sec=900,
        )

        if query.message:
            await query.message.answer(
                templates.onboarding_token_paste_prompt(),
                reply_markup=build_back_keyboard("onb_back_main"),
            )
        await query.answer("Ок")

    async def _send_next_uncat(message: Message, tg_id: int) -> None:
        tax = taxonomy_store.load(tg_id)

        if tax is None:
            tax = build_taxonomy_preset("min")

        items = uncat_store.load(tg_id)
        if not items:
            await message.answer(templates.uncat_empty_message())
            return

        item = items[0]
        pending = uncat_pending_store.create(
            tg_id, tx_id=item.tx_id, stage="pick_leaf", ttl_sec=900
        )

        leaves = list_leaf_options(tax, root_kind="expense")
        leaves = leaves[:8]

        kb = build_uncat_leaf_picker_keyboard(
            pending_id=pending.pending_id,
            leaves=[(opt.name, opt.leaf_id) for opt in leaves],
        )

        amount_uah = abs(int(item.amount)) / 100.0
        await message.answer(
            templates.uncat_purchase_prompt(item.description, format_money_grn(amount_uah)),
            reply_markup=kb,
        )

    @dp.callback_query(lambda c: c.data == "menu:uncat")
    async def cb_menu_uncat(query: CallbackQuery) -> None:
        await query.answer()

        if query.message:
            await query.message.answer(
                templates.uncat_menu_placeholder_message(),
                reply_markup=build_back_keyboard("menu:root"),
            )

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data.startswith("uncat_cancel:"))
    async def cb_uncat_cancel(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        parts = str(query.data).split(":")
        pid = parts[1] if len(parts) > 1 else ""

        cur = uncat_pending_store.load(tg_id)
        now_ts = int(time.time())
        if not await validate_uncat_pending_or_alert(query, cur, pid=pid, now_ts=now_ts):
            return

        uncat_pending_store.mark_used(tg_id)
        uncat_pending_store.clear(tg_id)

        if query.message:
            await query.message.answer("Ок, скасовано.")
        await query.answer("Скасовано")

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data.startswith("uncat_create:"))
    async def cb_uncat_create(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        parts = str(query.data).split(":")
        pid = parts[1] if len(parts) > 1 else ""

        cur = uncat_pending_store.load(tg_id)
        now_ts = int(time.time())
        if not await validate_uncat_pending_or_alert(
            query,
            cur,
            pid=pid,
            now_ts=now_ts,
            stage="pick_leaf",
        ):
            return

        uncat_pending_store.create(tg_id, tx_id=cur.tx_id, stage="create_name", ttl_sec=900)

        if query.message:
            await query.message.answer(templates.uncat_create_category_name_prompt())

        await query.answer("Ок")

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data.startswith("uncat_pick:"))
    async def cb_uncat_pick(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        parts = str(query.data).split(":")
        pid = parts[1] if len(parts) > 1 else ""
        leaf_id = parts[2] if len(parts) > 2 else ""

        cur = uncat_pending_store.load(tg_id)
        now_ts = int(time.time())
        if not await validate_uncat_pending_or_alert(
            query,
            cur,
            pid=pid,
            now_ts=now_ts,
            stage="pick_leaf",
        ):
            return

        tax = taxonomy_store.load(tg_id)
        if tax is None:
            tax = build_taxonomy_preset("min")

        nodes = tax.get("nodes")
        leaf_name = ""
        if isinstance(nodes, dict):
            n = nodes.get(leaf_id)
            if isinstance(n, dict):
                leaf_name = str(n.get("name") or "")

        items = uncat_store.load(tg_id)
        item = next((x for x in items if x.tx_id == cur.tx_id), None)
        if item is None:
            uncat_pending_store.clear(tg_id)
            await query.answer("Немає цієї покупки в черзі.", show_alert=True)
            return

        base = f"{leaf_id}:{item.description.lower().strip()}"
        rid = hashlib.sha1(base.encode("utf-8")).hexdigest()[:10]
        rules_store.add(tg_id, Rule(id=rid, leaf_id=leaf_id, merchant_contains=item.description))

        remaining = [x for x in items if x.tx_id != item.tx_id]
        uncat_store.save(tg_id, remaining)

        uncat_pending_store.mark_used(tg_id)
        uncat_pending_store.clear(tg_id)

        if query.message:
            await query.message.answer(
                templates.uncat_saved_mapping_message(
                    description=item.description,
                    leaf_name=(leaf_name or "категорія"),
                )
            )
            await _send_next_uncat(query.message, tg_id)

        await query.answer()

    @dp.callback_query(lambda c: c.data == "onb_back_main")
    async def cb_onb_back_main(query: CallbackQuery) -> None:
        if query.message:
            memory_store.pop_pending_manual_mode(query.from_user.id)
            kb = build_start_menu_keyboard()
            await query.message.answer(templates.start_message(), reply_markup=kb)
        await query.answer()

    @dp.callback_query(lambda c: c.data == "onb_resume")
    async def cb_onb_resume(query: CallbackQuery) -> None:
        await query.answer()
        await _send_onboarding_next(query)

    async def _send_currency_screen(message: Message, *, force_refresh: bool) -> None:
        try:
            pub = MonobankPublicClient()
            rates = pub.currency(force_refresh=force_refresh)
            text = _render_currency_screen_text(rates)
        except Exception as e:
            text = templates.error(f"Не вдалося отримати курси валют: {e}")
        finally:
            try:
                if pub is not None:
                    pub.close()
            except Exception:
                pass

        kb = _currency_screen_keyboard()
        await message.answer(text, reply_markup=kb)

    @dp.callback_query(lambda c: c.data == "menu:currency")
    async def cb_menu_currency(query: CallbackQuery) -> None:
        if query.message:
            await _send_currency_screen(query.message, force_refresh=False)
        await query.answer()

    @dp.callback_query(lambda c: c.data == "currency_refresh")
    async def cb_currency_refresh(query: CallbackQuery) -> None:
        if query.message:
            await _send_currency_screen(query.message, force_refresh=True)
        await query.answer("Оновлено")

    @dp.callback_query(lambda c: c.data == "currency_back")
    async def cb_currency_back(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer()
            return

        cfg = users.load(tg_id)
        prof = profile_store.load(tg_id) or {}
        onboarding_done = (
            cfg is not None
            and bool(cfg.mono_token)
            and bool(cfg.selected_account_ids)
            and bool(prof.get("persona"))
        )

        if query.message:
            if not onboarding_done:
                kb = build_start_menu_keyboard()
                await query.message.answer(templates.start_message(), reply_markup=kb)
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
            _sync_onboarding_progress(tg_id)
            onboarding_done = _onboarding_done(tg_id)

            if query.message:
                if not onboarding_done:
                    kb = build_back_keyboard("onb_back_main")
                    await query.message.answer(templates.help_message(), reply_markup=kb)
                else:
                    kb = build_main_menu_keyboard(uncat_enabled=True)
                    await query.message.answer(templates.help_message(), reply_markup=kb)

        await query.answer()

    @dp.callback_query(lambda c: c.data == "menu_week")
    async def cb_menu_week(query: CallbackQuery) -> None:
        if query.message and query.from_user:
            await _send_period_report(query.message, "week", tg_id_override=query.from_user.id)
        await query.answer()

    @dp.callback_query(lambda c: c.data == "menu_month")
    async def cb_menu_month(query: CallbackQuery) -> None:
        if query.message and query.from_user:
            await _send_period_report(query.message, "month", tg_id_override=query.from_user.id)
        await query.answer()

    @dp.callback_query(lambda c: c.data == "menu_status")
    async def cb_menu_status(query: CallbackQuery) -> None:
        if query.message:
            await cmd_status(query.message)
        await query.answer()

    @dp.callback_query(lambda c: c.data == "menu_accounts")
    async def cb_menu_accounts(query: CallbackQuery) -> None:
        if query.message:
            await cmd_accounts(query.message)
        await query.answer()

    @dp.callback_query(lambda c: c.data == "menu_refresh_week")
    async def cb_menu_refresh_week(query: CallbackQuery) -> None:
        if query.message:
            fake_msg = query.message
            fake_msg.text = "/refresh week"
            await cmd_refresh(fake_msg)
        await query.answer()

    @dp.callback_query(lambda c: bool(c.data) and c.data.startswith("nlq_pick:"))
    async def cb_nlq_pick(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає user id", show_alert=True)
            return

        raw = (query.data or "").strip()
        parts = raw.split(":")
        if len(parts) != 3 or parts[0] != "nlq_pick":
            await query.answer("Некоректний вибір", show_alert=True)
            return

        pid = parts[1].strip()
        idx_raw = parts[2].strip()
        if not idx_raw.isdigit():
            await query.answer("Некоректний вибір", show_alert=True)
            return

        now_ts = int(time.time())
        ok = memory_store.validate_and_consume_pending(tg_id, pending_id=pid, now_ts=now_ts)
        if not await validate_ok_or_alert(query, ok):
            return

        try:
            resp = handle_nlq(
                NLQRequest(
                    telegram_user_id=tg_id,
                    text=str(int(idx_raw)),
                    now_ts=now_ts,
                )
            )
        except Exception:
            await query.answer("Помилка", show_alert=True)
            return

        if query.message and resp.result:
            await query.message.answer(resp.result.text)
            await query.answer("Ок")
            return

        await query.answer("Ок")

    @dp.callback_query(lambda c: bool(c.data) and c.data.startswith("nlq_other:"))
    async def cb_nlq_other(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає user id", show_alert=True)
            return

        raw = (query.data or "").strip()
        parts = raw.split(":", 1)
        if len(parts) != 2 or parts[0] != "nlq_other":
            await query.answer("Некоректно", show_alert=True)
            return

        pid = parts[1].strip()
        now_ts = int(time.time())
        ok = memory_store.validate_and_consume_pending(tg_id, pending_id=pid, now_ts=now_ts)
        if not await validate_ok_or_alert(query, ok):
            return

        mem = memory_store.load_memory(tg_id)
        kind = mem.get("pending_kind") if isinstance(mem.get("pending_kind"), str) else None

        if kind == "recipient":
            expected = "recipient"
            hint = templates.manual_mode_hint_recipient()
        elif kind == "category_alias":
            expected = "merchant_or_recipient"
            hint = templates.manual_mode_hint_category_alias()
        else:
            expected = "merchant_or_recipient"
            hint = templates.manual_mode_hint_default()

        memory_store.set_pending_manual_mode(
            tg_id,
            expected=expected,
            hint=hint,
            source="nlq_other",
            ttl_sec=600,
        )

        if query.message:
            await query.message.answer(templates.nlq_manual_entry_prompt(hint))
        await query.answer("Ок")

    @dp.callback_query(lambda c: bool(c.data) and c.data.startswith("nlq_cancel:"))
    async def cb_nlq_cancel(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає user id", show_alert=True)
            return

        raw = (query.data or "").strip()
        parts = raw.split(":", 1)
        if len(parts) != 2 or parts[0] != "nlq_cancel":
            await query.answer("Некоректно", show_alert=True)
            return

        pid = parts[1].strip()
        now_ts = int(time.time())
        ok = memory_store.validate_and_consume_pending(tg_id, pending_id=pid, now_ts=now_ts)
        if not await validate_ok_or_alert(query, ok):
            return

        memory_store.pop_pending_action(tg_id)
        if query.message:
            await query.message.answer("Ок, скасовано.")
        await query.answer("Скасовано")

    @dp.callback_query(
        lambda c: c.data in ("boot_30", "boot_90", "boot_180", "boot_365", "boot_skip")
    )
    async def cb_bootstrap(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        cfg = users.load(tg_id)
        if cfg is None or not cfg.mono_token:
            await query.answer("Спочатку /connect", show_alert=True)
            return

        account_ids = list(cfg.selected_account_ids or [])
        if not account_ids:
            await query.answer("Спочатку вибери картки: /accounts", show_alert=True)
            return

        if query.data == "boot_skip":
            _sync_onboarding_progress(tg_id)
            onboarding_done = _onboarding_done(tg_id)
            if not onboarding_done:
                await query.answer("На онбордингу пропуск недоступний.", show_alert=True)
                return

            if query.message:
                await query.message.edit_text("Ок.")

            await query.answer("Пропущено")
            return

        days_map = {"boot_30": 30, "boot_90": 90, "boot_180": 180, "boot_365": 365}
        days = int(days_map[str(query.data)])

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
                async with user_locks[tg_id]:
                    from ..monobank.sync import sync_accounts_ledger

                    def _run_sync() -> object:
                        mb = MonobankClient(token=token)
                        try:
                            return sync_accounts_ledger(
                                mb=mb,
                                tx_store=tx_store,
                                telegram_user_id=tg_id,
                                account_ids=account_ids,
                                days_back=days,
                            )
                        finally:
                            mb.close()

                    res = await asyncio.to_thread(_run_sync)

                    await _compute_and_cache_reports_for_user(tg_id, account_ids, profile_store)

                    if chat_id is not None:
                        _sync_onboarding_progress(tg_id)
                        onboarding_done = _onboarding_done(tg_id)

                        if onboarding_done:
                            text = templates.bootstrap_done_message(
                                accounts=res.accounts,
                                fetched_requests=res.fetched_requests,
                                appended=res.appended,
                            )
                        else:
                            text = templates.bootstrap_done_onboarding_message()

                        await bot.send_message(chat_id, text)

            except Exception as e:
                if chat_id is not None:
                    msg = _map_monobank_error(e)
                    await bot.send_message(
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
        taxonomy_store.save(tg_id, tax)
        _sync_onboarding_progress(tg_id)

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
        reports_store.save(tg_id, cfg)
        _sync_onboarding_progress(tg_id)

        if preset == "custom":
            cfg_base = build_reports_preset("max")
            cfg_custom = ReportsConfig(
                preset="custom",
                daily=dict(cfg_base.daily),
                weekly=dict(cfg_base.weekly),
                monthly=dict(cfg_base.monthly),
            )
            reports_store.save(tg_id, cfg_custom)
            _sync_onboarding_progress(tg_id)

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
        cfg = reports_store.load(tg_id)

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
        cfg = reports_store.load(tg_id)

        daily = dict(cfg.daily)
        weekly = dict(cfg.weekly)
        monthly = dict(cfg.monthly)

        target = {"daily": daily, "weekly": weekly, "monthly": monthly}.get(period)
        if target is None or key not in target:
            await query.answer("Невідомий блок", show_alert=True)
            return

        target[key] = not bool(target[key])

        cfg2 = ReportsConfig(preset="custom", daily=daily, weekly=weekly, monthly=monthly)
        reports_store.save(tg_id, cfg2)
        _sync_onboarding_progress(tg_id)

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

        prof = profile_store.load(tg_id) or {}
        prof = apply_onboarding_settings(prof, activity_mode=mode)
        profile_store.save(tg_id, prof)
        _sync_onboarding_progress(tg_id)

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

        prof = profile_store.load(tg_id) or {}
        prof = apply_onboarding_settings(prof, uncategorized_prompt_frequency=freq)
        profile_store.save(tg_id, prof)
        _sync_onboarding_progress(tg_id)

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

        prof = profile_store.load(tg_id) or {}
        prof = apply_onboarding_settings(prof, persona=persona)
        profile_store.save(tg_id, prof)
        _sync_onboarding_progress(tg_id)

        if query.message:
            await query.message.answer(templates.onboarding_finished_message())
        await query.answer()

    @dp.message(Command("refresh"))
    async def cmd_refresh(message: Message) -> None:
        tg_id = message.from_user.id if message.from_user else None
        if tg_id is None:
            await message.answer(templates.error("Не зміг визначити твій Telegram user id."))
            return

        cfg = users.load(tg_id)
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
                async with user_locks[tg_id]:
                    from ..monobank.sync import sync_accounts_ledger

                    def _run_sync() -> object:
                        mb = MonobankClient(token=token)
                        try:
                            return sync_accounts_ledger(
                                mb=mb,
                                tx_store=tx_store,
                                telegram_user_id=tg_id,
                                account_ids=account_ids,
                                days_back=days_back,
                            )
                        finally:
                            mb.close()

                    res = await asyncio.to_thread(_run_sync)

                    await _compute_and_cache_reports_for_user(tg_id, account_ids, profile_store)

                    await bot.send_message(
                        chat_id,
                        templates.refresh_done_message(
                            accounts=res.accounts,
                            fetched_requests=res.fetched_requests,
                            appended=res.appended,
                        ),
                    )
            except Exception as e:
                msg = _map_monobank_error(e)
                await bot.send_message(
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

    async def _send_period_report(
        message: Message,
        period: str,
        *,
        tg_id_override: int | None = None,
    ) -> None:
        want_ai = " ai" in (" " + (message.text or "").lower() + " ")

        tg_id = (
            tg_id_override
            if tg_id_override is not None
            else (message.from_user.id if message.from_user else None)
        )
        if tg_id is None:
            await message.answer(templates.error("Не зміг визначити твій Telegram user id."))
            return

        cfg = users.load(tg_id)
        if cfg is None or not cfg.mono_token:
            await message.answer(templates.err_not_connected())
            return
        if not cfg.selected_account_ids:
            await message.answer(templates.err_no_accounts_selected())
            return
        _sync_onboarding_progress(tg_id)
        if not _onboarding_done(tg_id):
            await _prompt_finish_onboarding(message)
            return

        stored = store.load(tg_id, period)
        if stored is None:
            await message.answer(templates.err_no_ledger(period))
            return

        ai_block = None
        if want_ai:
            if not settings.openai_api_key:
                await message.answer(
                    await message.answer(templates.ai_disabled_missing_key_message())
                )
            else:
                period_label = {
                    "today": "Сьогодні",
                    "week": "Останні 7 днів",
                    "month": "Останні 30 днів",
                }.get(period, period)

                await message.answer(templates.ai_insights_progress_message())

                try:
                    from ..llm.openai_client import OpenAIClient

                    client = OpenAIClient(
                        api_key=settings.openai_api_key, model=settings.openai_model
                    )
                    try:
                        profile = profile_store.load(tg_id) or {}
                        facts_with_profile = {"period_facts": stored.facts, "user_profile": profile}
                        res = client.generate_report(facts_with_profile, period_label=period_label)
                    finally:
                        client.close()

                    ai_block = build_ai_block(
                        res.report.summary,
                        res.report.changes,
                        res.report.recs,
                        res.report.next_step,
                    )
                except Exception as e:
                    logger.warning("LLM unavailable, sending facts-only. err=%s", e)
                    await message.answer(_map_llm_error(e))
                    ai_block = None

        text = render_report_for_user(tg_id, period, stored.facts, ai_block=ai_block)
        await message.answer(text)

    @dp.message(Command("today"))
    async def cmd_today(message: Message) -> None:
        await _send_period_report(message, "today")

    @dp.message(Command("week"))
    async def cmd_week(message: Message) -> None:
        await _send_period_report(message, "week")

    @dp.message(Command("month"))
    async def cmd_month(message: Message) -> None:
        await _send_period_report(message, "month")

    @dp.message(Command("autojobs"))
    async def cmd_autojobs(message: Message) -> None:
        tg_id = message.from_user.id
        cfg = users.load(tg_id)
        if cfg is None:
            await message.answer(templates.need_connect_with_hint_message())
            return

        parts = (message.text or "").split()
        action = parts[1].lower() if len(parts) > 1 else "status"

        if action == "on":
            users.save(tg_id, autojobs_enabled=True)
            await message.answer(templates.success("Автозвіти увімкнено"))
            return
        if action == "off":
            users.save(tg_id, autojobs_enabled=False)
            await message.answer(templates.success("Автозвіти вимкнено"))
            return

        cfg2 = users.load(tg_id)
        await message.answer(
            templates.autojobs_status_line(enabled=bool(cfg2 and cfg2.autojobs_enabled))
        )

    @dp.message(F.text & ~F.text.startswith("/"))
    async def handle_plain_text(message: Message) -> None:
        user_id = message.from_user.id
        now_ts = int(time.time())
        text_raw = (message.text or "").strip()
        text_lower = text_raw.lower()
        uncat_pending = uncat_pending_store.load(user_id)
        if uncat_pending is not None and uncat_pending.stage == "create_name":
            if uncat_pending.used or uncat_pending.is_expired(now_ts):
                uncat_pending_store.clear(user_id)
            else:
                if text_lower == "cancel":
                    uncat_pending_store.clear(user_id)
                    await message.answer("Ок, скасовано.")
                    return

                tax = taxonomy_store.load(user_id)
                if tax is None:
                    tax = build_taxonomy_preset("min")

                try:
                    leaf_id = add_category(tax, root_kind="expense", name=text_raw)
                except Exception:
                    await message.answer(templates.taxonomy_invalid_category_name_message())
                    return

                taxonomy_store.save(user_id, tax)

                items = uncat_store.load(user_id)
                item = next((x for x in items if x.tx_id == uncat_pending.tx_id), None)
                if item is None:
                    uncat_pending_store.clear(user_id)
                    await message.answer("Немає цієї покупки в черзі.")
                    return

                base = f"{leaf_id}:{item.description.lower().strip()}"
                rid = hashlib.sha1(base.encode("utf-8")).hexdigest()[:10]
                rules_store.add(
                    user_id, Rule(id=rid, leaf_id=leaf_id, merchant_contains=item.description)
                )

                remaining = [x for x in items if x.tx_id != item.tx_id]
                uncat_store.save(user_id, remaining)
                uncat_pending_store.mark_used(user_id)
                uncat_pending_store.clear(user_id)

                await message.answer(
                    templates.uncat_category_created_and_applied_message(
                        category_name=text_raw,
                        description=item.description,
                    )
                )
                await _send_next_uncat(message, user_id)
                return

        manual = memory_store.get_pending_manual_mode(user_id, now_ts=now_ts)
        if manual is not None and str(manual.get("expected") or "") == "mono_token":
            if text_lower == "cancel":
                memory_store.pop_pending_manual_mode(user_id)
                await message.answer("Ок, скасовано.")
                return

            mono_token = text_raw
            if len(mono_token) < 20:
                await message.answer(templates.connect_validation_error())
                return

            await message.answer(templates.connect_token_validation_progress())

            try:
                mb = MonobankClient(token=mono_token)
                try:
                    info = mb.client_info()
                finally:
                    mb.close()
            except Exception as e:
                mapped = _map_monobank_error(e)
                await message.answer(mapped or templates.error("Помилка перевірки токена."))
                return

            users.save(user_id, mono_token=mono_token, selected_account_ids=[])
            _sync_onboarding_progress(user_id)
            memory_store.pop_pending_manual_mode(user_id)

            accounts = [
                {"id": a.id, "currencyCode": a.currencyCode, "maskedPan": a.maskedPan}
                for a in info.accounts
            ]
            selected_ids: set[str] = set()
            text, kb = render_accounts_screen(accounts, selected_ids)

            await message.answer(
                f"{templates.connect_success_confirm()}\n\n{text}", reply_markup=kb
            )
            return

        if text_lower == "cancel":
            memory_store.pop_pending_intent(user_id)
            await message.answer(templates.recipient_followup_cancelled())
            return

        cfg = users.load(user_id)
        if cfg is None or not cfg.mono_token:
            await message.answer(templates.err_not_connected())
            return
        if not cfg.selected_account_ids:
            await message.answer(templates.err_no_accounts_selected())
            return
        _sync_onboarding_progress(user_id)
        if not _onboarding_done(user_id):
            await _prompt_finish_onboarding(message)
            return

        stored = store.load(user_id, "week")
        if stored is None:
            await message.answer(templates.err_no_ledger("week"))
            return

        try:
            resp = handle_nlq(
                NLQRequest(
                    telegram_user_id=user_id,
                    text=message.text,
                    now_ts=int(time.time()),
                )
            )

            if resp.result:
                mem = memory_store.load_memory(user_id)
                kind = mem.get("pending_kind")
                opts = mem.get("pending_options")

                if (
                    kind in {"recipient", "category_alias", "paging"}
                    and isinstance(opts, list)
                    and opts
                ):
                    kb = build_nlq_clarify_keyboard(
                        opts,
                        pending_id=(
                            mem.get("pending_id")
                            if isinstance(mem.get("pending_id"), str)
                            else None
                        ),
                        limit=8,
                        include_other=(kind != "paging"),
                        include_cancel=True,
                    )
                    await message.answer(resp.result.text, reply_markup=kb)
                    return

                await message.answer(resp.result.text)
                return

            await message.answer(templates.unknown_nlq_message())
        except Exception:
            await message.answer(templates.nlq_failed_message())
