from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from mono_ai_budget_bot.analytics.compute import compute_facts
from mono_ai_budget_bot.analytics.enrich import enrich_period_facts
from mono_ai_budget_bot.analytics.from_ledger import rows_from_ledger
from mono_ai_budget_bot.bot.clarify import build_nlq_clarify_keyboard
from mono_ai_budget_bot.core.time_ranges import range_today
from mono_ai_budget_bot.monobank import MonobankClient
from mono_ai_budget_bot.nlq import memory_store
from mono_ai_budget_bot.nlq.pipeline import handle_nlq
from mono_ai_budget_bot.nlq.types import NLQRequest
from mono_ai_budget_bot.storage.report_store import ReportStore
from mono_ai_budget_bot.storage.tx_store import TxStore

from ..analytics.profile import build_user_profile
from ..config import load_settings
from ..logging_setup import setup_logging
from ..storage.profile_store import ProfileStore
from ..storage.user_store import UserConfig, UserStore
from . import templates

if TYPE_CHECKING:
    from aiogram.types import CallbackQuery, Message
    from aiogram.utils.keyboard import InlineKeyboardBuilder


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


def render_accounts_screen(
    accounts: list[dict], selected_ids: set[str]
) -> tuple[str, InlineKeyboardBuilder]:
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

    return "\n".join(lines).strip(), kb


def build_main_menu_keyboard():
    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="🔐 Connect", callback_data="menu_connect"),
        InlineKeyboardButton(text="🧾 Accounts", callback_data="menu_accounts"),
    )
    kb.row(
        InlineKeyboardButton(text="📊 Week", callback_data="menu_week"),
        InlineKeyboardButton(text="📅 Month", callback_data="menu_month"),
    )
    kb.row(
        InlineKeyboardButton(text="🔄 Refresh week", callback_data="menu_refresh_week"),
        InlineKeyboardButton(text="🔎 Status", callback_data="menu_status"),
    )
    kb.row(
        InlineKeyboardButton(text="📘 Help", callback_data="menu_help"),
    )
    return kb


def _render_facts_block(facts: dict) -> str:
    totals = _safe_get(facts, ["totals"], {}) or {}
    comparison = facts.get("comparison")

    real_spend = float(totals.get("real_spend_total_uah", 0.0))
    spend = float(totals.get("spend_total_uah", 0.0))
    income = float(totals.get("income_total_uah", 0.0))
    tr_in = float(totals.get("transfer_in_total_uah", 0.0))
    tr_out = float(totals.get("transfer_out_total_uah", 0.0))

    parts: list[str] = []

    summary_lines = [
        f"💸 Реальні витрати: *{md_escape(_fmt_money(real_spend))}*",
        f"🧾 Всі списання: {md_escape(_fmt_money(spend))}",
        f"💰 Надходження: {md_escape(_fmt_money(income))}",
        f"🔁 Перекази: +{md_escape(_fmt_money(tr_in))} / -{md_escape(_fmt_money(tr_out))}",
    ]
    parts.append(templates.section("Факти", summary_lines))

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

    if isinstance(comparison, dict):
        totals_cmp = comparison.get("totals", {})
        delta = totals_cmp.get("delta", {}) if isinstance(totals_cmp, dict) else {}
        pct = totals_cmp.get("pct_change", {}) if isinstance(totals_cmp, dict) else {}

        d_real = delta.get("real_spend_total_uah")
        p_real = pct.get("real_spend_total_uah")

        if d_real is not None:
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

            parts.append(templates.section("Порівняння з попереднім періодом", cmp_lines))

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


