import argparse
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


def main() -> int:
    parser = argparse.ArgumentParser(prog="mono-ai-budget-bot")
    parser.add_argument("--version", action="store_true", help="Print version and exit")
    parser.add_argument(
        "command",
        nargs="?",
        default="health",
        choices=["health", "status-env", "mono-client-info", "mono-statement", "range", "analytics"],
        help="Command to run",
    )

    parser.add_argument(
        "--period",
        choices=["today", "week", "month"],
        default="today",
        help="Calendar period in Kyiv timezone (used with range / mono-statement). Default: today",
    )
    parser.add_argument(
        "--account",
        type=str,
        default=None,
        help="Monobank account id to fetch statement for (used with mono-statement). "
        "If omitted, the first account from client-info will be used.",
    )

    args = parser.parse_args()

    if args.version:
        print(__version__)
        return 0

    settings = load_settings()
    setup_logging(settings.log_level)

    logger = logging.getLogger(__name__)

    if args.command == "health":
        logger.info("Application started successfully.")
        print("ok")
        return 0

    if args.command == "status-env":
        print("TELEGRAM_BOT_TOKEN =", mask(settings.telegram_bot_token))
        print("MONO_TOKEN =", mask(settings.mono_token))
        print("OPENAI_API_KEY =", mask(settings.openai_api_key))
        print("OPENAI_MODEL =", settings.openai_model)
        print("LOG_LEVEL =", settings.log_level)
        return 0

    if args.command == "range":
        from .core.time_ranges import range_month, range_today, range_week

        if args.period == "today":
            dr = range_today()
        elif args.period == "week":
            dr = range_week()
        else:
            dr = range_month()

        date_from, date_to = dr.to_unix()
        print("period =", args.period)
        print("dt_from =", dr.dt_from.isoformat())
        print("dt_to   =", dr.dt_to.isoformat())
        print("unix_from =", date_from)
        print("unix_to   =", date_to)
        return 0

    if args.command == "mono-client-info":
        from .monobank import MonobankClient

        mb = MonobankClient(token=settings.mono_token)
        try:
            info = mb.client_info()
        finally:
            mb.close()

        accounts_count = len(info.accounts)
        print("client_name =", info.name)
        print("accounts_count =", accounts_count)

        for acc in info.accounts[:5]:
            masked = acc.maskedPan[:1] if acc.maskedPan else []
            print(
                "account:",
                acc.id,
                "currencyCode=",
                acc.currencyCode,
                "balance=",
                acc.balance,
                "maskedPan=",
                masked,
            )

        if accounts_count > 5:
            print(f"... and {accounts_count - 5} more accounts")
        return 0

    if args.command == "mono-statement":
        from .core.time_ranges import range_month, range_today, range_week
        from .monobank import MonobankClient

        if args.period == "today":
            dr = range_today()
        elif args.period == "week":
            dr = range_week()
        else:
            dr = range_month()

        date_from, date_to = dr.to_unix()

        mb = MonobankClient(token=settings.mono_token)
        try:
            info = mb.client_info()
            account_id = args.account or (info.accounts[0].id if info.accounts else None)
            if not account_id:
                raise RuntimeError("No accounts returned by Monobank client-info.")

            items = mb.statement(account=account_id, date_from=date_from, date_to=date_to)
        finally:
            mb.close()

        print("period =", args.period)
        print("account_id =", account_id)
        print("transactions_count =", len(items))

        for it in items[:10]:
            desc = (it.description or "").replace("\n", " ").strip()
            if len(desc) > 80:
                desc = desc[:77] + "..."
            print("tx:", it.time, "amount=", it.amount, "mcc=", it.mcc, "desc=", desc)

        if len(items) > 10:
            print(f"... and {len(items) - 10} more transactions")
        return 0

    if args.command == "analytics":
        from .core.time_ranges import range_month, range_today, range_week
        from .monobank import MonobankClient
        from .analytics.from_monobank import rows_from_statement
        from .analytics.compute import compute_facts

        if args.period == "today":
            dr = range_today()
        elif args.period == "week":
            dr = range_week()
        else:
            dr = range_month()

        date_from, date_to = dr.to_unix()

        mb = MonobankClient(token=settings.mono_token)
        try:
            info = mb.client_info()
            rows = []
            # IMPORTANT: in this commit we fetch ONE account by default to avoid 60s limit per account.
            # Full merge across all accounts will come right after (with smarter batching or via cached runs).
            account_id = args.account or (info.accounts[0].id if info.accounts else None)
            if not account_id:
                raise RuntimeError("No accounts returned by Monobank client-info.")

            items = mb.statement(account=account_id, date_from=date_from, date_to=date_to)
            rows.extend(rows_from_statement(account_id, items))
        finally:
            mb.close()

        facts = compute_facts(rows)
        print(f"period = {args.period}")
        print(f"account_id = {account_id}")
        print(facts)
        return 0

    return 1