from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class ScheduleConfig:
    test_mode: bool
    tz_name: str
    weekly_cron: str
    monthly_cron: str
    refresh_minutes: int
    daily_refresh_cron: str


def load_schedule_config() -> ScheduleConfig:
    """
    Env:
    - SCHED_TEST_MODE=1 -> refresh every 1 min, weekly every 2 min, monthly every 3 min (dev)
    - SCHED_TZ=Europe/Kyiv (default)
    - SCHED_REFRESH_MINUTES=120  (prod: every 1-3 hours)
    - SCHED_DAILY_REFRESH_CRON="0 6 * * *" (daily refresh at 06:00)
    - SCHED_WEEKLY_CRON="0 9 * * 1"  (Mon 09:00)
    - SCHED_MONTHLY_CRON="0 9 1 * *" (1st day 09:00)
    """
    test_mode = os.getenv("SCHED_TEST_MODE", "").strip() == "1"
    tz_name = os.getenv("SCHED_TZ", "Europe/Kyiv").strip() or "Europe/Kyiv"

    weekly_cron = os.getenv("SCHED_WEEKLY_CRON", "0 9 * * 1").strip()
    monthly_cron = os.getenv("SCHED_MONTHLY_CRON", "0 9 1 * *").strip()
    daily_refresh_cron = os.getenv("SCHED_DAILY_REFRESH_CRON", "0 6 * * *").strip()

    refresh_minutes_str = os.getenv("SCHED_REFRESH_MINUTES", "120").strip()
    try:
        refresh_minutes = int(refresh_minutes_str)
    except Exception:
        refresh_minutes = 120

    if test_mode:
        weekly_cron = "*/2 * * * *"
        monthly_cron = "*/3 * * * *"
        daily_refresh_cron = "*/2 * * * *"
        refresh_minutes = 1

    return ScheduleConfig(
        test_mode=test_mode,
        tz_name=tz_name,
        weekly_cron=weekly_cron,
        monthly_cron=monthly_cron,
        refresh_minutes=refresh_minutes,
        daily_refresh_cron=daily_refresh_cron,
    )


def _parse_cron(expr: str) -> dict:
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression: {expr}")
    minute, hour, day, month, dow = parts
    return {
        "minute": minute,
        "hour": hour,
        "day": day,
        "month": month,
        "day_of_week": dow,
    }


def create_scheduler(logger: logging.Logger) -> AsyncIOScheduler:
    cfg = load_schedule_config()

    tz = None
    if ZoneInfo is not None:
        try:
            tz = ZoneInfo(cfg.tz_name)
        except Exception:
            logger.warning("ZoneInfo timezone not found: %s. Falling back to UTC.", cfg.tz_name)
            try:
                tz = ZoneInfo("UTC")
            except Exception:
                tz = None

    return AsyncIOScheduler(timezone=tz)


async def safe_send(bot, chat_id: int, text: str, logger: logging.Logger) -> None:
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode=None)
    except Exception as e:
        logger.warning("Failed to send message to chat_id=%s: %s", chat_id, e)


def start_jobs(
    scheduler: AsyncIOScheduler,
    *,
    loop: asyncio.AbstractEventLoop,
    bot,
    users,
    report_store,
    render_report_text,
    logger: logging.Logger,
    sync_user_ledger,
    recompute_reports_for_user,
) -> None:
    cfg = load_schedule_config()

    async def _refresh_user(u, *, days_back: int) -> bool:
        """
        Incremental refresh:
        - sync ledger (days_back)
        - recompute today/week/month facts from ledger
        """
        if not getattr(u, "autojobs_enabled", True):
            return False
        if not getattr(u, "chat_id", None):
            return False
        if not getattr(u, "mono_token", None):
            return False

        account_ids = list(getattr(u, "selected_account_ids", []) or [])
        if not account_ids:
            return False

        try:
            await sync_user_ledger(u.telegram_user_id, u, days_back=days_back)
            await recompute_reports_for_user(u.telegram_user_id, account_ids)
            return True
        except Exception as e:
            logger.warning("Refresh error for user=%s: %s", getattr(u, "telegram_user_id", "?"), e)
            return False

    async def job_refresh_all_users(*, days_back: int) -> None:
        logger.info("Scheduler: refresh_all_users started (days_back=%s)", days_back)
        refreshed = 0
        scanned = 0
        for u in users.iter_all():
            scanned += 1
            ok = await _refresh_user(u, days_back=days_back)
            if ok:
                refreshed += 1
        logger.info(
            "Scheduler: refresh_all_users done. scanned=%s refreshed=%s (days_back=%s)",
            scanned,
            refreshed,
            days_back,
        )

    async def job_weekly_report() -> None:
        logger.info("Scheduler: weekly_report started")
        for u in users.iter_all():
            ok = await _refresh_user(u, days_back=8)
            if not ok:
                continue

            stored = report_store.load(u.telegram_user_id, "week")
            if stored is None:
                continue

            text = render_report_text("week", stored.facts)
            await safe_send(bot, u.chat_id, text, logger)

        logger.info("Scheduler: weekly_report done")

    async def job_monthly_report() -> None:
        logger.info("Scheduler: monthly_report started")
        for u in users.iter_all():
            ok = await _refresh_user(u, days_back=32)
            if not ok:
                continue

            stored = report_store.load(u.telegram_user_id, "month")
            if stored is None:
                continue

            text = render_report_text("month", stored.facts)
            await safe_send(bot, u.chat_id, text, logger)

        logger.info("Scheduler: monthly_report done")

    def refresh_wrapper_interval() -> None:
        loop.create_task(job_refresh_all_users(days_back=2))

    def refresh_wrapper_daily() -> None:
        loop.create_task(job_refresh_all_users(days_back=8))

    def weekly_wrapper() -> None:
        loop.create_task(job_weekly_report())

    def monthly_wrapper() -> None:
        loop.create_task(job_monthly_report())

    scheduler.add_job(
        refresh_wrapper_interval,
        IntervalTrigger(minutes=cfg.refresh_minutes),
        id="refresh_all_users",
        replace_existing=True,
    )

    daily_trigger = CronTrigger(**_parse_cron(cfg.daily_refresh_cron))
    scheduler.add_job(
        refresh_wrapper_daily,
        daily_trigger,
        id="daily_refresh_all_users",
        replace_existing=True,
    )

    weekly_trigger = CronTrigger(**_parse_cron(cfg.weekly_cron))
    monthly_trigger = CronTrigger(**_parse_cron(cfg.monthly_cron))

    scheduler.add_job(weekly_wrapper, weekly_trigger, id="weekly_report", replace_existing=True)
    scheduler.add_job(monthly_wrapper, monthly_trigger, id="monthly_report", replace_existing=True)

    scheduler.start()
    logger.info(
        "Scheduler started (test_mode=%s). refresh_every=%s min daily='%s' weekly='%s' monthly='%s'",
        cfg.test_mode,
        cfg.refresh_minutes,
        cfg.daily_refresh_cron,
        cfg.weekly_cron,
        cfg.monthly_cron,
    )
