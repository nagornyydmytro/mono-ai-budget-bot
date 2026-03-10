from __future__ import annotations

import time
from datetime import date, datetime, timezone

from aiogram.types import CallbackQuery, Message

from mono_ai_budget_bot.analytics.enrich import enrich_period_facts
from mono_ai_budget_bot.nlq import memory_store
from mono_ai_budget_bot.nlq.types import NLQRequest
from mono_ai_budget_bot.settings.ai_features import (
    ai_feature_enabled,
    normalize_ai_features_settings,
)
from mono_ai_budget_bot.settings.persona import (
    build_persona_prompt_suffix,
    normalize_persona_settings,
)

from . import templates
from .clarify import validate_ok_or_alert
from .errors import map_llm_error
from .handlers_common import HandlerContext
from .report_flow_helpers import build_ai_block, compute_and_cache_reports_for_user
from .ui import (
    build_back_keyboard,
    build_report_mode_keyboard,
    build_reports_custom_calendar_keyboard,
    build_saved_to_root_keyboard,
)


def _parse_iso_day_utc(raw: str) -> tuple[str, int] | None:
    text = str(raw or "").strip()
    try:
        dt = datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        return None
    return dt.strftime("%Y-%m-%d"), int(dt.timestamp())


def _custom_period_kind(day_count: int) -> str:
    if day_count <= 1:
        return "daily"
    if day_count <= 7:
        return "weekly"
    return "monthly"


def _period_label(period: str) -> str:
    return {
        "today": "Today",
        "week": "Last 7 days",
        "month": "Last 30 days",
        "custom": "Custom",
    }.get(period, period)


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    month_index = (year * 12 + (month - 1)) + int(delta)
    next_year = month_index // 12
    next_month = (month_index % 12) + 1
    return next_year, next_month


def _today_iso_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _custom_calendar_text(*, step: str, start_date: str | None = None) -> str:
    if step == "end" and start_date:
        return templates.menu_reports_custom_end_prompt(start_date)
    return templates.menu_reports_custom_start_prompt()


async def _send_custom_calendar(
    query_or_message,
    *,
    tg_id: int,
    step: str,
    year: int,
    month: int,
    start_date: str | None = None,
) -> None:
    text = _custom_calendar_text(step=step, start_date=start_date)
    keyboard = build_reports_custom_calendar_keyboard(
        year=year,
        month=month,
        step=step,
        start_date=start_date,
        today_iso=_today_iso_utc(),
    )
    if hasattr(query_or_message, "message") and getattr(query_or_message, "message", None):
        await query_or_message.message.edit_text(text, reply_markup=keyboard)
        return
    await query_or_message.answer(text, reply_markup=keyboard)


