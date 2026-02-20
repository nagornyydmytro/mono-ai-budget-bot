# mono-ai-budget-bot

Telegram bot that connects to Monobank Personal API, analyzes spending across all accounts, and generates reports (with AI insights later).

## Features (planned)
- Connect Monobank token
- /today /week /month reports across all accounts
- Period-over-period comparison
- AI-generated insights and recommendations

## Setup
1) Install dependencies:
```bash
poetry install
poetry run python -m mono_ai_budget_bot --version
poetry run python -m mono_ai_budget_bot health