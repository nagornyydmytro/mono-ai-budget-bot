from __future__ import annotations

from mono_ai_budget_bot.bot import templates_alerts as _alerts
from mono_ai_budget_bot.bot import templates_categories as _categories
from mono_ai_budget_bot.bot import templates_common as _common
from mono_ai_budget_bot.bot import templates_currency as _currency
from mono_ai_budget_bot.bot import templates_insights as _insights
from mono_ai_budget_bot.bot import templates_menu as _menu
from mono_ai_budget_bot.bot import templates_nlq as _nlq
from mono_ai_budget_bot.bot import templates_onboarding as _onboarding

for _module in (
    _alerts,
    _categories,
    _common,
    _currency,
    _insights,
    _menu,
    _nlq,
    _onboarding,
):
    for _name in dir(_module):
        if _name.startswith("_"):
            continue
        globals()[_name] = getattr(_module, _name)

__all__ = [name for name in globals() if not name.startswith("_")]
