from __future__ import annotations

import time
from pathlib import Path

from mono_ai_budget_bot.analytics.compute import compute_facts
from mono_ai_budget_bot.analytics.enrich import enrich_period_facts
from mono_ai_budget_bot.analytics.from_ledger import rows_from_ledger
from mono_ai_budget_bot.core.time_ranges import range_today
from mono_ai_budget_bot.currency import MonobankPublicClient, normalize_records_to_uah

from ..analytics.profile import build_user_profile
from ..storage.profile_store import ProfileStore
from ..storage.report_store import ReportStore
from ..storage.rules_store import RulesStore
from ..storage.taxonomy_store import TaxonomyStore
from ..storage.tx_store import TxStore
from ..storage.uncat_store import UncatStore
from ..taxonomy.presets import build_taxonomy_preset
from ..uncat.queue import build_uncat_queue
from . import templates
from .renderers import md_escape

store = ReportStore()
tx_store = TxStore()


def build_ai_block(summary: str, changes: list[str], recs: list[str], next_step: str) -> str:
    lines: list[str] = []
    lines.append(f"• {md_escape(summary)}")

    if changes:
        lines.append("")
        lines.append(templates.ai_block_title_changes())
        for s in changes[:5]:
            lines.append(f"• {md_escape(s)}")

    if recs:
        lines.append("")
        lines.append(templates.ai_block_title_recommendations())
        for s in recs[:7]:
            lines.append(f"• {md_escape(s)}")

    lines.append("")
    lines.append(templates.ai_block_title_next_step())
    lines.append(f"• {md_escape(next_step)}")
    return "\n".join(lines)


async def compute_and_cache_reports_for_user(
    tg_id: int,
    account_ids: list[str],
    profile_store: ProfileStore,
) -> None:
    dr = range_today()
    ts_from, ts_to = dr.to_unix()
    records = tx_store.load_range(tg_id, account_ids, ts_from, ts_to)
    rows = rows_from_ledger(records)
    facts = compute_facts(rows)
    store.save(tg_id, "today", facts)

    now_ts = int(time.time())
    profile_from = now_ts - 90 * 24 * 60 * 60
    profile_records = tx_store.load_range(tg_id, account_ids, profile_from, now_ts)
    profile = build_user_profile(profile_records)
    pub = None
    try:
        pub = MonobankPublicClient()
        rates = pub.currency()
        profile_records = normalize_records_to_uah(profile_records, rates)
    except Exception:
        pass
    finally:
        try:
            if pub is not None:
                pub.close()
        except Exception:
            pass

    profile_store.save(tg_id, profile)

    taxonomy_store = TaxonomyStore(Path(".cache") / "taxonomy")
    uncat_store = UncatStore(Path(".cache") / "uncat")
    rules_store = RulesStore(Path(".cache") / "rules")

    for period, days_back in (("week", 7), ("month", 30)):
        now_ts = int(time.time())
        ts_from = now_ts - (2 * days_back + 1) * 24 * 60 * 60
        ts_to = now_ts

        records = tx_store.load_range(tg_id, account_ids, ts_from, ts_to)
        current_facts = enrich_period_facts(records, days_back=days_back, now_ts=now_ts)
        store.save(tg_id, period, current_facts)

    tax = taxonomy_store.load(tg_id)
    if tax is None:
        tax = build_taxonomy_preset("min")

    rules = rules_store.load(tg_id)
    uncat_items = build_uncat_queue(tax=tax, records=profile_records, rules=rules, limit=200)
    uncat_store.save(tg_id, uncat_items)
