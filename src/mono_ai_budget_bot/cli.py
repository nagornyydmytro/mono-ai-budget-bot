from __future__ import annotations

import argparse
import asyncio
import logging

from . import __version__
from .config import load_settings
from .logging_setup import setup_logging


def mask(value: str | None, show: int = 4) -> str:
    if not value:
        return "None"
    if len(value) <= show:
        return "*" * len(value)
    return value[:show] + "*" * (len(value) - show)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="monobot", description="Mono AI Budget Bot CLI")
    p.add_argument("--version", action="store_true", help="Print version and exit")
    p.add_argument(
        "command",
        nargs="?",
        default="health",
        choices=["health", "status-env", "range", "bot"],
        help="Command to run",
    )
    p.add_argument(
        "--period",
        choices=["today", "week", "month"],
        default="today",
        help="Calendar period in Kyiv timezone (used with range)",
    )
    return p


def cmd_health() -> int:
    print("ok")
    return 0


def cmd_status_env() -> int:
    settings = load_settings()
    setup_logging(settings.log_level)
    logging.getLogger(__name__).info("Loaded settings")

    print("TELEGRAM_BOT_TOKEN =", mask(settings.telegram_bot_token))
    print("MASTER_KEY =", mask(settings.master_key))
    print("CACHE_DIR =", str(settings.cache_dir))
    print("OPENAI_API_KEY =", mask(settings.openai_api_key))
    print("OPENAI_MODEL =", settings.openai_model)
    print("LOG_LEVEL =", settings.log_level)
    print("MONO_TOKEN =", mask(settings.mono_token), "(optional debug)")
    return 0


def cmd_range(period: str) -> int:
    from .core.time_ranges import range_month, range_today, range_week

    if period == "today":
        dr = range_today()
    elif period == "week":
        dr = range_week()
    else:
        dr = range_month()

    date_from, date_to = dr.to_unix()
    print("period =", period)
    print("dt_from =", dr.dt_from.isoformat())
    print("dt_to =", dr.dt_to.isoformat())
    print("unix_from=", date_from)
    print("unix_to =", date_to)
    return 0


def cmd_bot() -> int:
    from .bot.app import main as bot_main

    asyncio.run(bot_main())
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.version:
        print(__version__)
        return 0

    if args.command == "health":
        return cmd_health()
    if args.command == "status-env":
        return cmd_status_env()
    if args.command == "range":
        return cmd_range(args.period)
    if args.command == "bot":
        return cmd_bot()

    return 1
