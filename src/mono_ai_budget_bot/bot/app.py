from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from collections.abc import Mapping
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
from ..reports.config import ReportsConfig
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


def _fmt_money(v: float) -> str:
    return f"{v:,.2f} ₴".replace(",", " ")


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


def _render_totals_section(facts: dict) -> str | None:
    totals = _safe_get(facts, ["totals"], {}) or {}

    real_spend = float(totals.get("real_spend_total_uah", 0.0))
    spend = float(totals.get("spend_total_uah", 0.0))
    income = float(totals.get("income_total_uah", 0.0))
    tr_in = float(totals.get("transfer_in_total_uah", 0.0))
    tr_out = float(totals.get("transfer_out_total_uah", 0.0))

    summary_lines = [
        f"💸 Реальні витрати: *{md_escape(_fmt_money(real_spend))}*",
        f"🧾 Всі списання: {md_escape(_fmt_money(spend))}",
        f"💰 Надходження: {md_escape(_fmt_money(income))}",
        f"🔁 Перекази: +{md_escape(_fmt_money(tr_in))} / -{md_escape(_fmt_money(tr_out))}",
    ]
    return templates.section("Факти", summary_lines)


def _render_breakdowns_section(facts: dict) -> str | None:
    parts: list[str] = []

    top_named = facts.get("top_categories_named_real_spend", []) or []
    if top_named:
        items: list[str] = []
        for i, row in enumerate(top_named[:5], start=1):
            cat = md_escape(str(row.get("category", "—")))
            amt = float(row.get("amount_uah", 0.0))
            items.append(f"{i}. {cat} — {md_escape(_fmt_money(amt))}")
        parts.append(templates.section("Топ категорій", items))

    top_merchants = facts.get("top_merchants_real_spend", []) or []
    if top_merchants:
        items2: list[str] = []
        for i, row in enumerate(top_merchants[:5], start=1):
            m = md_escape(str(row.get("merchant", "—")))
            amt = float(row.get("amount_uah", 0.0))
            items2.append(f"{i}. {m} — {md_escape(_fmt_money(amt))}")
        parts.append(templates.section("Топ мерчантів", items2))

    deep_categories_block = _render_categories_deep_block(facts)
    if deep_categories_block:
        parts.append(deep_categories_block)

    if not parts:
        return None
    return "\n\n".join(parts).strip()


def _render_compare_section(facts: dict) -> str | None:
    comparison = facts.get("comparison")
    if not isinstance(comparison, dict):
        return None

    totals_cmp = comparison.get("totals", {})
    delta = totals_cmp.get("delta", {}) if isinstance(totals_cmp, dict) else {}
    pct = totals_cmp.get("pct_change", {}) if isinstance(totals_cmp, dict) else {}

    d_real = delta.get("real_spend_total_uah")
    p_real = pct.get("real_spend_total_uah")

    if d_real is None:
        return None

    d_real_f = float(d_real)
    sign = "+" if d_real_f >= 0 else ""
    pct_txt = "—" if p_real is None else f"{float(p_real):+.2f}%"

    cmp_lines: list[str] = [
        f"Реальні витрати: {md_escape(sign + _fmt_money(d_real_f))} ({md_escape(pct_txt)})"
    ]

    cat_cmp = comparison.get("categories", {})
    if isinstance(cat_cmp, dict) and cat_cmp:
        items3: list[tuple[str, float, float | None]] = []
        for k, v in cat_cmp.items():
            if not isinstance(v, dict):
                continue
            items3.append((str(k), float(v.get("delta_uah", 0.0)), v.get("pct_change")))
        items3.sort(key=lambda x: abs(x[1]), reverse=True)

        for k, dlt, pctv in items3[:5]:
            sign2 = "+" if dlt >= 0 else ""
            pct_txt2 = "—" if pctv is None else f"{float(pctv):+.2f}%"
            cmp_lines.append(
                f"{md_escape(k)}: {md_escape(sign2 + _fmt_money(dlt))} ({md_escape(pct_txt2)})"
            )

    return templates.section("Порівняння з попереднім періодом", cmp_lines)


def _render_facts_block_by_config(facts: dict, enabled: set[str]) -> str:
    parts: list[str] = []

    if "totals" in enabled:
        sec = _render_totals_section(facts)
        if sec:
            parts.append(sec)

    if "breakdowns" in enabled:
        sec2 = _render_breakdowns_section(facts)
        if sec2:
            parts.append(sec2)

    if "compare_baseline" in enabled:
        sec3 = _render_compare_section(facts)
        if sec3:
            parts.append(sec3)

    return "\n\n".join(parts).strip()


