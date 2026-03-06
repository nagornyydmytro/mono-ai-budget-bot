from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class HandlerContext:
    bot: Any
    settings: Any
    users: Any
    store: Any
    tx_store: Any
    profile_store: Any
    taxonomy_store: Any
    reports_store: Any
    uncat_store: Any
    rules_store: Any
    uncat_pending_store: Any
    user_locks: dict[int, Any]
    logger: Any
    sync_user_ledger: Any
    render_report_for_user: Any
    sync_onboarding_progress: Any
    onboarding_done: Any
    prompt_finish_onboarding: Any
    gate_menu_query_or_resume: Any
    gate_menu_dependencies: Any
    gate_refresh_dependencies: Any
    send_onboarding_next: Any
    send_next_uncat: Any
    send_currency_screen: Any
    send_period_report: Any
    monobank_client_factory: Any
    handle_nlq_fn: Any
