from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from aiogram import Bot, Dispatcher
from aiogram.types import CallbackQuery, Message

from mono_ai_budget_bot.currency import MonobankPublicClient
from mono_ai_budget_bot.monobank import MonobankClient
from mono_ai_budget_bot.nlq.pipeline import handle_nlq
from mono_ai_budget_bot.taxonomy.presets import build_taxonomy_preset
from mono_ai_budget_bot.uncat.ui import list_leaf_options

from . import templates
from .accounts_ui import render_accounts_screen
from .errors import map_llm_error
from .formatting import format_money_grn
from .handlers_common import HandlerContext
from .handlers_dev import register_dev_handlers
from .handlers_menu import register_menu_handlers
from .handlers_onboarding import register_onboarding_handlers
from .handlers_reports import register_report_handlers
from .handlers_start import register_start_handlers
from .handlers_text import register_text_handlers
from .handlers_uncat import register_uncat_handlers
from .menu_flow import gate_menu_dependencies, gate_menu_query_or_resume, gate_refresh_dependencies
from .onboarding_flow import send_onboarding_next
from .renderers import render_currency_screen_text
from .report_flow_helpers import build_ai_block
from .ui import (
    build_bootstrap_picker_keyboard,
    build_currency_screen_keyboard,
    build_main_menu_keyboard,
    build_onboarding_resume_keyboard,
    build_start_menu_keyboard,
    build_uncat_empty_keyboard,
    build_uncat_review_keyboard,
    build_vertical_options_keyboard,
)

if TYPE_CHECKING:
    from ..config import Settings
    from ..storage.profile_store import ProfileStore
    from ..storage.report_store import ReportStore
    from ..storage.reports_store import ReportsStore
    from ..storage.rules_store import RulesStore
    from ..storage.taxonomy_store import TaxonomyStore
    from ..storage.tx_store import TxStore
    from ..storage.uncat_store import UncatStore
    from ..storage.user_store import UserConfig, UserStore
    from ..uncat.pending import UncatPendingStore


