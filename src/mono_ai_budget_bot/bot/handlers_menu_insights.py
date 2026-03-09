from __future__ import annotations

from collections.abc import Callable

from aiogram.types import CallbackQuery

from . import templates
from .handlers_common import HandlerContext
from .menu_flow import render_menu_screen, render_placeholder_screen
from .ui import (
    build_back_keyboard,
    build_insights_forecast_keyboard,
    build_insights_guidance_keyboard,
    build_insights_menu_keyboard,
    build_insights_whatif_keyboard,
)


def register_insights_handlers(
    dp,
    *,
    ctx: HandlerContext,
    load_month_facts: Callable[[HandlerContext, int], dict | None],
    render_insight_body: Callable[[str, dict], str | None],
    render_whatif_pct_body: Callable[[dict, int], str | None],
    render_forecast_projection_body: Callable[[dict, str], str | None],
    render_explain_body: Callable[[dict], str | None],
) -> None:
    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data == "menu:insights")
    async def cb_menu_insights(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(
            query,
            require_token=True,
            require_accounts=True,
            require_ledger=True,
        ):
            return

        await render_menu_screen(
            query,
            text=templates.menu_insights_message(),
            reply_markup=build_insights_menu_keyboard(),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str)
        and c.data
        in {
            "menu:insights:trends",
            "menu:insights:anomalies",
            "menu:insights:whatif",
            "menu:insights:forecast",
            "menu:insights:explain",
        }
    )
    async def cb_menu_insight_sections(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(
            query,
            require_token=True,
            require_accounts=True,
            require_ledger=True,
        ):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        label_map = {
            "menu:insights:trends": "📈 *Trends*",
            "menu:insights:anomalies": "🚨 *Anomalies*",
            "menu:insights:whatif": "🧮 *What-if*",
            "menu:insights:forecast": "🔮 *Forecast*",
            "menu:insights:explain": "🧠 *Explain*",
        }
        section_label = label_map.get(str(query.data or ""), "✨ *Insights*")

        facts = load_month_facts(ctx, tg_id)
        if not isinstance(facts, dict) or not facts:
            await render_menu_screen(
                query,
                text=templates.menu_insights_needs_data_message(section_label),
                reply_markup=build_insights_guidance_keyboard(),
            )
            return

        insight_key = str(query.data or "")

        if insight_key == "menu:insights:whatif":
            await render_menu_screen(
                query,
                text=templates.menu_insights_whatif_message(),
                reply_markup=build_insights_whatif_keyboard(),
            )
            return

        if insight_key == "menu:insights:forecast":
            await render_menu_screen(
                query,
                text=templates.menu_insights_forecast_message(),
                reply_markup=build_insights_forecast_keyboard(),
            )
            return

        if insight_key == "menu:insights:explain":
            body = render_explain_body(facts)
            if not body:
                await render_menu_screen(
                    query,
                    text=templates.menu_insights_needs_data_message("🧠 *Explain*"),
                    reply_markup=build_insights_guidance_keyboard(),
                )
                return

            await render_menu_screen(
                query,
                text=templates.menu_insight_result_message(
                    "🧠 *Explain*",
                    "Пояснення росту/падіння на основі вже підготовлених deterministic facts.",
                    body,
                ),
                reply_markup=build_back_keyboard("menu:insights"),
            )
            return

        rendered = render_insight_body(insight_key, facts)
        if rendered:
            intro_map = {
                "menu:insights:trends": "Детермінований зріз на основі вже підготовлених trends facts за місячним контекстом.",
                "menu:insights:anomalies": "Детермінований зріз на основі вже підготовлених anomaly facts без вигадування нових даних.",
            }
            await render_menu_screen(
                query,
                text=templates.menu_insight_result_message(
                    section_label,
                    intro_map.get(str(query.data or ""), "Детермінований insights-зріз."),
                    rendered,
                ),
                reply_markup=build_back_keyboard("menu:insights"),
            )
            return

        if str(query.data or "") in {"menu:insights:trends", "menu:insights:anomalies"}:
            await render_menu_screen(
                query,
                text=templates.menu_insights_needs_data_message(section_label),
                reply_markup=build_insights_guidance_keyboard(),
            )
            return

        await render_placeholder_screen(
            query,
            text=templates.menu_insight_placeholder_message(section_label),
            reply_markup=build_back_keyboard("menu:insights"),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str)
        and c.data in {"menu:insights:whatif:pct:10", "menu:insights:whatif:pct:20"}
    )
    async def cb_menu_insight_whatif_variants(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(
            query,
            require_token=True,
            require_accounts=True,
            require_ledger=True,
        ):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        facts = load_month_facts(ctx, tg_id)
        if not isinstance(facts, dict) or not facts:
            await render_menu_screen(
                query,
                text=templates.menu_insights_needs_data_message("🧮 *What-if*"),
                reply_markup=build_insights_guidance_keyboard(),
            )
            return

        pct = 10 if str(query.data or "").endswith(":10") else 20
        body = render_whatif_pct_body(facts, pct)
        if not body:
            await render_menu_screen(
                query,
                text=templates.menu_insights_needs_data_message("🧮 *What-if*"),
                reply_markup=build_insights_guidance_keyboard(),
            )
            return

        await render_menu_screen(
            query,
            text=templates.menu_insight_result_message(
                "🧮 *What-if*",
                f"Сценарій -{pct}% на основі вже порахованих what-if facts.",
                body,
            ),
            reply_markup=build_back_keyboard("menu:insights:whatif"),
        )

    @dp.callback_query(
        lambda c: isinstance(c.data, str)
        and c.data in {"menu:insights:forecast:view:spend", "menu:insights:forecast:view:income"}
    )
    async def cb_menu_insight_forecast_variants(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(
            query,
            require_token=True,
            require_accounts=True,
            require_ledger=True,
        ):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        facts = load_month_facts(ctx, tg_id)
        if not isinstance(facts, dict) or not facts:
            await render_menu_screen(
                query,
                text=templates.menu_insights_needs_data_message("🔮 *Forecast*"),
                reply_markup=build_insights_guidance_keyboard(),
            )
            return

        metric = "income" if str(query.data or "").endswith(":income") else "spend"
        body = render_forecast_projection_body(facts, metric)
        if not body:
            await render_menu_screen(
                query,
                text=templates.menu_insights_needs_data_message("🔮 *Forecast*"),
                reply_markup=build_insights_guidance_keyboard(),
            )
            return

        intro = (
            "Детермінована проєкція доходів на основі вже підготовлених totals facts."
            if metric == "income"
            else "Детермінована проєкція витрат на основі вже підготовлених totals facts."
        )
        await render_menu_screen(
            query,
            text=templates.menu_insight_result_message("🔮 *Forecast*", intro, body),
            reply_markup=build_back_keyboard("menu:insights:forecast"),
        )