def _render_trends_block(trends: dict) -> str | None:
    if not isinstance(trends, dict):
        return None

    growing = trends.get("growing") or []
    declining = trends.get("declining") or []

    if not growing and not declining:
        return None

    lines: list[str] = []
    lines.append("*Тренди (7 днів vs попередні 7):*")

    def fmt_item(x: dict) -> str:
        label = md_escape(str(x.get("label", "—")))
        delta = float(x.get("delta_uah", 0.0))
        pct = x.get("pct")
        sign = "+" if delta > 0 else ""
        pct_part = f" ({sign}{int(pct)}%)" if isinstance(pct, (int, float)) else ""
        return f"• {label} {sign}{md_escape(_fmt_money(delta))}{pct_part}"

    if growing:
        lines.append("")
        lines.append("📈 *Зростання:*")
        for x in growing[:3]:
            lines.append(fmt_item(x))

    if declining:
        lines.append("")
        lines.append("📉 *Падіння:*")
        for x in declining[:3]:
            lines.append(fmt_item(x))

    return "\n".join(lines).strip()


def _render_categories_deep_block(facts: dict) -> str | None:
    categories = facts.get("categories_real_spend") or {}
    shares = facts.get("category_shares_real_spend") or {}

    if not isinstance(categories, dict) or not categories:
        return None

    cmp_categories = _safe_get(facts, ["comparison", "categories"], {})
    if not isinstance(cmp_categories, dict):
        cmp_categories = {}

    rows: list[tuple[str, float, float, float | None, float | None]] = []
    for cat, amt in categories.items():
        if cat is None:
            continue
        cat_s = str(cat)
        cur = float(amt or 0.0)
        share = float(shares.get(cat_s, 0.0) or 0.0)

        delta: float | None = None
        pct: float | None = None
        if cat_s in cmp_categories and isinstance(cmp_categories.get(cat_s), dict):
            v = cmp_categories[cat_s]
            delta = float(v.get("delta_uah", 0.0))
            pct_v = v.get("pct_change")
            pct = None if pct_v is None else float(pct_v)

        rows.append((cat_s, cur, share, delta, pct))

    rows.sort(key=lambda x: x[1], reverse=True)
    top_by_spend = rows[:7]

    spend_lines: list[str] = []
    spend_lines.append("*За часткою витрат:*")
    for cat, cur, share, delta, pct in top_by_spend:
        base = f"• {md_escape(cat)} — {md_escape(_fmt_money(cur))} ({md_escape(f'{share:.1f}%')})"
        if delta is None:
            spend_lines.append(base)
            continue

        sign = "+" if delta >= 0 else ""
        pct_txt = "—" if pct is None else f"{pct:+.2f}%"
        spend_lines.append(
            f"{base} | Δ {md_escape(sign + _fmt_money(delta))} ({md_escape(pct_txt)})"
        )

    movers_lines: list[str] = []
    movers = [x for x in rows if x[3] is not None and abs(float(x[3] or 0.0)) >= 1.0]
    movers.sort(key=lambda x: abs(float(x[3] or 0.0)), reverse=True)
    movers = movers[:5]

    if movers:
        movers_lines.append("")
        movers_lines.append("*Топ зміни vs попередній період:*")
        for cat, _, _, delta, pct in movers:
            d = float(delta or 0.0)
            sign = "+" if d >= 0 else ""
            pct_txt = "—" if pct is None else f"{float(pct):+.2f}%"
            movers_lines.append(
                f"• {md_escape(cat)}: Δ {md_escape(sign + _fmt_money(d))} ({md_escape(pct_txt)})"
            )

    return templates.section("Категорії детально", [*spend_lines, *movers_lines])


_ANOMALY_REASON_TEXT: dict[str, str] = {
    "first_time_large": "вперше велика сума за період",
    "spike_vs_median": "сплеск відносно типової (медіани)",
}


