from __future__ import annotations

import hashlib
import time

from aiogram.types import CallbackQuery

from mono_ai_budget_bot.taxonomy.presets import build_taxonomy_preset
from mono_ai_budget_bot.taxonomy.rules import Rule

from . import templates
from .clarify import validate_uncat_pending_or_alert
from .handlers_common import HandlerContext
from .ui import build_back_keyboard


def register_uncat_handlers(dp, *, ctx: HandlerContext) -> None:
    @dp.callback_query(lambda c: c.data == "menu:uncat")
    async def cb_menu_uncat(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(
            query,
            require_token=True,
            require_accounts=True,
            require_ledger=True,
        ):
            return
        await query.answer()

        if query.message:
            await query.message.answer(
                templates.uncat_menu_placeholder_message(),
                reply_markup=build_back_keyboard("menu:root"),
            )

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data.startswith("uncat_cancel:"))
    async def cb_uncat_cancel(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        parts = str(query.data).split(":")
        pid = parts[1] if len(parts) > 1 else ""

        cur = ctx.uncat_pending_store.load(tg_id)
        now_ts = int(time.time())
        if not await validate_uncat_pending_or_alert(query, cur, pid=pid, now_ts=now_ts):
            return

        ctx.uncat_pending_store.mark_used(tg_id)
        ctx.uncat_pending_store.clear(tg_id)

        if query.message:
            await query.message.answer("Ок, скасовано.")
        await query.answer("Скасовано")

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data.startswith("uncat_create:"))
    async def cb_uncat_create(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        parts = str(query.data).split(":")
        pid = parts[1] if len(parts) > 1 else ""

        cur = ctx.uncat_pending_store.load(tg_id)
        now_ts = int(time.time())
        if not await validate_uncat_pending_or_alert(
            query,
            cur,
            pid=pid,
            now_ts=now_ts,
            stage="pick_leaf",
        ):
            return

        ctx.uncat_pending_store.create(tg_id, tx_id=cur.tx_id, stage="create_name", ttl_sec=900)

        if query.message:
            await query.message.answer(templates.uncat_create_category_name_prompt())

        await query.answer("Ок")

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data.startswith("uncat_pick:"))
    async def cb_uncat_pick(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        parts = str(query.data).split(":")
        pid = parts[1] if len(parts) > 1 else ""
        leaf_id = parts[2] if len(parts) > 2 else ""

        cur = ctx.uncat_pending_store.load(tg_id)
        now_ts = int(time.time())
        if not await validate_uncat_pending_or_alert(
            query,
            cur,
            pid=pid,
            now_ts=now_ts,
            stage="pick_leaf",
        ):
            return

        tax = ctx.taxonomy_store.load(tg_id)
        if tax is None:
            tax = build_taxonomy_preset("min")

        nodes = tax.get("nodes")
        leaf_name = ""
        if isinstance(nodes, dict):
            n = nodes.get(leaf_id)
            if isinstance(n, dict):
                leaf_name = str(n.get("name") or "")

        items = ctx.uncat_store.load(tg_id)
        item = next((x for x in items if x.tx_id == cur.tx_id), None)
        if item is None:
            ctx.uncat_pending_store.clear(tg_id)
            await query.answer("Немає цієї покупки в черзі.", show_alert=True)
            return

        base = f"{leaf_id}:{item.description.lower().strip()}"
        rid = hashlib.sha1(base.encode("utf-8")).hexdigest()[:10]
        ctx.rules_store.add(
            tg_id,
            Rule(id=rid, leaf_id=leaf_id, merchant_contains=item.description),
        )

        remaining = [x for x in items if x.tx_id != item.tx_id]
        ctx.uncat_store.save(tg_id, remaining)

        ctx.uncat_pending_store.mark_used(tg_id)
        ctx.uncat_pending_store.clear(tg_id)

        if query.message:
            await query.message.answer(
                templates.uncat_saved_mapping_message(
                    description=item.description,
                    leaf_name=(leaf_name or "категорія"),
                )
            )
            await ctx.send_next_uncat(query.message, tg_id)

        await query.answer()
