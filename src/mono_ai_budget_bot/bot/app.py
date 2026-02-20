from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.markdown import hcode

from ..config import load_settings
from ..logging_setup import setup_logging
from ..storage.report_store import ReportStore


def _fmt_money(v: float) -> str:
    return f"{v:,.2f} ₴".replace(",", " ")


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


async def main() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)

    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher()
    store = ReportStore()

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

    @dp.message(Command("status"))
    async def cmd_status(message: Message) -> None:
        parts = ["*Статус кешу:*"]
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

    logger.info("Starting Telegram bot polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())