from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mono_ai_budget_bot.analytics.compute import compute_facts
from mono_ai_budget_bot.analytics.enrich import enrich_period_facts
from mono_ai_budget_bot.analytics.from_ledger import rows_from_ledger
from mono_ai_budget_bot.bot.ui import build_currency_screen_keyboard
from mono_ai_budget_bot.core.time_ranges import range_today
from mono_ai_budget_bot.currency import MonobankPublicClient, normalize_records_to_uah
from mono_ai_budget_bot.monobank import MonobankClient
from mono_ai_budget_bot.storage.report_store import ReportStore
from mono_ai_budget_bot.storage.tx_store import TxStore

from ..analytics.profile import build_user_profile
from ..config import load_settings
from ..logging_setup import setup_logging
from ..reports.renderer import render_report_for_user as _render_report_for_user_impl
from ..storage.profile_store import ProfileStore
from ..storage.reports_store import ReportsStore
from ..storage.rules_store import RulesStore
from ..storage.taxonomy_store import TaxonomyStore
from ..storage.uncat_store import UncatStore
from ..storage.user_store import UserConfig, UserStore
from ..taxonomy.presets import build_taxonomy_preset
from ..uncat.pending import UncatPendingStore
from ..uncat.queue import build_uncat_queue
from . import templates

if TYPE_CHECKING:
    pass


store = ReportStore()
tx_store = TxStore()

_MD_SPECIAL = "\\`*_[]()"


def md_escape(text: str) -> str:
    if text is None:
        return ""
    s = str(text)
    out = []
    for ch in s:
        if ch in _MD_SPECIAL:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def _map_monobank_error(e: Exception) -> str | None:
    s = str(e)

    if "Monobank API error: 401" in s or "Monobank API error: 403" in s:
        return templates.monobank_invalid_token_message()

    if "Monobank API error: 429" in s:
        return templates.monobank_rate_limit_message()

    if "Monobank API error:" in s:
        return templates.monobank_generic_error_message()

    return None


def _map_llm_error(_: Exception) -> str:
    return templates.llm_unavailable_message()


