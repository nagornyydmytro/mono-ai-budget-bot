from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..config import load_settings
from ..logging_setup import setup_logging
from ..storage.user_store import UserStore

from mono_ai_budget_bot.monobank import MonobankClient
from mono_ai_budget_bot.monobank.sync import sync_accounts_ledger
from mono_ai_budget_bot.analytics.from_ledger import rows_from_ledger
from mono_ai_budget_bot.analytics.compute import compute_facts
from mono_ai_budget_bot.core.time_ranges import range_today, range_week, range_month

from mono_ai_budget_bot.storage.report_store import ReportStore
from mono_ai_budget_bot.storage.tx_store import TxStore

from mono_ai_budget_bot.nlq.router import parse_nlq_intent
from mono_ai_budget_bot.nlq.executor import execute_intent

from mono_ai_budget_bot.analytics.period_report import build_period_report_from_ledger

from ..analytics.profile import build_user_profile
from ..storage.profile_store import ProfileStore

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


def render_accounts_screen(accounts: list[dict], selected_ids: set[str]) -> tuple[str, InlineKeyboardBuilder]:
    lines: list[str] = []
    lines.append("🧾 *Вибір карток для аналізу*")
    lines.append("")
    lines.append("Обери картки, які враховувати у звітах (інші ігноруються).")
    lines.append("")

    kb = InlineKeyboardBuilder()

    for acc in accounts:
        acc_id = acc["id"]
        masked = " / ".join(acc.get("maskedPan") or []) or "без картки"
        cur = str(acc.get("currencyCode", ""))
        mark = "✅" if acc_id in selected_ids else "⬜️"
        text = f"{mark} {masked} ({cur})"
        kb.button(text=text, callback_data=f"acc_toggle:{acc_id}")

    kb.adjust(1)
    kb.button(text="🧹 Очистити вибір", callback_data="acc_clear")
    kb.button(text="✅ Готово", callback_data="acc_done")
    kb.adjust(1, 2)

    return "\n".join(lines), kb


