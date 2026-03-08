from __future__ import annotations

import hashlib
import time

from aiogram.types import CallbackQuery

from mono_ai_budget_bot.taxonomy.presets import build_taxonomy_preset
from mono_ai_budget_bot.taxonomy.rules import Rule
from mono_ai_budget_bot.uncat.ui import list_leaf_options

from . import templates
from .clarify import validate_uncat_pending_or_alert
from .handlers_common import HandlerContext
from .ui import build_uncat_leaf_picker_keyboard


def register_uncat_handlers(dp, *, ctx: HandlerContext) -> None:
    async def _assign_leaf(query: CallbackQuery, *, tg_id: int, cur, leaf_id: str) -> None:
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

    @dp.callback_query(lambda c: c.data == "menu:uncat")
    async def cb_menu_uncat(query: CallbackQuery) -> None:
        if not await ctx.gate_menu_dependencies(
            query,
            require_token=True,
            require_accounts=True,
        ):
            return

        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        await query.answer()

        if query.message:
            await ctx.send_next_uncat(query.message, tg_id)

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

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data.startswith("uncat_choose:"))
    async def cb_uncat_choose(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        parts = str(query.data).split(":")
        pid = parts[1] if len(parts) > 1 else ""

        cur = ctx.uncat_pending_store.load(tg_id)
        now_ts = int(time.time())
        if not await validate_uncat_pending_or_alert(
            query, cur, pid=pid, now_ts=now_ts, stage="review"
        ):
            return

        next_pending = ctx.uncat_pending_store.create(
            tg_id,
            tx_id=cur.tx_id,
            stage="pick_leaf",
            ttl_sec=900,
        )

        tax = ctx.taxonomy_store.load(tg_id)
        if tax is None:
            tax = build_taxonomy_preset("min")

        leaves = list_leaf_options(tax, root_kind="expense")
        leaves = leaves[:8]

        if query.message:
            await query.message.answer(
                "📂 Обери категорію вручну:",
                reply_markup=build_uncat_leaf_picker_keyboard(
                    pending_id=next_pending.pending_id,
                    leaves=[(opt.name, opt.leaf_id) for opt in leaves],
                    back_callback="menu:uncat",
                ),
            )

        await query.answer()

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data.startswith("uncat_suggest:"))
    async def cb_uncat_suggest(query: CallbackQuery) -> None:
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
            query, cur, pid=pid, now_ts=now_ts, stage="review"
        ):
            return

        await _assign_leaf(query, tg_id=tg_id, cur=cur, leaf_id=leaf_id)
        await query.answer()

    @dp.callback_query(lambda c: isinstance(c.data, str) and c.data.startswith("uncat_skip:"))
    async def cb_uncat_skip(query: CallbackQuery) -> None:
        tg_id = query.from_user.id if query.from_user else None
        if tg_id is None:
            await query.answer("Немає tg id", show_alert=True)
            return

        parts = str(query.data).split(":")
        pid = parts[1] if len(parts) > 1 else ""

        cur = ctx.uncat_pending_store.load(tg_id)
        now_ts = int(time.time())
        if not await validate_uncat_pending_or_alert(
            query, cur, pid=pid, now_ts=now_ts, stage="review"
        ):
            return

        items = ctx.uncat_store.load(tg_id)
        item = next((x for x in items if x.tx_id == cur.tx_id), None)
        if item is not None:
            remaining = [x for x in items if x.tx_id != cur.tx_id]
            remaining.append(item)
            ctx.uncat_store.save(tg_id, remaining)

        ctx.uncat_pending_store.mark_used(tg_id)
        ctx.uncat_pending_store.clear(tg_id)

        if query.message:
            await ctx.send_next_uncat(query.message, tg_id)

        await query.answer("Пропущено")

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
        ):
            return
        if getattr(cur, "stage", None) not in {"review", "pick_leaf"}:
            await query.answer(templates.stale_button_message(), show_alert=True)
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

        await _assign_leaf(query, tg_id=tg_id, cur=cur, leaf_id=leaf_id)
        await query.answer()