def _render_anomalies_block(facts: dict) -> str | None:
    raw = facts.get("anomalies")
    items: list[dict] = []

    if isinstance(raw, list):
        items = [x for x in raw if isinstance(x, dict)]
    elif isinstance(raw, Mapping):
        v = raw.get("items")
        if isinstance(v, list):
            items = [x for x in v if isinstance(x, dict)]

    if not items:
        return None

    lines: list[str] = []
    for i, a in enumerate(items[:5], start=1):
        label = md_escape(str(a.get("label", "—")))
        last_uah = float(a.get("last_day_uah", 0.0) or 0.0)
        base_uah = float(a.get("baseline_median_uah", 0.0) or 0.0)

        reason = str(a.get("reason", "") or "").strip()
        reason_txt = _ANOMALY_REASON_TEXT.get(reason, reason if reason else "аномалія")

        lines.append(
            f"{i}. {label} — *{md_escape(_fmt_money(last_uah))}* "
            f"(звично ~ {md_escape(_fmt_money(base_uah))}) · {md_escape(reason_txt)}"
        )

    return templates.section("Аномалії", lines)


def _render_refunds_block(facts: dict) -> str | None:
    r = facts.get("refunds") or {}
    if not isinstance(r, dict):
        return None

    count = int(r.get("count") or 0)
    if count <= 0:
        return None

    total = float(r.get("total_uah") or 0.0)
    items = r.get("items") or []
    if not isinstance(items, list):
        items = []

    if count <= 1:
        lines = [f"• Виявлено повернення: *{md_escape(_fmt_money(total))}*"]
        return templates.section("Повернення", lines)

    lines: list[str] = []
    lines.append(f"• Виявлено повернень: *{count}* на суму *{md_escape(_fmt_money(total))}*")

    top = items[:3]
    if top:
        lines.append("")
        lines.append("Топ:")
        for it in top:
            if not isinstance(it, dict):
                continue
            merchant = md_escape(str(it.get("merchant") or "—"))
            amt = float(it.get("amount_uah") or 0.0)
            lines.append(f"• {merchant} — {md_escape(_fmt_money(amt))}")

    return templates.section("Повернення", lines)


def _render_whatif_block(facts: dict) -> str | None:
    whatifs = facts.get("whatif_suggestions") or []
    if not isinstance(whatifs, list) or not whatifs:
        return None

    lines: list[str] = []
    lines.append("*What-if (можлива економія):*")

    for w in whatifs[:2]:
        title = md_escape(str(w.get("title", "—")))
        base = float(w.get("monthly_spend_uah", 0.0))
        scenarios = w.get("scenarios") or []

        parts: list[str] = []
        if isinstance(scenarios, list):
            for s in scenarios[:2]:
                pct = int(s.get("pct", 0))
                sav = float(s.get("monthly_savings_uah", 0.0))
                parts.append(f"-{pct}% → ~{md_escape(_fmt_money(sav))}/міс")

        tail = "; ".join(parts) if parts else "—"
        lines.append(f"• {title} (зараз ~{md_escape(_fmt_money(base))}/міс): {tail}")

    return "\n".join(lines).strip()


def _render_ai_block(ai_block: str | None) -> str | None:
    if not ai_block:
        return None
    return f"🤖 *AI інсайти:*\n{ai_block.strip()}"


def _period_to_cfg_period(period: str) -> str:
    if period == "today":
        return "daily"
    if period == "week":
        return "weekly"
    if period == "month":
        return "monthly"
    return period


def _render_report_for_user(
    reports_store: ReportsStore,
    tg_id: int,
    period: str,
    facts: dict,
    *,
    ai_block: str | None = None,
) -> str:
    cfg: ReportsConfig = reports_store.load(tg_id)
    cfg_period = _period_to_cfg_period(period)
    enabled = set(cfg.get_enabled_blocks(cfg_period))

    title_map = {"today": "Сьогодні", "week": "Останні 7 днів", "month": "Останні 30 днів"}
    title = title_map.get(period, period)

    header = f"📊 {md_escape(title)}"

    facts_block = _render_facts_block_by_config(facts, enabled)

    trends_block = None
    if "trends" in enabled:
        trends_block = _render_trends_block(facts.get("trends") or {})

    anomalies_block = None
    if "anomalies" in enabled:
        anomalies_block = _render_anomalies_block(facts)

    whatif_block = None
    if "what_if" in enabled:
        whatif_block = _render_whatif_block(facts)

    refunds_block = _render_refunds_block(facts) if "totals" in enabled else None
    insight_block = _render_ai_block(ai_block)

    return templates.report_layout(
        header=header,
        facts_block=facts_block,
        trends_block=trends_block,
        anomalies_block=anomalies_block,
        whatif_block=whatif_block,
        insight_block=insight_block,
        refunds_block=refunds_block,
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