def render_report(period: str, facts: dict, ai_block: str | None = None) -> str:
    totals = _safe_get(facts, ["totals"], {}) or {}
    comparison = facts.get("comparison")

    real_spend = float(totals.get("real_spend_total_uah", 0.0))
    spend = float(totals.get("spend_total_uah", 0.0))
    income = float(totals.get("income_total_uah", 0.0))
    tr_in = float(totals.get("transfer_in_total_uah", 0.0))
    tr_out = float(totals.get("transfer_out_total_uah", 0.0))

    title_map = {"today": "Сьогодні", "week": "Останні 7 днів", "month": "Останні 30 днів"}
    title = title_map.get(period, period)

    lines: list[str] = []
    lines.append(f"📊 *{md_escape(title)}*")
    lines.append("")
    lines.append(f"💸 Реальні витрати (без переказів): *{md_escape(_fmt_money(real_spend))}*")
    lines.append(f"🧾 Всі списання (cash out): {md_escape(_fmt_money(spend))}")
    lines.append(f"💰 Надходження (cash in): {md_escape(_fmt_money(income))}")
    lines.append(f"🔁 Перекази: +{md_escape(_fmt_money(tr_in))} / -{md_escape(_fmt_money(tr_out))}")
    lines.append("")

    top_named = facts.get("top_categories_named_real_spend", []) or []
    if top_named:
        lines.append("*Топ категорій (реальні витрати):*")
        for i, row in enumerate(top_named[:5], start=1):
            cat = md_escape(str(row.get("category", "—")))
            amt = float(row.get("amount_uah", 0.0))
            lines.append(f"{i}. {cat}: {md_escape(_fmt_money(amt))}")
        lines.append("")

    top_merchants = facts.get("top_merchants_real_spend", []) or []
    if top_merchants:
        lines.append("*Топ мерчантів (реальні витрати):*")
        for i, row in enumerate(top_merchants[:5], start=1):
            m = md_escape(str(row.get("merchant", "—")))
            amt = float(row.get("amount_uah", 0.0))
            lines.append(f"{i}. {m}: {md_escape(_fmt_money(amt))}")
        lines.append("")

    if isinstance(comparison, dict):
        totals_cmp = comparison.get("totals", {})
        delta = totals_cmp.get("delta", {}) if isinstance(totals_cmp, dict) else {}
        pct = totals_cmp.get("pct_change", {}) if isinstance(totals_cmp, dict) else {}

        d_real = delta.get("real_spend_total_uah")
        p_real = pct.get("real_spend_total_uah")

        if d_real is not None:
            sign = "+" if float(d_real) >= 0 else ""
            pct_txt = "—" if p_real is None else f"{p_real:+.2f}%"
            lines.append("*Порівняння з попереднім періодом:*")
            lines.append(
                f"• Реальні витрати: {md_escape(sign + _fmt_money(float(d_real)))} ({md_escape(pct_txt)})"
            )
            lines.append("")

            cat_cmp = comparison.get("categories", {})
            if isinstance(cat_cmp, dict) and cat_cmp:
                items = []
                for k, v in cat_cmp.items():
                    if not isinstance(v, dict):
                        continue
                    delta_uah = float(v.get("delta_uah", 0.0))
                    items.append((k, delta_uah, v.get("pct_change")))
                items.sort(key=lambda x: abs(x[1]), reverse=True)

                lines.append("*Найбільші зміни по категоріях:*")
                for k, dlt, pctv in items[:5]:
                    sign2 = "+" if dlt >= 0 else ""
                    pct_txt2 = "—" if pctv is None else f"{pctv:+.2f}%"
                    lines.append(
                        f"• {md_escape(str(k))}: {md_escape(sign2 + _fmt_money(dlt))} ({md_escape(pct_txt2)})"
                    )
                lines.append("")

    if ai_block:
        lines.append("🤖 *AI інсайти:*")
        lines.append(ai_block.strip())
        lines.append("")

    return "\n".join(lines).strip()

async def refresh_period_for_user(period: str, cfg, store: ReportStore) -> None:
    """
    Ledger-based refresh (no direct Monobank calls).
    Assumes ledger was synced earlier by sync job / refresh command.

    period: "today" | "week" | "month"
    """
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

    report = build_period_report_from_ledger(records, days_back=days_back, now_ts=now_ts)

    current_facts = report["current"]

    current_facts["comparison"] = {
        "prev_period": {
            "dt_from": report["period"]["previous"]["start_iso_utc"],
            "dt_to": report["period"]["previous"]["end_iso_utc"],
            "totals": report["previous"].get("totals", {}),
            "categories_real_spend": report["previous"].get("categories_real_spend", {}),
        },
        "totals": report["compare"]["totals"],
        "categories": report["compare"]["categories_real_spend"],
    }

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
        report = build_period_report_from_ledger(records, days_back=days_back, now_ts=now_ts)

        current_facts = report["current"]
        current_facts["comparison"] = {
            "prev_period": {
                "dt_from": report["period"]["previous"]["start_iso_utc"],
                "dt_to": report["period"]["previous"]["end_iso_utc"],
                "totals": report["previous"].get("totals", {}),
                "categories_real_spend": report["previous"].get("categories_real_spend", {}),
            },
            "totals": report["compare"]["totals"],
            "categories": report["compare"]["categories_real_spend"],
        }

        store.save(tg_id, period, current_facts)