def render_report(period: str, facts: dict, ai_block: str | None = None) -> str:
    title_map = {"today": "Сьогодні", "week": "Останні 7 днів", "month": "Останні 30 днів"}
    title = title_map.get(period, period)

    header = f"📊 {md_escape(title)}"
    facts_block = _render_facts_block(facts)
    deep_categories_block = _render_categories_deep_block(facts)
    if deep_categories_block:
        facts_block = (facts_block + "\n\n" + deep_categories_block).strip()
    trends_block = _render_trends_block(facts.get("trends") or {})
    anomalies_block = _render_anomalies_block(facts)
    insight_block = _render_ai_block(ai_block)
    whatif_block = _render_whatif_block(facts)

    return templates.report_layout(
        header=header,
        facts_block=facts_block,
        trends_block=trends_block,
        anomalies_block=anomalies_block,
        whatif_block=whatif_block,
        insight_block=insight_block,
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
    profile_store.save(tg_id, profile)

    for period, days_back in (("week", 7), ("month", 30)):
        now_ts = int(time.time())
        ts_from = now_ts - (2 * days_back + 1) * 24 * 60 * 60
        ts_to = now_ts

        records = tx_store.load_range(tg_id, account_ids, ts_from, ts_to)

        current_facts = enrich_period_facts(records, days_back=days_back, now_ts=now_ts)

        store.save(tg_id, period, current_facts)


async def main() -> None:
    from aiogram import Bot, Dispatcher, F
    from aiogram.client.default import DefaultBotProperties
    from aiogram.filters import Command

    settings = load_settings()
    setup_logging(settings.log_level)
    profile_store = ProfileStore(Path(".cache") / "profiles")

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
        render_report_text=render_report,
        logger=logger,
        sync_user_ledger=sync_user_ledger,
        recompute_reports_for_user=lambda tg_id, account_ids: _compute_and_cache_reports_for_user(
            tg_id, account_ids, profile_store
        ),
    )

    @dp.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        tg_id = message.from_user.id if message.from_user else None
        if tg_id is None:
            return

        users.save(tg_id, chat_id=message.chat.id)
        cfg = users.load(tg_id)

        kb = build_main_menu_keyboard()

        text = templates.start_message()
        if cfg is not None and cfg.mono_token:
            text = "\n".join(
                [
                    text,
                    "",
                    templates.success("Monobank підключено."),
                    templates.onboarding_connected_next_steps(),
                ]
            ).strip()

        await message.answer(text, reply_markup=kb.as_markup())

    @dp.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        kb = build_main_menu_keyboard()
        await message.answer(templates.help_message(), reply_markup=kb.as_markup())

    @dp.message(Command("connect"))
    async def cmd_connect(message: Message) -> None:
        parts = (message.text or "").split(maxsplit=1)

        if len(parts) < 2 or not parts[1].strip():
            await message.answer(templates.connect_instructions())
            return

        mono_token = parts[1].strip()

        if len(mono_token) < 20:
            await message.answer(templates.connect_validation_error())
            return

        tg_id = message.from_user.id if message.from_user else None
        if tg_id is None:
            await message.answer(templates.error("Не зміг визначити твій Telegram user id."))
            return

        await message.answer("🔍 Перевіряю токен через Monobank API… (read-only)")

        try:
            mb = MonobankClient(token=mono_token)
            try:
                mb.client_info()
            finally:
                mb.close()
        except Exception as e:
            mapped = _map_monobank_error(e)
            await message.answer(mapped or templates.error("Помилка перевірки токена."))
            return

        users.save(tg_id, mono_token=mono_token, selected_account_ids=[])

        kb = build_main_menu_keyboard()
        await message.answer(templates.connect_success_confirm())
        await message.answer(
            "\n".join(
                [
                    templates.onboarding_connected_next_steps(),
                    "",
                    "Можеш натиснути 🧾 Accounts прямо в меню нижче.",
                ]
            ).strip(),
            reply_markup=kb.as_markup(),
        )

    @dp.message(Command("status"))
    async def cmd_status(message: Message) -> None:
        tg_id = message.from_user.id if message.from_user else None
        cfg = users.load(tg_id) if tg_id is not None else None

        parts: list[str] = []
        parts.append("🔎 *Статус*")
        parts.append("")

        if cfg is None:
            parts.append(
                templates.section(
                    "Monobank",
                    [
                        "🔐 Не підключено (зроби `/connect`)",
                        "📌 Вибрані картки: —",
                    ],
                )
            )
            parts.append("")
            parts.append(templates.section("Кеш звітів", []))
            parts.append("• today: —")
            parts.append("• week: —")
            parts.append("• month: —")
            await message.answer("\n".join(parts).strip())
            return

        masked = (
            md_escape(_mask_secret(cfg.mono_token)) if getattr(cfg, "mono_token", None) else "—"
        )
        selected_cnt = len(cfg.selected_account_ids or [])

        parts.append(
            templates.section(
                "Monobank",
                [
                    f"🔐 Підключено ({masked})",
                    f"📌 Вибрані картки: {selected_cnt}",
                    "• якщо кешу нема — зроби `/refresh week` або натисни 🔄 Refresh week",
                ],
            )
        )

        parts.append("")
        parts.append(templates.section("Кеш звітів", []))

        for p in ("today", "week", "month"):
            stored = store.load(cfg.telegram_user_id, p)
            if stored is None:
                parts.append(f"• {p}: немає (зроби `/refresh {p}`)")
            else:
                ts = datetime.fromtimestamp(stored.generated_at).isoformat(timespec="seconds")
                parts.append(f"• {p}: {md_escape(ts)}")

        await message.answer("\n".join(parts).strip())

    @dp.message(Command("accounts"))
    async def cmd_accounts(message: Message) -> None:
        tg_id = message.from_user.id if message.from_user else None
        if tg_id is None:
            await message.answer(templates.error("Не зміг визначити твій Telegram user id."))
            return

        cfg = users.load(tg_id)
        if cfg is None or not cfg.mono_token:
            await message.answer(templates.err_not_connected())
            return

        mb = MonobankClient(token=cfg.mono_token)
        try:
            info = mb.client_info()
        except Exception as e:
            msg = _map_monobank_error(e)
            await message.answer(msg or templates.error(f"Помилка Monobank: {md_escape(str(e))}"))
            return
        finally:
            mb.close()

        accounts = [
            {"id": a.id, "currencyCode": a.currencyCode, "maskedPan": a.maskedPan}
            for a in info.accounts
        ]
        selected_ids = set(cfg.selected_account_ids or [])
        text, kb = render_accounts_screen(accounts, selected_ids)
        await message.answer(text, reply_markup=kb.as_markup())

    @dp.callback_query(lambda c: c.data and c.data.startswith("acc_toggle:"))
    async def cb_toggle_account(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Помилка: нема user id", show_alert=True)
            return

        cfg = users.load(tg_id)
        if cfg is None:
            await query.answer("Спочатку /connect", show_alert=True)
            return

        acc_id = (query.data or "").split("acc_toggle:", 1)[1].strip()
        selected = set(cfg.selected_account_ids or [])

        if acc_id in selected:
            selected.remove(acc_id)
        else:
            selected.add(acc_id)

        _save_selected_accounts(users, tg_id, sorted(selected))

        mb = MonobankClient(token=cfg.mono_token)
        try:
            info = mb.client_info()
        except Exception as e:
            msg = _map_monobank_error(e)
            await query.answer(msg or "Помилка Monobank", show_alert=True)
            return
        finally:
            mb.close()

        accounts = [
            {"id": a.id, "currencyCode": a.currencyCode, "maskedPan": a.maskedPan}
            for a in info.accounts
        ]
        text, kb = render_accounts_screen(accounts, set(selected))

        if query.message:
            await query.message.edit_text(text, reply_markup=kb.as_markup())
        await query.answer("Ок")

    @dp.callback_query(lambda c: c.data == "acc_clear")
    async def cb_clear_accounts(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Помилка: нема user id", show_alert=True)
            return

        cfg = users.load(tg_id)
        if cfg is None:
            await query.answer("Спочатку підключи /connect", show_alert=True)
            return

        _save_selected_accounts(users, tg_id, [])

        mb = MonobankClient(token=cfg.mono_token)
        try:
            info = mb.client_info()
        finally:
            mb.close()

        accounts = [
            {"id": a.id, "currencyCode": a.currencyCode, "maskedPan": a.maskedPan}
            for a in info.accounts
        ]
        text, kb = render_accounts_screen(accounts, set())

        if query.message:
            await query.message.edit_text(text, reply_markup=kb.as_markup())
        await query.answer("Очищено")

    @dp.callback_query(lambda c: c.data == "acc_done")
    async def cb_done_accounts(query: CallbackQuery) -> None:
        from aiogram.types import InlineKeyboardButton
        from aiogram.utils.keyboard import InlineKeyboardBuilder

        tg_id = query.from_user.id if query.from_user else None
        cfg = users.load(tg_id) if tg_id is not None else None

        count = len(cfg.selected_account_ids) if cfg else 0
        if count <= 0:
            await query.answer("Спочатку вибери хоча б 1 картку", show_alert=True)
            return

        kb = InlineKeyboardBuilder()
        kb.row(
            InlineKeyboardButton(text="📥 Bootstrap 1 місяць", callback_data="boot_30"),
        )
        kb.row(
            InlineKeyboardButton(text="📥 Bootstrap 3 місяці", callback_data="boot_90"),
        )
        kb.row(
            InlineKeyboardButton(text="➡️ Skip", callback_data="boot_skip"),
        )

        if query.message:
            await query.message.edit_text(
                "\n".join(
                    [
                        templates.accounts_after_done(),
                        "",
                        f"Вибрано карток: {count}",
                    ]
                ).strip(),
                reply_markup=kb.as_markup(),
            )
        await query.answer("Done")

    @dp.callback_query(lambda c: c.data == "menu_connect")
    async def cb_menu_connect(query: CallbackQuery) -> None:
        if query.message:
            await query.message.answer(templates.connect_instructions())
        await query.answer()

    @dp.callback_query(lambda c: c.data == "menu_help")
    async def cb_menu_help(query: CallbackQuery) -> None:
        if query.message:
            kb = build_main_menu_keyboard()
            await query.message.answer(templates.help_message(), reply_markup=kb.as_markup())
        await query.answer()

    @dp.callback_query(lambda c: c.data == "menu_week")
    async def cb_menu_week(query: CallbackQuery) -> None:
        if query.message:
            await _send_period_report(query.message, "week")
        await query.answer()

    @dp.callback_query(lambda c: c.data == "menu_month")
    async def cb_menu_month(query: CallbackQuery) -> None:
        if query.message:
            await _send_period_report(query.message, "month")
        await query.answer()

    @dp.callback_query(lambda c: c.data == "menu_status")
    async def cb_menu_status(query: CallbackQuery) -> None:
        if query.message:
            await cmd_status(query.message)
        await query.answer()

    @dp.callback_query(lambda c: c.data == "menu_accounts")
    async def cb_menu_accounts(query: CallbackQuery) -> None:
        if query.message:
            await cmd_accounts(query.message)
        await query.answer()

    @dp.callback_query(lambda c: c.data == "menu_refresh_week")
    async def cb_menu_refresh_week(query: CallbackQuery) -> None:
        if query.message:
            fake_msg = query.message
            fake_msg.text = "/refresh week"
            await cmd_refresh(fake_msg)
        await query.answer()

    @dp.callback_query(lambda c: c.data and c.data.startswith("nlq_pick:"))
    async def cb_nlq_pick(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає user id", show_alert=True)
            return

        idx_raw = (query.data or "").split("nlq_pick:", 1)[1].strip()
        if not idx_raw.isdigit():
            await query.answer("Некоректний вибір", show_alert=True)
            return

        try:
            resp = handle_nlq(
                NLQRequest(
                    telegram_user_id=tg_id,
                    text=str(int(idx_raw)),
                    now_ts=int(time.time()),
                )
            )
        except Exception:
            await query.answer("Помилка", show_alert=True)
            return

        if query.message and resp.result:
            await query.message.answer(resp.result.text)
            await query.answer("Ок")
            return

        await query.answer("Ок")

    @dp.callback_query(lambda c: c.data == "nlq_other")
    async def cb_nlq_other(query: CallbackQuery) -> None:
        if query.message:
            await query.message.answer(
                "Ок. Напиши в чат мерчанта/отримувача як у виписці (можна частину назви)."
            )
        await query.answer("Ок")

    @dp.callback_query(lambda c: c.data == "nlq_cancel")
    async def cb_nlq_cancel(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає user id", show_alert=True)
            return
        memory_store.pop_pending_action(tg_id)
        if query.message:
            await query.message.answer("Ок, скасовано.")
        await query.answer("Скасовано")

    @dp.callback_query(lambda c: c.data in ("boot_30", "boot_90", "boot_skip"))
    async def cb_bootstrap(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        cfg = users.load(tg_id)
        if cfg is None or not cfg.mono_token:
            await query.answer("Спочатку /connect", show_alert=True)
            return

        account_ids = list(cfg.selected_account_ids or [])
        if not account_ids:
            await query.answer("Спочатку вибери картки: /accounts", show_alert=True)
            return

        if query.data == "boot_skip":
            if query.message:
                await query.message.edit_text(
                    "Ок! Можеш зробити `/refresh week` або одразу `/week` (якщо кеш уже є)."
                )
            await query.answer("Пропущено")
            return

        days = 30 if query.data == "boot_30" else 90

        if query.message:
            await query.message.edit_text(
                "\n".join(
                    [
                        f"📥 Запустив завантаження історії за *{days} днів* у фоні…",
                        "Це може зайняти час через ліміти Monobank API.",
                        "",
                        "Я напишу, коли буде готово ✅",
                    ]
                ).strip()
            )
        await query.answer("Старт")

        chat_id = query.message.chat.id if query.message else None
        token = cfg.mono_token

        async def job() -> None:
            try:
                async with user_locks[tg_id]:
                    from ..monobank.sync import sync_accounts_ledger

                    def _run_sync() -> object:
                        mb = MonobankClient(token=token)
                        try:
                            return sync_accounts_ledger(
                                mb=mb,
                                tx_store=tx_store,
                                telegram_user_id=tg_id,
                                account_ids=account_ids,
                                days_back=days,
                            )
                        finally:
                            mb.close()

                    res = await asyncio.to_thread(_run_sync)

                    await _compute_and_cache_reports_for_user(tg_id, account_ids, profile_store)

                    if chat_id is not None:
                        await bot.send_message(
                            chat_id,
                            "\n".join(
                                [
                                    templates.success("Готово!"),
                                    "",
                                    f"Карток: {res.accounts}",
                                    f"Запитів до API: {res.fetched_requests}",
                                    f"Додано транзакцій: {res.appended}",
                                    "",
                                    "Тепер можеш:",
                                    "• /today",
                                    "• /week",
                                    "• /month",
                                    "• /week ai",
                                ]
                            ).strip(),
                        )
            except Exception as e:
                if chat_id is not None:
                    msg = _map_monobank_error(e)
                    await bot.send_message(
                        chat_id,
                        templates.error(f"Помилка bootstrap: {md_escape(msg or str(e))}"),
                    )

        asyncio.create_task(job())

    @dp.message(Command("refresh"))
    async def cmd_refresh(message: Message) -> None:
        tg_id = message.from_user.id if message.from_user else None
        if tg_id is None:
            await message.answer(templates.error("Не зміг визначити твій Telegram user id."))
            return

        cfg = users.load(tg_id)
        if cfg is None or not cfg.mono_token:
            await message.answer(templates.err_not_connected())
            return

        account_ids = list(cfg.selected_account_ids or [])
        if not account_ids:
            await message.answer(templates.err_no_accounts_selected())
            return

        parts = (message.text or "").split()
        arg = parts[1].strip().lower() if len(parts) > 1 else "week"

        if arg not in ("today", "week", "month", "all"):
            await message.answer(templates.warning("Використання: `/refresh today|week|month|all`"))
            return

        if arg == "today":
            days_back = 2
        elif arg == "week":
            days_back = 8
        elif arg == "month":
            days_back = 32
        else:
            days_back = 90

        await message.answer(
            "\n".join(
                [
                    f"⏳ Запустив оновлення за ~{days_back} днів у фоні…",
                    "Я напишу, коли буде готово ✅",
                ]
            ).strip()
        )

        chat_id = message.chat.id
        token = cfg.mono_token

        async def job() -> None:
            try:
                async with user_locks[tg_id]:
                    from ..monobank.sync import sync_accounts_ledger

                    def _run_sync() -> object:
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

                    res = await asyncio.to_thread(_run_sync)

                    await _compute_and_cache_reports_for_user(tg_id, account_ids, profile_store)

                    await bot.send_message(
                        chat_id,
                        "\n".join(
                            [
                                templates.success("Оновлено!"),
                                f"Карток: {res.accounts}",
                                f"Запитів до API: {res.fetched_requests}",
                                f"Додано транзакцій: {res.appended}",
                                "",
                                "Можеш дивитись: /today /week /month",
                            ]
                        ).strip(),
                    )
            except Exception as e:
                msg = _map_monobank_error(e)
                await bot.send_message(
                    chat_id,
                    templates.error(f"Помилка оновлення: {md_escape(msg or str(e))}"),
                )

        asyncio.create_task(job())

    @dp.message(Command("aliases"))
    async def cmd_aliases(message: Message) -> None:
        tg_id = message.from_user.id if message.from_user else None
        if tg_id is None:
            await message.answer(templates.error("Не зміг визначити user id."))
            return

        mem = memory_store.load_memory(tg_id)
        merchant_aliases = mem.get("merchant_aliases", {})
        recipient_aliases = mem.get("recipient_aliases", {})

        if not merchant_aliases and not recipient_aliases:
            await message.answer(templates.aliases_empty_message())
            return

        await message.answer(templates.aliases_list_message(merchant_aliases, recipient_aliases))

    @dp.message(Command("aliases_clear"))
    async def cmd_aliases_clear(message: Message) -> None:
        tg_id = message.from_user.id if message.from_user else None
        if tg_id is None:
            await message.answer(templates.error("Не зміг визначити user id."))
            return

        memory_store.save_memory(
            tg_id,
            {"merchant_aliases": {}, "recipient_aliases": {}},
        )
        await message.answer(templates.aliases_cleared_message())

    async def _send_period_report(message: Message, period: str) -> None:
        want_ai = " ai" in (" " + (message.text or "").lower() + " ")

        tg_id = message.from_user.id if message.from_user else None
        if tg_id is None:
            await message.answer(templates.error("Не зміг визначити твій Telegram user id."))
            return

        cfg = users.load(tg_id)
        if cfg is None or not cfg.mono_token:
            await message.answer(templates.err_not_connected())
            return
        if not cfg.selected_account_ids:
            await message.answer(templates.err_no_accounts_selected())
            return

        stored = store.load(tg_id, period)
        if stored is None:
            await message.answer(templates.err_no_ledger(period))
            return

        ai_block = None
        if want_ai:
            if not settings.openai_api_key:
                await message.answer(
                    templates.warning("OPENAI_API_KEY не задано в .env — AI недоступний.")
                )
            else:
                period_label = {
                    "today": "Сьогодні",
                    "week": "Останні 7 днів",
                    "month": "Останні 30 днів",
                }.get(period, period)

                await message.answer("🤖 Генерую AI інсайти…")

                try:
                    from ..llm.openai_client import OpenAIClient

                    client = OpenAIClient(
                        api_key=settings.openai_api_key, model=settings.openai_model
                    )
                    try:
                        profile = profile_store.load(tg_id) or {}
                        facts_with_profile = {"period_facts": stored.facts, "user_profile": profile}
                        res = client.generate_report(facts_with_profile, period_label=period_label)
                    finally:
                        client.close()

                    ai_block = build_ai_block(
                        res.report.summary,
                        res.report.changes,
                        res.report.recs,
                        res.report.next_step,
                    )
                except Exception as e:
                    logger.warning("LLM unavailable, sending facts-only. err=%s", e)
                    await message.answer(_map_llm_error(e))
                    ai_block = None

        text = render_report(period, stored.facts, ai_block=ai_block)
        await message.answer(text)

    @dp.message(Command("today"))
    async def cmd_today(message: Message) -> None:
        await _send_period_report(message, "today")

    @dp.message(Command("week"))
    async def cmd_week(message: Message) -> None:
        await _send_period_report(message, "week")

    @dp.message(Command("month"))
    async def cmd_month(message: Message) -> None:
        await _send_period_report(message, "month")

    @dp.message(Command("autojobs"))
    async def cmd_autojobs(message: Message) -> None:
        tg_id = message.from_user.id
        cfg = users.load(tg_id)
        if cfg is None:
            await message.answer(
                templates.warning("Спочатку підключи Monobank: `/connect <token>`")
            )
            return

        parts = (message.text or "").split()
        action = parts[1].lower() if len(parts) > 1 else "status"

        if action == "on":
            users.save(tg_id, autojobs_enabled=True)
            await message.answer(templates.success("Автозвіти увімкнено"))
            return
        if action == "off":
            users.save(tg_id, autojobs_enabled=False)
            await message.answer(templates.success("Автозвіти вимкнено"))
            return

        cfg2 = users.load(tg_id)
        await message.answer(f"Автозвіти: {'ON' if cfg2 and cfg2.autojobs_enabled else 'OFF'}")

    @dp.message(F.text & ~F.text.startswith("/"))
    async def handle_plain_text(message: Message) -> None:
        user_id = message.from_user.id
        text_lower = (message.text or "").strip().lower()

        if text_lower == "cancel":
            memory_store.pop_pending_intent(user_id)
            await message.answer(templates.recipient_followup_cancelled())
            return

        cfg = users.load(user_id)
        if cfg is None or not cfg.mono_token:
            await message.answer(templates.err_not_connected())
            return
        if not cfg.selected_account_ids:
            await message.answer(templates.err_no_accounts_selected())
            return

        stored = store.load(user_id, "week")
        if stored is None:
            await message.answer(templates.err_no_ledger("week"))
            return

        try:
            resp = handle_nlq(
                NLQRequest(
                    telegram_user_id=user_id,
                    text=message.text,
                    now_ts=int(time.time()),
                )
            )

            if resp.result:
                mem = memory_store.load_memory(user_id)
                kind = mem.get("pending_kind")
                opts = mem.get("pending_options")

                if kind in {"recipient", "category_alias"} and isinstance(opts, list) and opts:
                    kb = build_nlq_clarify_keyboard(
                        opts, limit=8, include_other=True, include_cancel=True
                    )
                    await message.answer(resp.result.text, reply_markup=kb)
                    return

                await message.answer(resp.result.text)
                return

            await message.answer(templates.unknown_nlq_message())
        except Exception:
            await message.answer(templates.nlq_failed_message())

    logger.info("Starting Telegram bot polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
