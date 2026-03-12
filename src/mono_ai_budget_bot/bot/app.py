from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

from mono_ai_budget_bot.analytics.compute import compute_facts
from mono_ai_budget_bot.analytics.enrich import enrich_period_facts
from mono_ai_budget_bot.analytics.from_ledger import rows_from_ledger
from mono_ai_budget_bot.core.time_ranges import range_today
from mono_ai_budget_bot.monobank import MonobankClient
from mono_ai_budget_bot.storage.report_store import ReportStore
from mono_ai_budget_bot.storage.tx_store import TxStore

from ..config import load_bot_runtime_settings
from ..logging_setup import setup_logging
from ..reports.renderer import render_report_for_user as _render_report_for_user_impl
from ..storage.profile_store import ProfileStore
from ..storage.reports_store import ReportsStore
from ..storage.rules_store import RulesStore
from ..storage.taxonomy_store import TaxonomyStore
from ..storage.uncat_store import UncatStore
from ..storage.user_store import UserConfig, UserStore
from ..uncat.pending import UncatPendingStore
from . import templates
from .report_flow_helpers import compute_and_cache_reports_for_user

if TYPE_CHECKING:
    pass


store = ReportStore()
tx_store = TxStore()


def _safe_get(d: dict, path: list[str], default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def _ensure_ready(cfg: UserConfig | None) -> str | None:
    if cfg is None or not cfg.mono_token:
        return templates.err_not_connected()
    if not cfg.selected_account_ids:
        return templates.err_no_accounts_selected()
    return None


def _render_report_for_user(
    reports_store: ReportsStore,
    tg_id: int,
    period: str,
    facts: dict,
    *,
    ai_block: str | None = None,
) -> str:
    return _render_report_for_user_impl(
        reports_store,
        tg_id,
        period,
        facts,
        ai_block=ai_block,
    )


async def refresh_period_for_user(period: str, cfg, store: ReportStore) -> None:
    if not cfg.selected_account_ids:
        return

    account_ids = list(cfg.selected_account_ids)

    if period == "today":
        dr = range_today()
        ts_from, ts_to = dr.to_unix()
        records = tx_store.load_range(cfg.telegram_user_id, account_ids, ts_from, ts_to)
        rows = rows_from_ledger(records)
        facts = compute_facts(rows)

        cov = tx_store.aggregated_coverage_window(cfg.telegram_user_id, account_ids)
        if cov is not None:
            facts["coverage"] = {
                "coverage_from_ts": int(cov[0]),
                "coverage_to_ts": int(cov[1]),
                "requested_from_ts": int(ts_from),
                "requested_to_ts": int(ts_to),
            }

        store.save(cfg.telegram_user_id, period, facts)
        return

    if period == "week":
        days_back = 7
    else:
        days_back = 30

    now_ts = int(time.time())

    ts_from = now_ts - (2 * days_back + 1) * 24 * 60 * 60
    ts_to = now_ts

    records = tx_store.load_range(cfg.telegram_user_id, account_ids, ts_from, ts_to)
    current_facts = enrich_period_facts(records, days_back=days_back, now_ts=now_ts)

    req_from = now_ts - days_back * 24 * 60 * 60
    req_to = now_ts

    cov = tx_store.aggregated_coverage_window(cfg.telegram_user_id, account_ids)
    if cov is not None and isinstance(current_facts, dict):
        current_facts["coverage"] = {
            "coverage_from_ts": int(cov[0]),
            "coverage_to_ts": int(cov[1]),
            "requested_from_ts": int(req_from),
            "requested_to_ts": int(req_to),
        }

    store.save(cfg.telegram_user_id, period, current_facts)


async def main() -> None:
    settings = load_bot_runtime_settings()

    from aiogram import Bot, Dispatcher
    from aiogram.client.default import DefaultBotProperties

    setup_logging(settings.log_level)
    profile_store = ProfileStore(Path(".cache") / "profiles")
    taxonomy_store = TaxonomyStore(Path(".cache") / "taxonomy")
    reports_store = ReportsStore(Path(".cache") / "reports")

    def render_report_for_user(
        tg_id: int,
        period: str,
        facts: dict,
        *,
        ai_block: str | None = None,
    ) -> str:
        return _render_report_for_user(
            reports_store,
            tg_id,
            period,
            facts,
            ai_block=ai_block,
        )

    uncat_store = UncatStore(Path(".cache") / "uncat")
    rules_store = RulesStore(Path(".cache") / "rules")
    uncat_pending_store = UncatPendingStore(Path(".cache") / "uncat_pending")

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode="Markdown"),
    )

    dp = Dispatcher()

    user_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    users = UserStore()

    logger = logging.getLogger("mono_ai_budget_bot.bot")

    async def sync_user_ledger(tg_id: int, cfg: UserConfig, *, days_back: int) -> object:
        from ..monobank.sync import sync_accounts_ledger

        account_ids = list(cfg.selected_account_ids or [])
        token = cfg.mono_token

        def _run() -> object:
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

        return await asyncio.to_thread(_run)

    from .scheduler import create_scheduler, start_jobs

    scheduler = create_scheduler(logger)
    loop = asyncio.get_running_loop()

    start_jobs(
        scheduler,
        loop=loop,
        bot=bot,
        users=users,
        report_store=store,
        render_report_text=render_report_for_user,
        logger=logger,
        sync_user_ledger=sync_user_ledger,
        recompute_reports_for_user=lambda tg_id, account_ids: compute_and_cache_reports_for_user(
            tg_id, account_ids, profile_store
        ),
        profile_store=profile_store,
        uncat_store=uncat_store,
    )

    from .handlers import register_handlers

    register_handlers(
        dp,
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
    )

    logger.info("Starting Telegram bot polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
