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
        choices=["health", "status-env", "mono-client-info", "mono-statement"],
        help="Command to run",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Number of last days for statement range (used with mono-statement). Default: 1",
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
        from .core.time_ranges import last_days
        from .monobank import MonobankClient

        mb = MonobankClient(token=settings.mono_token)
        try:
            info = mb.client_info()
            account_id = args.account or (info.accounts[0].id if info.accounts else None)
            if not account_id:
                raise RuntimeError("No accounts returned by Monobank client-info.")

            dr = last_days(max(1, args.days))
            date_from, date_to = dr.to_unix()

            items = mb.statement(account=account_id, date_from=date_from, date_to=date_to)
        finally:
            mb.close()

        print("account_id =", account_id)
        print("range_days =", max(1, args.days))
        print("transactions_count =", len(items))

        # Show a few sample rows (no sensitive details beyond description & amounts)
        for it in items[:10]:
            desc = (it.description or "").replace("\n", " ").strip()
            if len(desc) > 80:
                desc = desc[:77] + "..."
            print("tx:", it.time, "amount=", it.amount, "mcc=", it.mcc, "desc=", desc)

        if len(items) > 10:
            print(f"... and {len(items) - 10} more transactions")
        return 0

    return 1