def register_handlers(
    dp: Dispatcher,
    *,
    bot: Bot,
    settings: Settings,
    users: UserStore,
    store: ReportStore,
    tx_store: TxStore,
    profile_store: ProfileStore,
    taxonomy_store: TaxonomyStore,
    reports_store: ReportsStore,
    uncat_store: UncatStore,
    rules_store: RulesStore,
    uncat_pending_store: UncatPendingStore,
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

    async def _gate_menu_query_or_resume(query: CallbackQuery) -> bool:
        return await gate_menu_query_or_resume(
            query,
            sync_onboarding_progress=_sync_onboarding_progress,
            onboarding_done=_onboarding_done,
            finish_onboarding_text=templates.menu_finish_onboarding_message(),
            finish_onboarding_keyboard=build_onboarding_resume_keyboard(),
        )

    async def _gate_menu_dependencies(
        query: CallbackQuery,
        *,
        require_token: bool = False,
        require_accounts: bool = False,
        require_ledger: bool = False,
    ) -> bool:
        return await gate_menu_dependencies(
            query,
            users=users,
            tx_store=tx_store,
            sync_onboarding_progress=_sync_onboarding_progress,
            onboarding_done=_onboarding_done,
            require_token=require_token,
            require_accounts=require_accounts,
            require_ledger=require_ledger,
            missing_token_text=templates.menu_missing_token_message(),
            missing_token_keyboard=build_vertical_options_keyboard(
                [("🔐 Connect", "menu_connect"), ("⬅️ Назад", "menu:root")]
            ),
            missing_accounts_text=templates.menu_missing_accounts_message(),
            missing_accounts_keyboard=build_vertical_options_keyboard(
                [("⚙️ Мої дані", "menu:mydata"), ("⬅️ Назад", "menu:root")]
            ),
            missing_ledger_text=templates.menu_missing_ledger_message(),
            missing_ledger_keyboard=build_vertical_options_keyboard(
                [("🔄 Refresh latest", "menu:data:refresh"), ("⬅️ Назад", "menu:root")]
            ),
            finish_onboarding_text=templates.menu_finish_onboarding_message(),
            finish_onboarding_keyboard=build_onboarding_resume_keyboard(),
        )

    async def _gate_refresh_dependencies(query: CallbackQuery) -> tuple[bool, UserConfig | None]:
        ok, cfg = await gate_refresh_dependencies(
            query,
            users=users,
            missing_token_text=templates.menu_missing_token_message(),
            missing_token_keyboard=build_vertical_options_keyboard(
                [("🔐 Connect", "menu_connect"), ("⬅️ Назад", "menu:root")]
            ),
            missing_accounts_text=templates.menu_missing_accounts_message(),
            missing_accounts_keyboard=build_vertical_options_keyboard(
                [("⚙️ Мої дані", "menu:mydata"), ("⬅️ Назад", "menu:root")]
            ),
        )
        return ok, cfg

    def _monobank_client_factory(*, token: str):
        return MonobankClient(token=token)

    def _handle_nlq_fn(req):
        return handle_nlq(req)

    async def _send_onboarding_next(chat: Message | CallbackQuery) -> None:
        await send_onboarding_next(
            chat,
            users=users,
            profile_store=profile_store,
            taxonomy_store=taxonomy_store,
            reports_store=reports_store,
            monobank_client_cls=_monobank_client_factory,
            render_accounts_screen=render_accounts_screen,
            start_message_text=templates.start_message(),
            connect_success_confirm_text=templates.connect_success_confirm(),
            accounts_after_done_with_count_text=templates.accounts_after_done_with_count,
            taxonomy_preset_prompt_text=templates.taxonomy_preset_prompt(),
            reports_preset_labels=templates.reports_preset_labels,
            reports_preset_prompt_text=templates.reports_preset_prompt(),
            activity_mode_labels=templates.activity_mode_labels,
            activity_mode_prompt_text=templates.activity_mode_prompt(),
            uncat_frequency_labels=templates.uncat_frequency_labels,
            uncat_frequency_prompt_text=templates.uncat_frequency_prompt(),
            persona_labels=templates.persona_labels,
            persona_prompt_text=templates.persona_prompt(),
            menu_root_message_text=templates.menu_root_message(),
            build_start_menu_keyboard=build_start_menu_keyboard,
            build_bootstrap_picker_keyboard=build_bootstrap_picker_keyboard,
            build_vertical_options_keyboard=build_vertical_options_keyboard,
            build_main_menu_keyboard=build_main_menu_keyboard,
        )

    async def _send_next_uncat(message: Message, tg_id: int) -> None:
        tax = taxonomy_store.load(tg_id)

        if tax is None:
            tax = build_taxonomy_preset("min")

        items = uncat_store.load(tg_id)
        if not items:
            await message.answer(
                templates.uncat_empty_message(),
                reply_markup=build_uncat_empty_keyboard(),
            )
            return

        item = items[0]
        pending = uncat_pending_store.create(tg_id, tx_id=item.tx_id, stage="review", ttl_sec=900)

        leaves = list_leaf_options(tax, root_kind="expense")
        leaves = leaves[:8]

        suggested = None
        if len(leaves) == 1:
            opt = leaves[0]
            suggested = (opt.name, opt.leaf_id)

        kb = build_uncat_review_keyboard(
            pending_id=pending.pending_id,
            suggested_leaf=suggested,
        )

        amount_uah = abs(int(item.amount)) / 100.0
        await message.answer(
            templates.uncat_purchase_prompt(item.description, format_money_grn(amount_uah)),
            reply_markup=kb,
        )

    async def _send_currency_screen(message: Message, *, force_refresh: bool) -> None:
        pub = None
        try:
            pub = MonobankPublicClient()
            rates = pub.currency(force_refresh=force_refresh)
            text = render_currency_screen_text(rates)
        except Exception as e:
            text = templates.error(f"Не вдалося отримати курси валют: {e}")
        finally:
            try:
                if pub is not None:
                    pub.close()
            except Exception:
                pass

        kb = build_currency_screen_keyboard()
        await message.edit_text(text, reply_markup=kb)

    async def _send_period_report(
        message: Message,
        period: str,
        *,
        tg_id_override: int | None = None,
        want_ai_override: bool | None = None,
    ) -> None:
        from mono_ai_budget_bot.analytics.coverage import CoverageStatus, classify_coverage
        from mono_ai_budget_bot.nlq import memory_store

        want_ai = (
            bool(want_ai_override)
            if want_ai_override is not None
            else (" ai" in (" " + (message.text or "").lower() + " "))
        )

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
            from .app import refresh_period_for_user

            await refresh_period_for_user(period, cfg, store)
            stored = store.load(tg_id, period)

        if stored is None:
            await message.answer(templates.err_no_ledger(period))
            return

        coverage_status = CoverageStatus.missing
        facts_cov = stored.facts.get("coverage") if isinstance(stored.facts, dict) else None
        if isinstance(facts_cov, dict):
            try:
                cov_from = int(facts_cov["coverage_from_ts"])
                cov_to = int(facts_cov["coverage_to_ts"])
                req_from = int(facts_cov["requested_from_ts"])
                req_to = int(facts_cov["requested_to_ts"])
                coverage_status = classify_coverage(
                    requested_from_ts=req_from,
                    requested_to_ts=req_to,
                    coverage_window=(cov_from, cov_to),
                )
            except Exception:
                coverage_status = CoverageStatus.missing

        if coverage_status == CoverageStatus.missing:
            days_back = {"today": 1, "week": 7, "month": 30}.get(period)
            if isinstance(days_back, int):
                memory_store.set_pending_intent(
                    tg_id,
                    payload={
                        "action": "coverage_sync",
                        "days_back": int(days_back),
                    },
                    kind="coverage_cta",
                    options=None,
                )
                mem = memory_store.load_memory(tg_id)
                pid = mem.get("pending_id") if isinstance(mem.get("pending_id"), str) else None
                from .ui import build_coverage_cta_keyboard

                kb = build_coverage_cta_keyboard(pending_id=(pid or ""))
                if kb is not None:
                    await message.answer(
                        templates.warning("Немає даних для запитаного періоду."),
                        reply_markup=kb,
                    )
                    return

        ai_block = None
        if want_ai:
            if not settings.openai_api_key:
                await message.answer(templates.ai_disabled_missing_key_message())
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
                        system = (
                            "Ти допомагаєш з персональною фінансовою аналітикою. "
                            "Працюй лише на основі переданих фактів. "
                            "Не вигадуй дані. "
                            "Не давай інвестиційних, медичних або юридичних порад. "
                            "Поверни JSON з полями: summary, changes, recs, next_step."
                        )
                        user = (
                            f"Період: {period_label}\n"
                            f"Факти: {stored.facts}\n"
                            f"Профіль: {profile}"
                        )
                        res = client.generate_report_v2(system, user)
                    finally:
                        client.close()

                    ai_block = build_ai_block(
                        res.summary,
                        res.changes,
                        res.recs,
                        res.next_step,
                    )
                except Exception as e:
                    logger.warning("LLM unavailable, sending facts-only. err=%s", e)
                    await message.answer(map_llm_error(e))
                    ai_block = None

        text = render_report_for_user(tg_id, period, stored.facts, ai_block=ai_block)
        await message.answer(text)

    ctx = HandlerContext(
        bot=bot,
        settings=settings,
        users=users,
        store=store,
        tx_store=tx_store,
        profile_store=profile_store,
        taxonomy_store=taxonomy_store,
        reports_store=reports_store,
        uncat_store=uncat_store,
        rules_store=rules_store,
        uncat_pending_store=uncat_pending_store,
        user_locks=user_locks,
        logger=logger,
        sync_user_ledger=sync_user_ledger,
        render_report_for_user=render_report_for_user,
        sync_onboarding_progress=_sync_onboarding_progress,
        onboarding_done=_onboarding_done,
        prompt_finish_onboarding=_prompt_finish_onboarding,
        gate_menu_query_or_resume=_gate_menu_query_or_resume,
        gate_menu_dependencies=_gate_menu_dependencies,
        gate_refresh_dependencies=_gate_refresh_dependencies,
        send_onboarding_next=_send_onboarding_next,
        send_next_uncat=_send_next_uncat,
        send_currency_screen=_send_currency_screen,
        send_period_report=_send_period_report,
        monobank_client_factory=_monobank_client_factory,
        handle_nlq_fn=_handle_nlq_fn,
    )

    register_start_handlers(dp, ctx=ctx)
    register_menu_handlers(dp, ctx=ctx)
    register_onboarding_handlers(dp, ctx=ctx)
    register_uncat_handlers(dp, ctx=ctx)
    register_report_handlers(dp, ctx=ctx)
    register_text_handlers(dp, ctx=ctx)
    register_dev_handlers(dp, ctx=ctx)
