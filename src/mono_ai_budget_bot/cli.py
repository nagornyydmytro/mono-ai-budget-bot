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
        choices=["health", "status-env", "mono-client-info"],
        help="Command to run",
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

    return 1