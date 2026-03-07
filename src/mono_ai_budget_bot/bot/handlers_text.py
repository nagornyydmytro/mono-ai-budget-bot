from __future__ import annotations

import hashlib
import time

from aiogram import F
from aiogram.types import CallbackQuery, Message

from mono_ai_budget_bot.nlq import memory_store
from mono_ai_budget_bot.nlq.types import NLQRequest
from mono_ai_budget_bot.taxonomy.models import add_category
from mono_ai_budget_bot.taxonomy.presets import build_taxonomy_preset
from mono_ai_budget_bot.taxonomy.rules import Rule

from . import templates
from .accounts_ui import render_accounts_screen
from .clarify import validate_ok_or_alert
from .errors import map_monobank_error
from .handlers_common import HandlerContext
from .handlers_reports import handle_reports_custom_manual_input
from .onboarding_flow import submit_manual_token
from .ui import build_coverage_cta_keyboard, build_nlq_clarify_keyboard


def register_text_handlers(dp, *, ctx: HandlerContext) -> None:
    @dp.callback_query(lambda c: bool(c.data) and c.data.startswith("nlq_pick:"))
    async def cb_nlq_pick(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає user id", show_alert=True)
            return

        raw = (query.data or "").strip()
        parts = raw.split(":")
        if len(parts) != 3 or parts[0] != "nlq_pick":
            await query.answer("Некоректний вибір", show_alert=True)
            return

        pid = parts[1].strip()
        idx_raw = parts[2].strip()
        if not idx_raw.isdigit():
            await query.answer("Некоректний вибір", show_alert=True)
            return

        now_ts = int(time.time())
        ok = memory_store.validate_and_consume_pending(tg_id, pending_id=pid, now_ts=now_ts)
        if not await validate_ok_or_alert(query, ok):
            return

        try:
            resp = ctx.handle_nlq_fn(
                NLQRequest(
                    telegram_user_id=tg_id,
                    text=str(int(idx_raw)),
                    now_ts=now_ts,
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

    @dp.callback_query(lambda c: bool(c.data) and c.data.startswith("nlq_other:"))
    async def cb_nlq_other(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає user id", show_alert=True)
            return

        raw = (query.data or "").strip()
        parts = raw.split(":", 1)
        if len(parts) != 2 or parts[0] != "nlq_other":
            await query.answer("Некоректно", show_alert=True)
            return

        pid = parts[1].strip()
        now_ts = int(time.time())
        ok = memory_store.validate_and_consume_pending(tg_id, pending_id=pid, now_ts=now_ts)
        if not await validate_ok_or_alert(query, ok):
            return

        mem = memory_store.load_memory(tg_id)
        kind = mem.get("pending_kind") if isinstance(mem.get("pending_kind"), str) else None

        if kind == "recipient":
            expected = "recipient"
            hint = templates.manual_mode_hint_recipient()
        elif kind == "category_alias":
            expected = "merchant_or_recipient"
            hint = templates.manual_mode_hint_category_alias()
        else:
            expected = "merchant_or_recipient"
            hint = templates.manual_mode_hint_default()

        memory_store.set_pending_manual_mode(
            tg_id,
            expected=expected,
            hint=hint,
            source="nlq_other",
            ttl_sec=600,
        )

        if query.message:
            await query.message.answer(templates.nlq_manual_entry_prompt(hint))
        await query.answer("Ок")

    @dp.callback_query(lambda c: bool(c.data) and c.data.startswith("nlq_cancel:"))
    async def cb_nlq_cancel(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає user id", show_alert=True)
            return

        raw = (query.data or "").strip()
        parts = raw.split(":", 1)
        if len(parts) != 2 or parts[0] != "nlq_cancel":
            await query.answer("Некоректно", show_alert=True)
            return

        pid = parts[1].strip()
        now_ts = int(time.time())
        ok = memory_store.validate_and_consume_pending(tg_id, pending_id=pid, now_ts=now_ts)
        if not await validate_ok_or_alert(query, ok):
            return

        memory_store.pop_pending_action(tg_id)
        if query.message:
            await query.message.answer("Ок, скасовано.")
        await query.answer("Скасовано")

    @dp.message(F.text & ~F.text.startswith("/"))
    async def handle_plain_text(message: Message) -> None:
        user_id = message.from_user.id
        now_ts = int(time.time())
        text_raw = (message.text or "").strip()
        text_lower = text_raw.lower()
        uncat_pending = ctx.uncat_pending_store.load(user_id)
        if uncat_pending is not None and uncat_pending.stage == "create_name":
            if uncat_pending.used or uncat_pending.is_expired(now_ts):
                ctx.uncat_pending_store.clear(user_id)
            else:
                if text_lower == "cancel":
                    ctx.uncat_pending_store.clear(user_id)
                    await message.answer("Ок, скасовано.")
                    return

                tax = ctx.taxonomy_store.load(user_id)
                if tax is None:
                    tax = build_taxonomy_preset("min")

                try:
                    leaf_id = add_category(tax, root_kind="expense", name=text_raw)
                except Exception:
                    await message.answer(templates.taxonomy_invalid_category_name_message())
                    return

                ctx.taxonomy_store.save(user_id, tax)

                items = ctx.uncat_store.load(user_id)
                item = next((x for x in items if x.tx_id == uncat_pending.tx_id), None)
                if item is None:
                    ctx.uncat_pending_store.clear(user_id)
                    await message.answer("Немає цієї покупки в черзі.")
                    return

                base = f"{leaf_id}:{item.description.lower().strip()}"
                rid = hashlib.sha1(base.encode("utf-8")).hexdigest()[:10]
                ctx.rules_store.add(
                    user_id,
                    Rule(id=rid, leaf_id=leaf_id, merchant_contains=item.description),
                )

                remaining = [x for x in items if x.tx_id != item.tx_id]
                ctx.uncat_store.save(user_id, remaining)
                ctx.uncat_pending_store.mark_used(user_id)
                ctx.uncat_pending_store.clear(user_id)

                await message.answer(
                    templates.uncat_category_created_and_applied_message(
                        category_name=text_raw,
                        description=item.description,
                    )
                )
                await ctx.send_next_uncat(message, user_id)
                return

        manual = memory_store.get_pending_manual_mode(user_id, now_ts=now_ts)
        if manual is not None and str(manual.get("expected") or "") == "mono_token":
            handled = await submit_manual_token(
                message,
                user_id=user_id,
                text_raw=text_raw,
                text_lower=text_lower,
                users=ctx.users,
                monobank_client_cls=ctx.monobank_client_factory,
                sync_onboarding_progress=ctx.sync_onboarding_progress,
                pop_pending_manual_mode=memory_store.pop_pending_manual_mode,
                map_monobank_error=map_monobank_error,
                connect_validation_error_text=templates.connect_validation_error(),
                validation_progress_text=templates.connect_token_validation_progress(),
                connect_success_confirm_text=templates.connect_success_confirm(),
                render_accounts_screen=render_accounts_screen,
                error_text_factory=templates.error,
            )
            if handled:
                return

        handled_custom_report = await handle_reports_custom_manual_input(
            message,
            ctx=ctx,
            user_id=user_id,
            text_raw=text_raw,
            now_ts=now_ts,
        )
        if handled_custom_report:
            return

        if text_lower == "cancel":
            memory_store.pop_pending_intent(user_id)
            await message.answer(templates.recipient_followup_cancelled())
            return

        cfg = ctx.users.load(user_id)
        if cfg is None or not cfg.mono_token:
            await message.answer(templates.err_not_connected())
            return

        if not cfg.selected_account_ids:
            await ctx.prompt_finish_onboarding(
                message,
                text=templates.onboarding_pick_accounts_prompt_message(),
            )
            return

        ctx.sync_onboarding_progress(user_id)
        if not ctx.onboarding_done(user_id):
            await ctx.prompt_finish_onboarding(message)
            return

        stored = ctx.store.load(user_id, "week")
        if stored is None:
            await message.answer(templates.err_no_ledger("week"))
            return

        try:
            resp = ctx.handle_nlq_fn(
                NLQRequest(
                    telegram_user_id=user_id,
                    text=message.text,
                    now_ts=int(time.time()),
                )
            )

            if resp.result:
                mem = memory_store.load_memory(user_id)
                cov_status = mem.get("last_coverage_status")
                cov_days = mem.get("last_coverage_days_back")
                if cov_status in {"missing", "partial"} and isinstance(cov_days, int):
                    memory_store.set_pending_intent(
                        user_id,
                        payload={
                            "action": "coverage_sync",
                            "days_back": int(cov_days),
                            "nlq_text": (message.text or "").strip(),
                        },
                        kind="coverage_cta",
                        options=None,
                    )
                    mem2 = memory_store.load_memory(user_id)
                    pid = (
                        mem2.get("pending_id") if isinstance(mem2.get("pending_id"), str) else None
                    )
                    kb = build_coverage_cta_keyboard(pending_id=(pid or ""))
                    if kb is not None:
                        await message.answer(resp.result.text, reply_markup=kb)
                        return
                kind = mem.get("pending_kind")
                opts = mem.get("pending_options")

                if (
                    kind in {"recipient", "category_alias", "paging"}
                    and isinstance(opts, list)
                    and opts
                ):
                    kb = build_nlq_clarify_keyboard(
                        opts,
                        pending_id=(
                            mem.get("pending_id")
                            if isinstance(mem.get("pending_id"), str)
                            else None
                        ),
                        limit=8,
                        include_other=(kind != "paging"),
                        include_cancel=True,
                    )
                    await message.answer(resp.result.text, reply_markup=kb)
                    return

                await message.answer(resp.result.text)
                return

            await message.answer(templates.unknown_nlq_message())
        except Exception:
            await message.answer(templates.nlq_failed_message())
