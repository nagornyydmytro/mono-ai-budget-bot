Contributing to Mono AI Budget Bot

Python version:
>=3.11,<3.14

Setup:
poetry install

Local config:
- Copy .env.example → .env and fill required variables.
- Do not commit .env or any .env.* files (only .env.example is tracked).

Local state (stored under .cache/, ignored by git):
- .cache/users/<telegram_user_id>.json — encrypted token + selected accounts + chat_id
- .cache/tx/<telegram_user_id>/<account_id>.jsonl — local transaction ledger
- .cache/reports/<telegram_user_id>/facts_<period>.json — cached period facts (today/week/month)
- .cache/profiles/<telegram_user_id>.json — baseline profile cache
- .cache/memory/<telegram_user_id>.json — NLQ aliases + pending follow-ups

Reset to a clean slate:
- macOS/Linux:
  rm -rf .cache
- Windows PowerShell:
  Remove-Item -Recurse -Force .cache

Run local checks before commit:
poetry run ruff format .
poetry run ruff check .
poetry run pytest -q

Or run all checks via pre-commit:
poetry run python -m pre_commit run --all-files

All checks must pass before pushing.

Tests:
Located in tests/
Run with:
poetry run pytest

Code style:
- Use Ruff for linting and formatting
- Avoid unused variables
- Avoid ambiguous variable names
- Keep business logic out of Telegram handlers
- Keep analytics deterministic

Security rules:
- Never log raw Monobank tokens
- Never send raw transaction history to LLM
- LLM must receive only aggregated structured facts
- Financial calculations must never be done by LLM

Architecture layers:
- monobank/ — API client
- analytics/ — deterministic computation
- profile/ — baseline model
- categories/ — MCC taxonomy
- nlq/ — natural language pipeline
- llm/ — insight writer (facts-only)
- bot/ — Telegram interface
- storage/ — persistence layer

Design principle:
facts → structured JSON → LLM explanation
Never the other way around.

Commit convention:
Use prefixes:
feat:
refactor:
test:
chore:
docs:
deploy:

Example:
feat(analytics): add anomaly detection for merchant spikes