async def _finalize_custom_report(
    message: Message,
    *,
    ctx: HandlerContext,
    user_id: int,
    start_date: str,
    start_ts: int,
    end_date: str,
    end_day_start_ts: int,
    want_ai: bool,
) -> None:
    day_count = ((int(end_day_start_ts) - int(start_ts)) // 86400) + 1
    if day_count > 366:
        await message.answer(
            templates.menu_reports_custom_invalid_range_message(366),
            reply_markup=build_back_keyboard("menu:reports"),
        )
        return

    cfg = ctx.users.load(user_id)
    mem = memory_store.load_memory(user_id)
    if cfg is None or not cfg.mono_token:
        memory_store.pop_pending_manual_mode(user_id)
        mem.pop("reports_custom", None)
        memory_store.save_memory(user_id, mem)
        await message.answer(templates.err_not_connected())
        return

    if not cfg.selected_account_ids:
        memory_store.pop_pending_manual_mode(user_id)
        mem.pop("reports_custom", None)
        memory_store.save_memory(user_id, mem)
        await message.answer(templates.err_no_accounts_selected())
        return

    ctx.sync_onboarding_progress(user_id)
    if not ctx.onboarding_done(user_id):
        await ctx.prompt_finish_onboarding(message)
        return

    end_exclusive_ts = int(end_day_start_ts) + 86400
    lookback_from_ts = end_exclusive_ts - ((2 * day_count + 1) * 86400)

    records = ctx.tx_store.load_range(
        user_id,
        list(cfg.selected_account_ids or []),
        lookback_from_ts,
        end_exclusive_ts,
    )
    facts = enrich_period_facts(
        records,
        days_back=day_count,
        now_ts=end_exclusive_ts,
    )

    cov = ctx.tx_store.aggregated_coverage_window(user_id, list(cfg.selected_account_ids or []))
    if cov is not None and isinstance(facts, dict):
        facts["coverage"] = {
            "coverage_from_ts": int(cov[0]),
            "coverage_to_ts": int(cov[1]),
            "requested_from_ts": int(start_ts),
            "requested_to_ts": int(end_exclusive_ts),
        }

    facts["requested_period_label"] = f"{start_date} → {end_date}"

    kind = _custom_period_kind(day_count)
    period_key = f"custom:{kind}"

    memory_store.pop_pending_manual_mode(user_id)
    mem.pop("pending_manual_mode", None)
    mem.pop("reports_custom", None)
    memory_store.save_memory(user_id, mem)

    await message.answer(templates.menu_reports_custom_building_message(start_date, end_date))

    ai_block = None
    profile = normalize_ai_features_settings(
        normalize_persona_settings(ctx.profile_store.load(user_id) or {})
    )
    if want_ai and not ai_feature_enabled(profile, "report_explanations"):
        await message.answer(templates.ai_feature_disabled_message("AI explanations"))
        want_ai = False

    if want_ai:
        if not ctx.settings.openai_api_key:
            await message.answer(templates.ai_disabled_missing_key_message())
        else:
            await message.answer(templates.ai_insights_progress_message())
            try:
                ai_block = await _build_ai_block_from_facts(
                    ctx=ctx,
                    tg_id=user_id,
                    period_label=facts.get("requested_period_label")
                    or f"{start_date} → {end_date}",
                    facts=facts,
                )
            except Exception as e:
                s = str(e)
                if "429" in s and "Too Many Requests" in s:
                    ctx.logger.info("LLM rate-limited, sending facts-only. err=%s", e)
                else:
                    ctx.logger.warning("LLM unavailable, sending facts-only. err=%s", e)
                await message.answer(map_llm_error(e))

    text = ctx.render_report_for_user(
        user_id,
        period_key,
        facts,
        ai_block=ai_block,
    )
    await message.answer(text, reply_markup=build_saved_to_root_keyboard())


async def _build_ai_block_from_facts(
    *,
    ctx: HandlerContext,
    tg_id: int,
    period_label: str,
    facts: dict,
) -> str | None:
    if not ctx.settings.openai_api_key:
        return None

    from ..llm.openai_client import OpenAIClient

    client = OpenAIClient(api_key=ctx.settings.openai_api_key, model=ctx.settings.openai_model)
    try:
        profile = normalize_ai_features_settings(
            normalize_persona_settings(ctx.profile_store.load(tg_id) or {})
        )
        system = (
            "Ти допомагаєш з персональною фінансовою аналітикою. "
            "Працюй лише на основі переданих фактів. "
            "Не вигадуй дані. "
            "Не давай інвестиційних, медичних або юридичних порад. "
            "Пиши українською, коротко і природно. "
            "Не дублюй блок 'Факти' і не переписуй всі totals без нового висновку. "
            "Не використовуй technical keys, snake_case, key=value, JSON-like fragments. "
            "У summary дай 1–3 речення лише з висновками. "
            "У changes пиши лише нетривіальні зміни vs previous period. "
            "У recs давай 1–3 конкретні дії, прив'язані до фактів, а не загальні фрази. "
            "Якщо великі transfer_in/transfer_out, чітко відрізняй 'всі списання' від 'реальних витрат'. "
            "Якщо uncategorized_real_spend_total_uah суттєвий, прямо скажи, що категорійна картина неповна. "
            "Поверни JSON з полями: summary, changes, recs, next_step. "
            + build_persona_prompt_suffix(profile)
        )
        user = f"Період: {period_label}\nФакти: {facts}\nПрофіль: {profile}"
        res = client.generate_report_v2(system, user)
    finally:
        client.close()

    return build_ai_block(
        res.summary,
        res.changes,
        res.recs,
        res.next_step,
    )


async def handle_reports_custom_manual_input(
    message: Message,
    *,
    ctx: HandlerContext,
    user_id: int,
    text_raw: str,
    now_ts: int,
) -> bool:
    manual = memory_store.get_pending_manual_mode(user_id, now_ts=now_ts)
    expected = str((manual or {}).get("expected") or "").strip()
    if expected not in {"report_custom_start", "report_custom_end"}:
        return False

    parsed = _parse_iso_day_utc(text_raw)
    if parsed is None:
        await message.answer(
            templates.menu_reports_custom_invalid_date_message(),
            reply_markup=build_back_keyboard("menu:reports"),
        )
        return True

    date_label, day_start_ts = parsed
    mem = memory_store.load_memory(user_id)
    reports_custom = mem.get("reports_custom")
    if not isinstance(reports_custom, dict):
        reports_custom = {}

    if expected == "report_custom_start":
        reports_custom["start_date"] = date_label
        reports_custom["start_ts"] = int(day_start_ts)
        mem["reports_custom"] = reports_custom
        memory_store.save_memory(user_id, mem)
        memory_store.set_pending_manual_mode(
            user_id,
            expected="report_custom_end",
            hint="YYYY-MM-DD",
            source="reports_custom",
            ttl_sec=900,
        )
        await message.answer(
            templates.menu_reports_custom_end_prompt(date_label),
            reply_markup=build_back_keyboard("menu:reports"),
        )
        return True

    start_date = str(reports_custom.get("start_date") or "").strip()
    start_ts_raw = reports_custom.get("start_ts")
    try:
        start_ts = int(start_ts_raw)
    except Exception:
        memory_store.set_pending_manual_mode(
            user_id,
            expected="report_custom_start",
            hint="YYYY-MM-DD",
            source="reports_custom",
            ttl_sec=900,
        )
        await message.answer(
            templates.menu_reports_custom_start_prompt(),
            reply_markup=build_back_keyboard("menu:reports"),
        )
        return True

    if day_start_ts < start_ts:
        await message.answer(
            templates.menu_reports_custom_invalid_order_message(start_date, date_label),
            reply_markup=build_back_keyboard("menu:reports"),
        )
        return True

    want_ai = bool(reports_custom.get("want_ai"))
    await _finalize_custom_report(
        message,
        ctx=ctx,
        user_id=user_id,
        start_date=start_date,
        start_ts=int(start_ts),
        end_date=date_label,
        end_day_start_ts=int(day_start_ts),
        want_ai=want_ai,
    )
    return True

    day_count = ((int(day_start_ts) - int(start_ts)) // 86400) + 1
    if day_count > 366:
        await message.answer(
            templates.menu_reports_custom_invalid_range_message(366),
            reply_markup=build_back_keyboard("menu:reports"),
        )
        return True

    cfg = ctx.users.load(user_id)
    if cfg is None or not cfg.mono_token:
        memory_store.pop_pending_manual_mode(user_id)
        mem.pop("reports_custom", None)
        memory_store.save_memory(user_id, mem)
        await message.answer(templates.err_not_connected())
        return True

    if not cfg.selected_account_ids:
        memory_store.pop_pending_manual_mode(user_id)
        mem.pop("reports_custom", None)
        memory_store.save_memory(user_id, mem)
        await message.answer(templates.err_no_accounts_selected())
        return True

    ctx.sync_onboarding_progress(user_id)
    if not ctx.onboarding_done(user_id):
        await ctx.prompt_finish_onboarding(message)
        return True

    end_exclusive_ts = int(day_start_ts) + 86400
    lookback_from_ts = end_exclusive_ts - ((2 * day_count + 1) * 86400)

    records = ctx.tx_store.load_range(
        user_id,
        list(cfg.selected_account_ids or []),
        lookback_from_ts,
        end_exclusive_ts,
    )
    facts = enrich_period_facts(
        records,
        days_back=day_count,
        now_ts=end_exclusive_ts,
    )

    cov = ctx.tx_store.aggregated_coverage_window(user_id, list(cfg.selected_account_ids or []))
    if cov is not None and isinstance(facts, dict):
        facts["coverage"] = {
            "coverage_from_ts": int(cov[0]),
            "coverage_to_ts": int(cov[1]),
            "requested_from_ts": int(start_ts),
            "requested_to_ts": int(end_exclusive_ts),
        }

    facts["requested_period_label"] = f"{start_date} → {date_label}"

    kind = _custom_period_kind(day_count)
    period_key = f"custom:{kind}"
    want_ai = bool(reports_custom.get("want_ai"))

    memory_store.pop_pending_manual_mode(user_id)
    mem.pop("pending_manual_mode", None)
    mem.pop("reports_custom", None)
    memory_store.save_memory(user_id, mem)

    await message.answer(templates.menu_reports_custom_building_message(start_date, date_label))

    ai_block = None
    profile = normalize_ai_features_settings(
        normalize_persona_settings(ctx.profile_store.load(user_id) or {})
    )
    if want_ai and not ai_feature_enabled(profile, "report_explanations"):
        await message.answer(templates.ai_feature_disabled_message("AI explanations"))
        want_ai = False

    if want_ai:
        if not ctx.settings.openai_api_key:
            await message.answer(templates.ai_disabled_missing_key_message())
        else:
            await message.answer(templates.ai_insights_progress_message())
            try:
                ai_block = await _build_ai_block_from_facts(
                    ctx=ctx,
                    tg_id=user_id,
                    period_label=f"{start_date} → {date_label}",
                    facts=facts,
                )
            except Exception as e:
                ctx.logger.warning("LLM unavailable, sending facts-only. err=%s", e)
                await message.answer(map_llm_error(e))
                ai_block = None

    text = ctx.render_report_for_user(user_id, period_key, facts, ai_block=ai_block)
    await message.answer(text)
    return True


def register_report_handlers(dp, *, ctx: HandlerContext) -> None:
    async def _send_report_from_menu(
        query: CallbackQuery,
        period: str,
        *,
        want_ai: bool,
    ) -> None:
        if not await ctx.gate_menu_query_or_resume(query):
            return
        if query.message and query.from_user:
            await ctx.send_period_report(
                query.message,
                period,
                tg_id_override=query.from_user.id,
                want_ai_override=want_ai,
            )
        await query.answer()

    async def _open_report_mode_picker(query: CallbackQuery, *, period: str) -> None:
        if not await ctx.gate_menu_dependencies(
            query,
            require_token=True,
            require_accounts=True,
            require_ledger=True,
        ):
            return

        if query.message:
            await query.message.edit_text(
                templates.menu_reports_mode_message(_period_label(period)),
                reply_markup=build_report_mode_keyboard(
                    det_callback=f"menu:reports:run:{period}:det",
                    ai_callback=f"menu:reports:run:{period}:ai",
                    back_callback="menu:reports",
                ),
            )
        await query.answer()

    @dp.callback_query(lambda c: c.data == "menu:reports:today")
    async def cb_menu_today(query: CallbackQuery) -> None:
        await _open_report_mode_picker(query, period="today")

    @dp.callback_query(lambda c: c.data == "menu:reports:week")
    async def cb_menu_reports_week(query: CallbackQuery) -> None:
        await _open_report_mode_picker(query, period="week")

    @dp.callback_query(lambda c: c.data == "menu:reports:month")
    async def cb_menu_reports_month(query: CallbackQuery) -> None:
        await _open_report_mode_picker(query, period="month")

    @dp.callback_query(lambda c: c.data == "menu_week")
    async def cb_menu_week(query: CallbackQuery) -> None:
        await _send_report_from_menu(query, "week", want_ai=False)

    @dp.callback_query(lambda c: c.data == "menu_month")
    async def cb_menu_month(query: CallbackQuery) -> None:
        await _send_report_from_menu(query, "month", want_ai=False)

    @dp.callback_query(lambda c: c.data == "menu_today")
    async def cb_menu_legacy_today(query: CallbackQuery) -> None:
        await _send_report_from_menu(query, "today", want_ai=False)

    @dp.callback_query(lambda c: bool(c.data) and str(c.data).startswith("menu:reports:run:"))
    async def cb_menu_run_report_mode(query: CallbackQuery) -> None:
        raw = str(query.data or "")
        parts = raw.split(":")
        if len(parts) != 5:
            await query.answer("Некоректно", show_alert=True)
            return

        period = parts[3]
        mode = parts[4]
        if period not in {"today", "week", "month"} or mode not in {"det", "ai"}:
            await query.answer("Некоректно", show_alert=True)
            return

        await _send_report_from_menu(query, period, want_ai=(mode == "ai"))

    @dp.callback_query(lambda c: c.data == "menu:reports:custom")
    async def cb_menu_reports_custom(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(
            query,
            require_token=True,
            require_accounts=True,
            require_ledger=True,
        ):
            return

        if query.message:
            await query.message.edit_text(
                templates.menu_reports_mode_message(_period_label("custom")),
                reply_markup=build_report_mode_keyboard(
                    det_callback="menu:reports:custom:det",
                    ai_callback="menu:reports:custom:ai",
                    back_callback="menu:reports",
                ),
            )
        await query.answer()

    @dp.callback_query(lambda c: c.data in {"menu:reports:custom:det", "menu:reports:custom:ai"})
    async def cb_menu_reports_custom_mode(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(
            query,
            require_token=True,
            require_accounts=True,
            require_ledger=True,
        ):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає user id", show_alert=True)
            return

        want_ai = str(query.data or "").endswith(":ai")
        mem = memory_store.load_memory(tg_id)
        mem["reports_custom"] = {"want_ai": want_ai}
        memory_store.save_memory(tg_id, mem)
        memory_store.set_pending_manual_mode(
            tg_id,
            expected="report_custom_start",
            hint="YYYY-MM-DD",
            source="reports_custom",
            ttl_sec=900,
        )

        today = date.today()
        mem = memory_store.load_memory(tg_id)
        reports_custom = mem.get("reports_custom") or {}
        reports_custom["calendar"] = {
            "step": "start",
            "year": int(today.year),
            "month": int(today.month),
        }
        mem["reports_custom"] = reports_custom
        memory_store.save_memory(tg_id, mem)

        if query.message:
            await _send_custom_calendar(
                query,
                tg_id=tg_id,
                step="start",
                year=int(today.year),
                month=int(today.month),
            )
        await query.answer()

    @dp.callback_query(
        lambda c: bool(c.data) and str(c.data).startswith("menu:reports:custom:cal:noop")
    )
    async def cb_menu_reports_custom_calendar_noop(query: CallbackQuery) -> None:
        await query.answer()

    @dp.callback_query(
        lambda c: bool(c.data) and str(c.data).startswith("menu:reports:custom:cal:nav:")
    )
    async def cb_menu_reports_custom_calendar_nav(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає user id", show_alert=True)
            return

        mem = memory_store.load_memory(tg_id)
        reports_custom = mem.get("reports_custom")
        if not isinstance(reports_custom, dict):
            reports_custom = {}

        raw = str(query.data or "")
        parts = raw.split(":")
        if len(parts) != 9:
            await query.answer("Некоректно", show_alert=True)
            return

        step = parts[5]
        try:
            year = int(parts[6])
            month = int(parts[7])
            delta = int(parts[8])
        except Exception:
            await query.answer("Некоректно", show_alert=True)
            return

        year, month = _shift_month(year, month, delta)
        today = date.today()
        if (year, month) > (today.year, today.month):
            year, month = today.year, today.month

        calendar_state = reports_custom.get("calendar")
        if not isinstance(calendar_state, dict):
            calendar_state = {}
        calendar_state.update({"step": step, "year": year, "month": month})
        reports_custom["calendar"] = calendar_state
        mem["reports_custom"] = reports_custom
        memory_store.save_memory(tg_id, mem)

        await _send_custom_calendar(
            query,
            tg_id=tg_id,
            step=step,
            year=year,
            month=month,
            start_date=str(reports_custom.get("start_date") or "").strip() or None,
        )
        await query.answer()

    @dp.callback_query(lambda c: c.data == "menu:reports:custom:cal:back:start")
    async def cb_menu_reports_custom_calendar_back_start(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає user id", show_alert=True)
            return

        mem = memory_store.load_memory(tg_id)
        reports_custom = mem.get("reports_custom")
        if not isinstance(reports_custom, dict):
            reports_custom = {}

        start_date_raw = str(reports_custom.get("start_date") or "").strip()
        parsed = _parse_iso_day_utc(start_date_raw)
        if parsed is None:
            today = date.today()
            year, month = today.year, today.month
        else:
            start_dt = datetime.strptime(parsed[0], "%Y-%m-%d")
            year, month = start_dt.year, start_dt.month

        reports_custom["calendar"] = {
            "step": "start",
            "year": year,
            "month": month,
        }
        mem["reports_custom"] = reports_custom
        memory_store.save_memory(tg_id, mem)

        await _send_custom_calendar(
            query,
            tg_id=tg_id,
            step="start",
            year=year,
            month=month,
        )
        await query.answer()

    @dp.callback_query(
        lambda c: bool(c.data) and str(c.data).startswith("menu:reports:custom:cal:pick:")
    )
    async def cb_menu_reports_custom_calendar_pick(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає user id", show_alert=True)
            return

        raw = str(query.data or "")
        parts = raw.split(":")
        if len(parts) != 7:
            await query.answer("Некоректно", show_alert=True)
            return

        step = parts[5]
        iso = parts[6]
        parsed = _parse_iso_day_utc(iso)
        if parsed is None:
            await query.answer("Некоректно", show_alert=True)
            return

        date_label, day_start_ts = parsed
        mem = memory_store.load_memory(tg_id)
        reports_custom = mem.get("reports_custom")
        if not isinstance(reports_custom, dict):
            reports_custom = {}

        if step == "start":
            reports_custom["start_date"] = date_label
            reports_custom["start_ts"] = int(day_start_ts)
            reports_custom["calendar"] = {
                "step": "end",
                "year": int(date_label[:4]),
                "month": int(date_label[5:7]),
            }
            mem["reports_custom"] = reports_custom
            memory_store.save_memory(tg_id, mem)
            memory_store.set_pending_manual_mode(
                tg_id,
                expected="report_custom_end",
                hint="YYYY-MM-DD",
                source="reports_custom",
                ttl_sec=900,
            )
            await _send_custom_calendar(
                query,
                tg_id=tg_id,
                step="end",
                year=int(date_label[:4]),
                month=int(date_label[5:7]),
                start_date=date_label,
            )
            await query.answer()
            return

        start_date = str(reports_custom.get("start_date") or "").strip()
        start_ts_raw = reports_custom.get("start_ts")
        try:
            start_ts = int(start_ts_raw)
        except Exception:
            await query.answer("Спочатку обери start date", show_alert=True)
            today = date.today()
            await _send_custom_calendar(
                query,
                tg_id=tg_id,
                step="start",
                year=int(today.year),
                month=int(today.month),
            )
            return

        if int(day_start_ts) < start_ts:
            await query.answer("End date не може бути раніше start date", show_alert=True)
            return

        want_ai = bool(reports_custom.get("want_ai"))
        if query.message:
            await _finalize_custom_report(
                query.message,
                ctx=ctx,
                user_id=tg_id,
                start_date=start_date,
                start_ts=start_ts,
                end_date=date_label,
                end_day_start_ts=int(day_start_ts),
                want_ai=want_ai,
            )
        await query.answer()

    @dp.callback_query(lambda c: bool(c.data) and str(c.data).startswith("cov_sync:"))
    async def cb_cov_sync(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає user id", show_alert=True)
            return

        raw = (query.data or "").strip()
        parts = raw.split(":", 1)
        if len(parts) != 2 or parts[0] != "cov_sync":
            await query.answer("Некоректно", show_alert=True)
            return

        pid = parts[1].strip()
        ok = memory_store.validate_and_consume_pending(
            tg_id, pending_id=pid, now_ts=int(time.time())
        )
        if not await validate_ok_or_alert(query, ok):
            return

        mem = memory_store.load_memory(tg_id)
        payload = mem.get("pending_intent")
        days_back_raw = payload.get("days_back") if isinstance(payload, dict) else None
        nlq_text = payload.get("nlq_text") if isinstance(payload, dict) else None

        try:
            days_back = int(days_back_raw)
        except Exception:
            days_back = 30
        days_back = max(1, min(days_back, 93))

        cfg = ctx.users.load(tg_id)
        if cfg is None or not cfg.mono_token or not cfg.selected_account_ids:
            if query.message:
                await query.message.answer(templates.need_connect_and_accounts_message())
            memory_store.pop_pending_action(tg_id)
            await query.answer()
            return

        if query.message:
            await query.message.edit_reply_markup(reply_markup=None)
            await query.message.answer(templates.ledger_refresh_progress_message())

        try:
            await ctx.sync_user_ledger(tg_id, cfg, days_back=days_back)
            await compute_and_cache_reports_for_user(
                tg_id,
                list(cfg.selected_account_ids or []),
                ctx.profile_store,
            )
        except Exception:
            memory_store.pop_pending_action(tg_id)
            if query.message:
                await query.message.answer(templates.monobank_generic_error_message())
            await query.answer("Помилка", show_alert=True)
            return

        memory_store.pop_pending_action(tg_id)

        if query.message:
            await query.message.answer(templates.coverage_sync_done_message())

        text = str(nlq_text or "").strip()
        if text and query.message:
            resp = ctx.handle_nlq_fn(
                NLQRequest(
                    telegram_user_id=tg_id,
                    text=text,
                    now_ts=int(time.time()),
                )
            )
            if resp.result:
                await query.message.answer(resp.result.text)

        await query.answer("Ок")

    @dp.callback_query(lambda c: bool(c.data) and str(c.data).startswith("cov_cancel:"))
    async def cb_cov_cancel(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає user id", show_alert=True)
            return

        raw = (query.data or "").strip()
        parts = raw.split(":", 1)
        if len(parts) != 2 or parts[0] != "cov_cancel":
            await query.answer("Некоректно", show_alert=True)
            return

        pid = parts[1].strip()
        ok = memory_store.validate_and_consume_pending(
            tg_id, pending_id=pid, now_ts=int(time.time())
        )
        if not await validate_ok_or_alert(query, ok):
            return

        memory_store.pop_pending_action(tg_id)
        if query.message:
            await query.message.edit_reply_markup(reply_markup=None)
        await query.answer("Скасовано")
