from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from aiogram import Bot, Dispatcher
from aiogram.types import CallbackQuery

from mono_ai_budget_bot.currency import MonobankPublicClient
from mono_ai_budget_bot.monobank import MonobankClient
from mono_ai_budget_bot.nlq.pipeline import handle_nlq

from .handlers_common import HandlerContext
from .handlers_dev import register_dev_handlers
from .handlers_menu import register_menu_handlers
from .handlers_onboarding import register_onboarding_handlers
from .handlers_reports import register_report_handlers
from .handlers_runtime import build_handler_runtime
from .handlers_start import register_start_handlers
from .handlers_text import register_text_handlers
from .handlers_uncat import register_uncat_handlers

if TYPE_CHECKING:
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
    runtime = build_handler_runtime(
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
        logger=logger,
        sync_user_ledger=sync_user_ledger,
        render_report_for_user=render_report_for_user,
        monobank_client_cls=MonobankClient,
        monobank_public_client_cls=MonobankPublicClient,
        handle_nlq_fn=handle_nlq,
    )

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

        result = runtime["sync_onboarding_progress"](tg_id)
        if bool(result.get("completed")) != completed:
            return result
        return result

    def _onboarding_done(tg_id: int) -> bool:
        _sync_onboarding_progress(tg_id)
        prof = profile_store.load(tg_id) or {}
        return bool(prof.get("onboarding_completed"))

    async def _prompt_finish_onboarding(message, *, text: str | None = None) -> None:
        await runtime["prompt_finish_onboarding"](message, text=text)

    async def _gate_menu_query_or_resume(query: CallbackQuery) -> bool:
        return await runtime["gate_menu_query_or_resume"](query)

    async def _gate_menu_dependencies(
        query: CallbackQuery,
        *,
        require_token: bool = False,
        require_accounts: bool = False,
        require_ledger: bool = False,
    ) -> bool:
        return await runtime["gate_menu_dependencies"](
            query,
            require_token=require_token,
            require_accounts=require_accounts,
            require_ledger=require_ledger,
        )

    async def _gate_refresh_dependencies(query: CallbackQuery):
        return await runtime["gate_refresh_dependencies"](query)

    async def _send_onboarding_next(chat) -> None:
        await runtime["send_onboarding_next"](chat)

    async def _send_next_uncat(message, tg_id: int) -> None:
        await runtime["send_next_uncat"](message, tg_id)

    async def _send_currency_screen(message, *, force_refresh: bool) -> None:
        await runtime["send_currency_screen"](message, force_refresh=force_refresh)

    async def _send_period_report(
        message,
        period: str,
        *,
        tg_id_override: int | None = None,
        want_ai_override: bool | None = None,
    ) -> None:
        await runtime["send_period_report"](
            message,
            period,
            tg_id_override=tg_id_override,
            want_ai_override=want_ai_override,
        )

    def _monobank_client_factory(*, token: str):
        return MonobankClient(token=token)

    def _handle_nlq_fn(req):
        return runtime["handle_nlq_fn"](req)

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