async def main() -> None:
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

    from collections import defaultdict
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
    loop=asyncio.get_running_loop()

    start_jobs(
        scheduler,
        loop=loop,
        bot=bot,
        users=users,
        report_store=store,
        render_report_text=render_report,
        logger=logger,
        sync_user_ledger=sync_user_ledger,
        recompute_reports_for_user=lambda tg_id, account_ids: _compute_and_cache_reports_for_user(tg_id, account_ids, profile_store)
    )

    @dp.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        tg_id = message.from_user.id if message.from_user else None
        if tg_id is None:
            return

        users.save(tg_id, chat_id=message.chat.id)

        text = (
            "👋 Mono AI Budget Bot\n\n"
            "Я допоможу аналізувати твої витрати Monobank з AI-інсайтами.\n\n"
            "🔌 Підключення:\n"
            "/connect — додати Monobank token\n"
            "Отримати токен: https://api.monobank.ua/index.html\n\n"
            "📊 Звіти:\n"
            "/today\n"
            "/week\n"
            "/month\n\n"
            "⚙️ Дані зберігаються локально (папка .cache).\n"
            "Деталі — /help"
        )

        await message.answer(text, parse_mode=None)

    @dp.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        await message.answer(
            "📘 Команди:\n\n"
            "🔌 Підключення:\n"
            "/connect — додати Monobank token\n"
            "/status — перевірити доступ до API\n"
            "/accounts — вибрати рахунки\n"
            "/refresh — синхронізувати ledger\n\n"
            "📊 Звіти:\n"
            "/today — витрати за сьогодні\n"
            "/week — останні 7 днів + порівняння\n"
            "/month — останні 30 днів + порівняння\n\n"
            "🔒 Privacy:\n"
            "Токен і ledger зберігаються локально (.cache).\n"
            "Щоб видалити всі дані — видали папку .cache.\n\n"
            "Monobank API: https://api.monobank.ua/index.html",
            parse_mode=None,
        )

    @dp.message(Command("connect"))
    async def cmd_connect(message: Message) -> None:
        parts = (message.text or "").split(maxsplit=1)

        if len(parts) < 2 or not parts[1].strip():
            await message.answer(
                "🔐 Підключення Monobank\n\n"
                "1) Перейди на сторінку:\n"
                "https://api.monobank.ua/index.html\n"
                "2) Авторизуйся через Monobank\n"
                "3) Створи Personal API token\n"
                "4) Надішли його так:\n"
                "/connect YOUR_TOKEN\n\n"
                "Токен зберігається локально і не публікується.",
                parse_mode=None,
            )
            return

        mono_token = parts[1].strip()
        tg_id = message.from_user.id if message.from_user else None

        if tg_id is None:
            await message.answer("Не зміг визначити твій Telegram user id.")
            return

        users.save(tg_id, mono_token=mono_token, selected_account_ids=[])

        await message.answer(
            "✅ Monobank token збережено.\n\n"
            "Далі:\n"
            "• /accounts — вибір карток\n"
            "Після вибору карток бот запропонує завантажити історію за 1 або 3 місяці."
        )

    @dp.message(Command("status"))
    async def cmd_status(message: Message) -> None:
        lines = ["*Статус:*"]

        tg_id = message.from_user.id if message.from_user else None
        cfg = users.load(tg_id) if tg_id is not None else None

        if cfg is None:
            lines.append("🔐 Monobank: не підключено")
            lines.append("Підключи: /connect <monobank token>")
        else:
            masked = md_escape(_mask_secret(cfg.mono_token))
            lines.append(f"🔐 Monobank: підключено ({masked})")
            lines.append(f"📌 Вибрані картки: {len(cfg.selected_account_ids)}")

        lines.append("")
        lines.append("*Статус кешу:*")
        for p in ("today", "week", "month"):
            stored = store.load(cfg.telegram_user_id,p)
            if stored is None:
                lines.append(f"• {p}: немає (зроби /refresh {p})")
            else:
                ts = datetime.fromtimestamp(stored.generated_at).isoformat(timespec="seconds")
                lines.append(f"• {p}: {md_escape(ts)}")

        await message.answer("\n".join(lines))

    @dp.message(Command("accounts"))
    async def cmd_accounts(message: Message) -> None:
        tg_id = message.from_user.id if message.from_user else None
        if tg_id is None:
            await message.answer("Не зміг визначити твій Telegram user id.")
            return

        cfg = users.load(tg_id)
        if cfg is None:
            await message.answer("🔐 Спочатку підключи Monobank: /connect <monobank token>")
            return

        from ..monobank import MonobankClient

        mb = MonobankClient(token=cfg.mono_token)
        try:
            info = mb.client_info()
        finally:
            mb.close()

        accounts = [{"id": a.id, "currencyCode": a.currencyCode, "maskedPan": a.maskedPan} for a in info.accounts]
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
            await query.answer("Спочатку підключи /connect", show_alert=True)
            return

        acc_id = (query.data or "").split("acc_toggle:", 1)[1].strip()
        selected = set(cfg.selected_account_ids or [])

        if acc_id in selected:
            selected.remove(acc_id)
        else:
            selected.add(acc_id)

        _save_selected_accounts(users, tg_id, sorted(selected))

        from ..monobank import MonobankClient

        mb = MonobankClient(token=cfg.mono_token)
        try:
            info = mb.client_info()
        finally:
            mb.close()

        accounts = [{"id": a.id, "currencyCode": a.currencyCode, "maskedPan": a.maskedPan} for a in info.accounts]
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

        from ..monobank import MonobankClient

        mb = MonobankClient(token=cfg.mono_token)
        try:
            info = mb.client_info()
        finally:
            mb.close()

        accounts = [{"id": a.id, "currencyCode": a.currencyCode, "maskedPan": a.maskedPan} for a in info.accounts]
        text, kb = render_accounts_screen(accounts, set())

        if query.message:
            await query.message.edit_text(text, reply_markup=kb.as_markup())
        await query.answer("Очищено")

    @dp.callback_query(lambda c: c.data == "acc_done")
    async def cb_done_accounts(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        cfg = users.load(tg_id) if tg_id is not None else None

        count = len(cfg.selected_account_ids) if cfg else 0

        kb = InlineKeyboardBuilder()
        kb.row(
            InlineKeyboardButton(text="📥 Завантажити 1 місяць", callback_data="boot_30"),
            InlineKeyboardButton(text="📥 Завантажити 3 місяці", callback_data="boot_90"),
        )
        kb.row(InlineKeyboardButton(text="Пропустити", callback_data="boot_skip"))

        if query.message:
            await query.message.edit_text(
                "✅ Збережено!\n\n"
                f"Вибрано карток: {count}\n\n"
                "Хочеш завантажити історію транзакцій?\n"
                "Після завантаження звіти /today /week /month працюватимуть одразу.\n",
                reply_markup=kb.as_markup(),
                parse_mode=None,
            )
        await query.answer("Готово")

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
                    "Ок! Можеш зробити /refresh week або одразу /week (якщо кеш уже є).",
                    parse_mode=None,
                )
            await query.answer("Пропущено")
            return

        days = 30 if query.data == "boot_30" else 90

        if query.message:
            await query.message.edit_text(
                f"📥 Запустив завантаження історії за {days} днів у фоні… "
                "Це може зайняти час через ліміти Monobank API.\n\n"
                "Я напишу, коли буде готово ✅",
                parse_mode=None,
            )
        await query.answer("Старт")

        chat_id = query.message.chat.id if query.message else None
        token = cfg.mono_token

        async def job() -> None:
            try:
                async with user_locks[tg_id]:
                    from ..monobank import MonobankClient
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
                            "✅ Готово!\n\n"
                            f"Карток: {res.accounts}\n"
                            f"Запитів до API: {res.fetched_requests}\n"
                            f"Додано транзакцій: {res.appended}\n\n"
                            "Тепер можеш:\n"
                            "• /today\n"
                            "• /week\n"
                            "• /month\n"
                            "• /week ai\n",
                            parse_mode=None,
                        )
            except Exception as e:
                if chat_id is not None:
                    await bot.send_message(chat_id, f"❌ Помилка bootstrap: {md_escape(str(e))}", parse_mode=None)

        asyncio.create_task(job())

    @dp.message(Command("refresh"))
    async def cmd_refresh(message: Message) -> None:
        tg_id = message.from_user.id if message.from_user else None
        if tg_id is None:
            await message.answer("Не зміг визначити твій Telegram user id.")
            return

        cfg = users.load(tg_id)
        if cfg is None or not cfg.mono_token:
            await message.answer("Спочатку підключи Monobank: /connect YOUR_TOKEN")
            return

        account_ids = list(cfg.selected_account_ids or [])
        if not account_ids:
            await message.answer("Спочатку вибери картки для аналізу: /accounts")
            return

        parts = (message.text or "").split()
        arg = parts[1].strip().lower() if len(parts) > 1 else "week"

        if arg not in ("today", "week", "month", "all"):
            await message.answer("Використання: /refresh today|week|month|all")
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
            f"⏳ Запустив оновлення за ~{days_back} днів у фоні…\n"
            "Я напишу, коли буде готово ✅",
            parse_mode=None,
        )

        chat_id = message.chat.id
        token = cfg.mono_token

        async def job() -> None:
            try:
                async with user_locks[tg_id]:
                    from ..monobank import MonobankClient
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
                        "✅ Оновлено!\n"
                        f"Карток: {res.accounts}\n"
                        f"Запитів до API: {res.fetched_requests}\n"
                        f"Додано транзакцій: {res.appended}\n\n"
                        "Можеш дивитись: /today /week /month",
                        parse_mode=None,
                    )
            except Exception as e:
                await bot.send_message(chat_id, f"❌ Помилка оновлення: {md_escape(str(e))}", parse_mode=None)

        asyncio.create_task(job())

    async def _send_period_report(message: Message, period: str) -> None:
        want_ai = " ai" in (" " + (message.text or "").lower() + " ")

        tg_id = message.from_user.id if message.from_user else None
        if tg_id is None:
            await message.answer("Не зміг визначити твій Telegram user id.")
            return

        cfg = users.load(tg_id)
        if cfg is None or not cfg.mono_token:
            await message.answer("Спочатку підключи Monobank: /connect <monobank token>")
            return

        stored = store.load(tg_id, period)
        if stored is None:
            await message.answer(f"Немає кешу для {period}. Зроби: /refresh {period}")
            return

        ai_block = None
        if want_ai:
            if not settings.openai_api_key:
                await message.answer("OPENAI_API_KEY не задано в .env — AI недоступний.")
            else:
                period_label = {"today": "Сьогодні", "week": "Останні 7 днів", "month": "Останні 30 днів"}.get(
                    period, period
                )
                if settings.openai_api_key:
                    await message.answer("🤖 Генерую AI інсайти…")
                    try:
                        from ..llm.openai_client import OpenAIClient

                        client = OpenAIClient(api_key=settings.openai_api_key, model=settings.openai_model)
                        try:
                            profile = profile_store.load(tg_id) or {}

                            facts_with_profile = {
                                "period_facts": stored.facts,
                                "user_profile": profile,
                            }

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
            await message.answer("Спочатку підключи Monobank: /connect <mono_token>")
            return

        parts = (message.text or "").split()
        action = parts[1].lower() if len(parts) > 1 else "status"

        if action == "on":
            users.save(tg_id, autojobs_enabled=True)
            await message.answer("✅ Автозвіти увімкнено")
            return
        if action == "off":
            users.save(tg_id, autojobs_enabled=False)
            await message.answer("✅ Автозвіти вимкнено")
            return

        cfg2 = users.load(tg_id)
        await message.answer(f"Автозвіти: {'ON' if cfg2 and cfg2.autojobs_enabled else 'OFF'}")

    @dp.message(F.text & ~F.text.startswith("/"))
    async def handle_plain_text(message: Message) -> None:
        user_id = message.from_user.id

        try:
            intent = parse_nlq_intent(message.text)
            answer = execute_intent(user_id, intent)
            await message.answer(answer)
        except Exception:
            await message.answer("Сталася помилка при обробці запиту.")

    logger.info("Starting Telegram bot polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())