from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from dotenv import load_dotenv
load_dotenv()


@dataclass(frozen=True)
class ScheduleConfig:
    test_mode: bool
    tz_name: str
    weekly_cron: str
    monthly_cron: str


def load_schedule_config() -> ScheduleConfig:
    """
    Env:
    - SCHED_TEST_MODE=1 -> weekly кажні 2 хв, monthly кожні 3 хв (для dev)
    - SCHED_TZ=Europe/Kyiv (default)
    - SCHED_WEEKLY_CRON="0 9 * * 1"  (Mon 09:00)
    - SCHED_MONTHLY_CRON="0 9 1 * *" (1st day 09:00)
    """
    test_mode = os.getenv("SCHED_TEST_MODE", "").strip() == "1"
    tz_name = os.getenv("SCHED_TZ", "Europe/Kyiv").strip() or "Europe/Kyiv"

    weekly_cron = os.getenv("SCHED_WEEKLY_CRON", "0 9 * * 1").strip()
    monthly_cron = os.getenv("SCHED_MONTHLY_CRON", "0 9 1 * *").strip()

    if test_mode:
        weekly_cron = "*/2 * * * *"
        monthly_cron = "*/3 * * * *"

    return ScheduleConfig(
        test_mode=test_mode,
        tz_name=tz_name,
        weekly_cron=weekly_cron,
        monthly_cron=monthly_cron,
    )


def _parse_cron(expr: str) -> dict:
    # "min hour day month dow"
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

    scheduler = AsyncIOScheduler(timezone=tz)
    return scheduler


async def safe_send(bot, chat_id: int, text: str, logger: logging.Logger) -> None:
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    except Exception as e:
        logger.warning("Failed to send message to chat_id=%s: %s", chat_id, e)


def start_jobs(
    scheduler: AsyncIOScheduler,
    *,
    loop: asyncio.AbstractEventLoop,
    bot,
    users,
    report_store,
    refresh_period_for_user,
    render_report_text,
    logger: logging.Logger,
) -> None:
    cfg = load_schedule_config()

    async def job_weekly() -> None:
        logger.info("Scheduler: weekly job started")
        for u in users.iter_all():
            # skip users without enabled autojobs / chat_id / mono token
            if not getattr(u, "autojobs_enabled", True):
                continue
            if not getattr(u, "chat_id", None):
                continue
            if not getattr(u, "mono_token", None):
                continue

            try:
                await refresh_period_for_user("week", u, report_store)
                stored = report_store.load("week")
                if stored is None:
                    continue
                text = render_report_text("week", stored.facts)
                await safe_send(bot, u.chat_id, text, logger)
            except Exception as e:
                logger.warning("Weekly job error for user=%s: %s", getattr(u, "telegram_user_id", "?"), e)

    async def job_monthly() -> None:
        logger.info("Scheduler: monthly job started")
        for u in users.iter_all():
            if not getattr(u, "autojobs_enabled", True):
                continue
            if not getattr(u, "chat_id", None):
                continue
            if not getattr(u, "mono_token", None):
                continue

            try:
                await refresh_period_for_user("month", u, report_store)
                stored = report_store.load("month")
                if stored is None:
                    continue
                text = render_report_text("month", stored.facts)
                await safe_send(bot, u.chat_id, text, logger)
            except Exception as e:
                logger.warning("Monthly job error for user=%s: %s", getattr(u, "telegram_user_id", "?"), e)

    # APScheduler calls sync callables — we schedule async jobs onto the running loop
    def weekly_wrapper() -> None:
        loop.create_task(job_weekly())

    def monthly_wrapper() -> None:
        loop.create_task(job_monthly())

    weekly_trigger = CronTrigger(**_parse_cron(cfg.weekly_cron))
    monthly_trigger = CronTrigger(**_parse_cron(cfg.monthly_cron))

    scheduler.add_job(weekly_wrapper, weekly_trigger, id="weekly_report", replace_existing=True)
    scheduler.add_job(monthly_wrapper, monthly_trigger, id="monthly_report", replace_existing=True)

    scheduler.start()
    logger.info(
        "Scheduler started (test_mode=%s). weekly='%s' monthly='%s'",
        cfg.test_mode,
        cfg.weekly_cron,
        cfg.monthly_cron,
    )