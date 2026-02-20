from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.markdown import hcode
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..config import load_settings
from ..logging_setup import setup_logging
from ..storage.report_store import ReportStore
from ..storage.user_store import UserStore


def _fmt_money(v: float) -> str:
    return f"{v:,.2f} ₴".replace(",", " ")

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

def _safe_get(d: dict, path: list[str], default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def render_report(period: str, stored: dict) -> str:
    totals = _safe_get(stored, ["totals"], {}) or {}
    comparison = stored.get("comparison")

    real_spend = float(totals.get("real_spend_total_uah", 0.0))
    spend = float(totals.get("spend_total_uah", 0.0))
    income = float(totals.get("income_total_uah", 0.0))
    tr_in = float(totals.get("transfer_in_total_uah", 0.0))
    tr_out = float(totals.get("transfer_out_total_uah", 0.0))

    title_map = {"today": "Сьогодні", "week": "Останні 7 днів", "month": "Останні 30 днів"}
    title = title_map.get(period, period)

    lines: list[str] = []
    lines.append(f"*📊 {title}*")
    lines.append("")
    lines.append(f"💸 Реальні витрати (без переказів):* {_fmt_money(real_spend)}*")
    lines.append(f"🧾 Всі списання (cash out): {_fmt_money(spend)}")
    lines.append(f"💰 Надходження (cash in): {_fmt_money(income)}")
    lines.append(f"🔁 Перекази: +{_fmt_money(tr_in)} / -{_fmt_money(tr_out)}")
    lines.append("")

    # Top categories (named)
    top_named = stored.get("top_categories_named_real_spend", []) or []
    if top_named:
        lines.append("*Топ категорій (реальні витрати):*")
        for i, row in enumerate(top_named[:5], start=1):
            cat = row.get("category", "—")
            amt = float(row.get("amount_uah", 0.0))
            lines.append(f"{i}. {cat}: {_fmt_money(amt)}")
        lines.append("")

    # Top merchants
    top_merchants = stored.get("top_merchants_real_spend", []) or []
    if top_merchants:
        lines.append("*Топ мерчантів (реальні витрати):*")
        for i, row in enumerate(top_merchants[:5], start=1):
            m = row.get("merchant", "—")
            amt = float(row.get("amount_uah", 0.0))
            lines.append(f"{i}. {m}: {_fmt_money(amt)}")
        lines.append("")

    # Comparison (week/month)
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
            lines.append(f"• Реальні витрати: {sign}{_fmt_money(float(d_real))} ({pct_txt})")
            lines.append("")

            # Category deltas (top changes)
            cat_cmp = comparison.get("categories", {})
            if isinstance(cat_cmp, dict) and cat_cmp:
                # sort by abs delta
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
                    lines.append(f"• {k}: {sign2}{_fmt_money(dlt)} ({pct_txt2})")
                lines.append("")

    return "\n".join(lines).strip()

async def refresh_period_for_user(period: str, cfg, store: ReportStore) -> None:
    from ..core.time_ranges import range_month, range_today, range_week, previous_period
    from ..monobank import MonobankClient
    from ..analytics.from_monobank import rows_from_statement
    from ..analytics.compute import compute_facts
    from ..analytics.compare import compare_totals, compare_categories

    # choose range
    if period == "today":
        current_dr = range_today()
        duration_days = 1
    elif period == "week":
        current_dr = range_week()
        duration_days = 7
    else:
        current_dr = range_month()
        duration_days = 30

    current_from, current_to = current_dr.to_unix()

    mb = MonobankClient(token=cfg.mono_token)
    try:
        info = mb.client_info()
        if cfg.selected_account_ids:
            account_ids = cfg.selected_account_ids
        else:
            account_ids = [a.id for a in info.accounts]

        rows = []
        for aid in account_ids:
            items = mb.statement(account=aid, date_from=current_from, date_to=current_to)
            rows.extend(rows_from_statement(aid, items))
        current_facts = compute_facts(rows)

        if period in ("week", "month"):
            prev_dr = previous_period(current_dr, days=duration_days)
            prev_from, prev_to = prev_dr.to_unix()

            prev_rows = []
            for aid in account_ids:
                prev_items = mb.statement(account=aid, date_from=prev_from, date_to=prev_to)
                prev_rows.extend(rows_from_statement(aid, prev_items))
            prev_facts = compute_facts(prev_rows)

            current_facts["comparison"] = {
                "prev_period": {
                    "dt_from": prev_dr.dt_from.isoformat(),
                    "dt_to": prev_dr.dt_to.isoformat(),
                    "totals": prev_facts["totals"],
                    "categories_real_spend": prev_facts.get("categories_real_spend", {}),
                },
                "totals": compare_totals(current_facts, prev_facts),
                "categories": compare_categories(
                    current_facts.get("categories_real_spend", {}),
                    prev_facts.get("categories_real_spend", {}),
                ),
            }
    finally:
        mb.close()

    store.save(period, current_facts)

def render_accounts_screen(accounts: list[dict], selected_ids: set[str]) -> tuple[str, InlineKeyboardBuilder]:
    """
    accounts: list of dicts with keys: id, currencyCode, maskedPan
    """
    lines: list[str] = []
    lines.append("🧾 <b>Вибір карток для аналізу</b>")
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

    # action row
    kb.button(text="🧹 Очистити вибір", callback_data="acc_clear")
    kb.button(text="✅ Готово", callback_data="acc_done")
    kb.adjust(1, 2)

    return "\n".join(lines), kb

async def main() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)

    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher()
    store = ReportStore()
    users = UserStore()

    logger = logging.getLogger("mono_ai_budget_bot.bot")

    @dp.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        text = (
            "Привіт! Я mono-ai-budget-bot 🤖\n\n"
            "Команди:\n"
            "• /today — звіт за сьогодні\n"
            "• /week — звіт за останні 7 днів\n"
            "• /month — звіт за останні 30 днів\n"
            "• /status — статус кешу\n"
            "• /help — допомога\n\n"
            "Поки що звіти беруться з локального кешу. Оновлення даних зробимо наступним кроком."
        )
        await message.answer(text)

    @dp.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        await message.answer(
            "ℹ️ Допомога\n\n"
            "Звіти:\n"
            "• /today\n"
            "• /week\n"
            "• /month\n\n"
            "Статус:\n"
            "• /status — покаже, коли востаннє оновлювались facts.\n"
        )

    @dp.message(Command("connect"))
    async def cmd_connect(message: Message) -> None:
        """
        Usage:
          /connect <mono_token>
        """
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            await message.answer(
                "🔐 Підключення Monobank\n\n"
                "Надішли команду так:\n"
                f"{hcode('/connect <mono_token>')}\n\n"
                "Токен зберігається локально на твоєму комп'ютері (не комітиться в репозиторій)."
            )
            return

        mono_token = parts[1].strip()
        tg_id = message.from_user.id if message.from_user else None
        if tg_id is None:
            await message.answer("Не зміг визначити твій Telegram user id.")
            return

        users.save(tg_id, mono_token=mono_token, selected_account_ids=[])
        await message.answer(
            "✅ Monobank токен збережено.\n\n"
            "Далі:\n"
            "• /status — перевірити статус\n"
            "• (далі додамо) /accounts — вибір карток для аналізу"
        )

    @dp.message(Command("status"))
    async def cmd_status(message: Message) -> None:
        parts = ["*Статус:*"]

        tg_id = message.from_user.id if message.from_user else None
        cfg = users.load(tg_id) if tg_id is not None else None

        if cfg is None:
            parts.append("🔐 Monobank: не підключено")
            parts.append(f"Підключи: {hcode('/connect <mono_token>')}")
        else:
            parts.append(f"🔐 Monobank: підключено ({hcode(_mask_secret(cfg.mono_token))})")
            parts.append(f"📌 Вибрані картки: {len(cfg.selected_account_ids)} (налаштуємо в /accounts)")

        parts.append("")
        parts.append("*Статус кешу:*")
        for p in ("today", "week", "month"):
            stored = store.load(p)
            if stored is None:
                parts.append(f"• {p}: немає (зроби refresh-facts)")
            else:
                ts = datetime.fromtimestamp(stored.generated_at).isoformat(timespec="seconds")
                parts.append(f"• {p}: {hcode(ts)}")

        await message.answer("\n".join(parts))

    async def _send_period_report(message: Message, period: str) -> None:
        stored = store.load(period)
        if stored is None:
            await message.answer(
                f"Немає кешованого звіту для {period}.\n"
                f"Запусти локально: {hcode(f'monobot refresh-facts --period {period}')}"
            )
            return

        text = render_report(period, stored.facts)
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

    @dp.message(Command("accounts"))
    async def cmd_accounts(message: Message) -> None:
        tg_id = message.from_user.id if message.from_user else None
        if tg_id is None:
            await message.answer("Не зміг визначити твій Telegram user id.")
            return

        cfg = users.load(tg_id)
        if cfg is None:
            await message.answer(
                "🔐 Спочатку підключи Monobank токен:\n"
                f"{hcode('/connect <mono_token>')}"
            )
            return

        # Fetch accounts from Monobank (client-info)
        from ..monobank import MonobankClient

        mb = MonobankClient(token=cfg.mono_token)
        try:
            info = mb.client_info()
        finally:
            mb.close()

        accounts = []
        for a in info.accounts:
            accounts.append(
                {
                    "id": a.id,
                    "currencyCode": a.currencyCode,
                    "maskedPan": a.maskedPan,
                }
            )

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

        # Re-render screen (re-fetch accounts to keep UI consistent)
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
        if query.message:
            await query.message.edit_text(
                "✅ Збережено!\n\n"
                f"Вибрано карток: <b>{count}</b>\n"
                "Далі:\n"
                "• /status — перевірити\n"
                "• /week — звіт\n"
            )
        await query.answer("Готово")

    @dp.message(Command("refresh"))
    async def cmd_refresh(message: Message) -> None:
        tg_id = message.from_user.id if message.from_user else None
        if tg_id is None:
            await message.answer("Не зміг визначити твій Telegram user id.")
            return

        cfg = users.load(tg_id)
        if cfg is None:
            await message.answer(f"Спочатку підключи: {hcode('/connect <mono_token>')}")
            return

        parts = (message.text or "").split()
        period = parts[1].strip().lower() if len(parts) > 1 else "week"

        if period not in ("today", "week", "month", "all"):
            await message.answer("Використання: /refresh today|week|month|all")
            return

        await message.answer("⏳ Оновлюю дані… (може зайняти час через ліміти Mono API)")

        try:
            if period == "all":
                for p in ("today", "week", "month"):
                    await refresh_period_for_user(p, cfg, store)
            else:
                await refresh_period_for_user(period, cfg, store)
        except Exception as e:
            await message.answer(f"❌ Помилка оновлення: {hcode(str(e))}")
            return

        await message.answer("✅ Готово! Дані оновлено.\n\nМожеш дивитись: /today /week /month")

    logger.info("Starting Telegram bot polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())