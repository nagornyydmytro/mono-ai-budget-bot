from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..config import load_settings
from ..logging_setup import setup_logging
from ..storage.report_store import ReportStore
from ..storage.user_store import UserStore


# --- Markdown (NOT MarkdownV2) escaping for dynamic text ---
# In Telegram Markdown, these chars can break formatting if they appear in user/merchant/category strings.
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

    # кнопки не парсяться як Markdown, але текст кнопок ми все одно робимо простим і без форматування
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
    from ..analytics.compare import compare_categories, compare_totals
    from ..analytics.compute import compute_facts
    from ..analytics.from_monobank import rows_from_statement
    from ..core.time_ranges import previous_period, range_month, range_today, range_week
    from ..monobank import MonobankClient

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

    store.save(cfg.telegram_user_id, period, current_facts)


def build_ai_block(summary: str, insights: list[str], next_step: str) -> str:
    lines: list[str] = []
    lines.append(f"• {md_escape(summary)}")
    lines.append("")
    lines.append("*Рекомендації:*")
    for s in insights[:7]:
        lines.append(f"• {md_escape(s)}")
    lines.append("")
    lines.append("*Наступний крок (7 днів):*")
    lines.append(f"• {md_escape(next_step)}")
    return "\n".join(lines)


async def main() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)

    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    # Telegram "Markdown" (not V2) so *bold* works and parentheses/arrows won't explode parsing.
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode="Markdown"),
    )

    dp = Dispatcher()
    store = ReportStore()
    users = UserStore()

    logger = logging.getLogger("mono_ai_budget_bot.bot")
    
    from .scheduler import create_scheduler, start_jobs
    scheduler = create_scheduler(logger)
    loop=asyncio.get_running_loop()
    start_jobs(
        scheduler,
        loop=loop,
        bot=bot,
        users=users,
        report_store=store,
        refresh_period_for_user=refresh_period_for_user,
        render_report_text=render_report,
        logger=logger,
    )

    @dp.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        tg_id = message.from_user.id if message.from_user else None
        if tg_id is None:
            return
        users.save(tg_id, chat_id=message.chat.id)
        text = (
            "Привіт! Я mono-ai-budget-bot 🤖\n\n"
            "*Команди:*\n"
            "• /connect <mono_token> — підключити Monobank\n"
            "• /accounts — вибір карток для аналізу\n"
            "• /refresh today|week|month|all — оновити дані\n\n"
            "*Звіти:*\n"
            "• /today\n"
            "• /week\n"
            "• /month\n\n"
            "*AI (on-demand):*\n"
            "• /week ai — звіт + AI інсайти\n"
            "• /today ai\n"
            "• /month ai\n\n"
            "*Статус:*\n"
            "• /status\n"
            "• /help\n"
        )
        await message.answer(text, parse_mode=None)

    @dp.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        await message.answer(
            "*Як користуватись:*\n"
            "1) /connect <mono_token>\n"
            "2) /accounts (вибери картки)\n"
            "3) /refresh week (онови дані)\n"
            "4) /week (звіт)\n"
            "5) /week ai (звіт + AI)\n", parse_mode=None
        )

    @dp.message(Command("connect"))
    async def cmd_connect(message: Message) -> None:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            await message.answer(
                "🔐 *Підключення Monobank*\n\n"
                "Надішли команду так:\n"
                "/connect <mono_token>\n\n"
                "Токен зберігається локально на твоєму комп'ютері (не комітиться в репозиторій).", parse_mode=None
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
            "• /accounts — вибір карток\n"
            "• /refresh week — оновити дані\n"
            "• /status — перевірити статус"
        )

    @dp.message(Command("status"))
    async def cmd_status(message: Message) -> None:
        lines = ["*Статус:*"]

        tg_id = message.from_user.id if message.from_user else None
        cfg = users.load(tg_id) if tg_id is not None else None

        if cfg is None:
            lines.append("🔐 Monobank: не підключено")
            lines.append("Підключи: /connect <mono_token>")
        else:
            # token mask may contain '*' which is markdown special, escape it
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
            await message.answer("🔐 Спочатку підключи Monobank: /connect <mono_token>")
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
        if query.message:
            await query.message.edit_text(
                "✅ Збережено!\n\n"
                f"Вибрано карток: *{count}*\n"
                "Далі:\n"
                "• /refresh week — оновити дані\n"
                "• /week — звіт\n"
                "• /week ai — звіт + AI\n"
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
            await message.answer("Спочатку підключи: /connect <mono_token>")
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
            await message.answer(f"❌ Помилка оновлення: {md_escape(str(e))}")
            return

        await message.answer("✅ Готово! Дані оновлено.\n\nМожеш дивитись: /today /week /month")

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
                await message.answer("🤖 Генерую AI інсайти…")
                try:
                    from ..llm.openai_client import OpenAIClient

                    client = OpenAIClient(api_key=settings.openai_api_key, model=settings.openai_model)
                    try:
                        res = client.generate_report(stored.facts, period_label=period_label)
                    finally:
                        client.close()

                    ai_block = build_ai_block(res.summary, res.insights, res.next_step)
                except Exception as e:
                    await message.answer(f"❌ AI помилка: {md_escape(str(e))}")

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

    logger.info("Starting Telegram bot polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())