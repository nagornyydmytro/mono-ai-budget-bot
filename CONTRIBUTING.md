Contributing to Mono AI Budget Bot

Python version:
>=3.11,<3.14

Setup:
poetry install

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