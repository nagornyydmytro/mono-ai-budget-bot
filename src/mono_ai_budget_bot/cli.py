import argparse

from . import __version__

def main() -> int:
    parser = argparse.ArgumentParser(prog="mono-ai-budget-bot")
    parser.add_argument("--version", action="store_true", help="Print version and exit")
    parser.add_argument("command", nargs="?", default="health", choices=["health"])
    args = parser.parse_args()

    if args.version:
        print(__version__)
        return 0

    if args.command == "health":
        print("ok")
        return 0

    return 1