def _safe_get(d: dict, path: list[str], default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def _mask_secret(s: str, show: int = 4) -> str:
    if not s:
        return "None"
    if len(s) <= show:
        return "*" * len(s)
    return s[:show] + "*" * (len(s) - show)


def _save_selected_accounts(users: UserStore, telegram_user_id: int, selected: list[str]) -> None:
    cfg = users.load(telegram_user_id)
    if cfg is None:
        return
    users.save(telegram_user_id, mono_token=cfg.mono_token, selected_account_ids=selected)


def _ensure_ready(cfg: UserConfig | None) -> str | None:
    if cfg is None or not cfg.mono_token:
        return templates.err_not_connected()
    if not cfg.selected_account_ids:
        return templates.err_no_accounts_selected()
    return None


def render_accounts_screen(accounts: list[dict], selected_ids: set[str]) -> tuple[str, Any]:
    from aiogram.types import InlineKeyboardMarkup
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    lines: list[str] = []
    lines.append(
        templates.accounts_picker_header(
            selected=len(selected_ids),
            total=len(accounts),
        )
    )

    kb = InlineKeyboardBuilder()

    for acc in accounts:
        acc_id = acc["id"]
        masked = " / ".join(acc.get("maskedPan") or []) or "без картки"
        cur = str(acc.get("currencyCode", ""))
        mark = "✅" if acc_id in selected_ids else "⬜️"
        text = f"{mark} {masked} ({cur})"
        kb.button(text=text, callback_data=f"acc_toggle:{acc_id}")

    kb.adjust(1)
    kb.button(text="🧹 Clear", callback_data="acc_clear")
    kb.button(text="✅ Done", callback_data="acc_done")
    kb.adjust(1, 2)

    markup: InlineKeyboardMarkup = kb.as_markup()
    return "\n".join(lines).strip(), markup


def _currency_screen_keyboard():
    return build_currency_screen_keyboard()


def _render_currency_screen_text(rates) -> str:
    def pick(code_a: int, code_b: int = 980):
        for r in rates:
            if int(getattr(r, "currencyCodeA", -1)) == int(code_a) and int(
                getattr(r, "currencyCodeB", -1)
            ) == int(code_b):
                return r
        return None

    def fmt_rate(r) -> str:
        rb = getattr(r, "rateBuy", None)
        rs = getattr(r, "rateSell", None)
        rc = getattr(r, "rateCross", None)
        parts = []
        if rc is not None:
            parts.append(f"cross {float(rc):.4f}")
        if rb is not None:
            parts.append(f"buy {float(rb):.4f}")
        if rs is not None:
            parts.append(f"sell {float(rs):.4f}")
        return ", ".join(parts) if parts else "немає даних"

    updated_ts = 0
    for r in rates:
        try:
            updated_ts = max(updated_ts, int(getattr(r, "date", 0) or 0))
        except Exception:
            pass

    updated = "—"
    if updated_ts > 0:
        updated = datetime.fromtimestamp(updated_ts).isoformat(timespec="seconds")

    usd = pick(840)
    eur = pick(978)
    pln = pick(985)

    usd_s = md_escape(fmt_rate(usd)) if usd else None
    eur_s = md_escape(fmt_rate(eur)) if eur else None
    pln_s = md_escape(fmt_rate(pln)) if pln else None

    return templates.currency_screen_text(md_escape(updated), usd_s, eur_s, pln_s)


def _render_report_for_user(
    reports_store: ReportsStore,
    tg_id: int,
    period: str,
    facts: dict,
    *,
    ai_block: str | None = None,
) -> str:
    return _render_report_for_user_impl(
        reports_store,
        tg_id,
        period,
        facts,
        ai_block=ai_block,
    )


async def refresh_period_for_user(period: str, cfg, store: ReportStore) -> None:
    if not cfg.selected_account_ids:
        return

    account_ids = list(cfg.selected_account_ids)

    if period == "today":
        dr = range_today()
        ts_from, ts_to = dr.to_unix()
        records = tx_store.load_range(cfg.telegram_user_id, account_ids, ts_from, ts_to)
        rows = rows_from_ledger(records)
        facts = compute_facts(rows)
        store.save(cfg.telegram_user_id, period, facts)
        return

    if period == "week":
        days_back = 7
    else:
        days_back = 30

    now_ts = int(time.time())

    ts_from = now_ts - (2 * days_back + 1) * 24 * 60 * 60
    ts_to = now_ts

    records = tx_store.load_range(cfg.telegram_user_id, account_ids, ts_from, ts_to)

    current_facts = enrich_period_facts(records, days_back=days_back, now_ts=now_ts)

    store.save(cfg.telegram_user_id, period, current_facts)


def build_ai_block(summary: str, changes: list[str], recs: list[str], next_step: str) -> str:
    lines: list[str] = []
    lines.append(f"• {md_escape(summary)}")

    if changes:
        lines.append("")
        lines.append("*Що змінилось:*")
        for s in changes[:5]:
            lines.append(f"• {md_escape(s)}")

    if recs:
        lines.append("")
        lines.append("*Рекомендації:*")
        for s in recs[:7]:
            lines.append(f"• {md_escape(s)}")

    lines.append("")
    lines.append("*Наступний крок (7 днів):*")
    lines.append(f"• {md_escape(next_step)}")
    return "\n".join(lines)


async def _compute_and_cache_reports_for_user(
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
    try:
        pub = MonobankPublicClient()
        rates = pub.currency()
        profile_records = normalize_records_to_uah(profile_records, rates)
        pub.close()
    except Exception:
        try:
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


async def main() -> None:
    from aiogram import Bot, Dispatcher
    from aiogram.client.default import DefaultBotProperties

    settings = load_settings(require_bot_token=True)
    setup_logging(settings.log_level)
    profile_store = ProfileStore(Path(".cache") / "profiles")
    taxonomy_store = TaxonomyStore(Path(".cache") / "taxonomy")
    reports_store = ReportsStore(Path(".cache") / "reports")

    def render_report_for_user(
        tg_id: int,
        period: str,
        facts: dict,
        *,
        ai_block: str | None = None,
    ) -> str:
        return _render_report_for_user(
            reports_store,
            tg_id,
            period,
            facts,
            ai_block=ai_block,
        )

    uncat_store = UncatStore(Path(".cache") / "uncat")
    rules_store = RulesStore(Path(".cache") / "rules")
    uncat_pending_store = UncatPendingStore(Path(".cache") / "uncat_pending")

    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode="Markdown"),
    )

    dp = Dispatcher()

    user_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    users = UserStore()

    logger = logging.getLogger("mono_ai_budget_bot.bot")

    async def sync_user_ledger(tg_id: int, cfg: UserConfig, *, days_back: int) -> object:
        from ..monobank.sync import sync_accounts_ledger

        account_ids = list(cfg.selected_account_ids or [])
        token = cfg.mono_token

        def _run() -> object:
            mb = MonobankClient(token=token)
            try:
                return sync_accounts_ledger(
                    mb=mb,
                    tx_store=tx_store,
                    telegram_user_id=tg_id,
                    account_ids=account_ids,
                    days_back=days_back,
                )
            finally:
                mb.close()

        return await asyncio.to_thread(_run)

    from .scheduler import create_scheduler, start_jobs

    scheduler = create_scheduler(logger)
    loop = asyncio.get_running_loop()

    start_jobs(
        scheduler,
        loop=loop,
        bot=bot,
        users=users,
        report_store=store,
        render_report_text=render_report_for_user,
        logger=logger,
        sync_user_ledger=sync_user_ledger,
        recompute_reports_for_user=lambda tg_id, account_ids: _compute_and_cache_reports_for_user(
            tg_id, account_ids, profile_store
        ),
        profile_store=profile_store,
        uncat_store=uncat_store,
    )

    from .handlers import register_handlers

    register_handlers(
        dp,
        bot=bot,
        settings=settings,
        users=users,
        store=store,
        tx_store=tx_store,
        profile_store=profile_store,
        taxonomy_store=taxonomy_store,
        reports_store=reports_store,
        uncat_store=uncat_store,
        rules_store=rules_store,
        uncat_pending_store=uncat_pending_store,
        user_locks=user_locks,
        logger=logger,
        sync_user_ledger=sync_user_ledger,
        render_report_for_user=render_report_for_user,
    )

    logger.info("Starting Telegram bot polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
