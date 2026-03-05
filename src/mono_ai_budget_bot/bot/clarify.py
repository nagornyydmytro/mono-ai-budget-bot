from __future__ import annotations


async def validate_pending_or_alert(query, pending):
    from . import templates

    if pending is None:
        await query.answer(templates.stale_button_message(), show_alert=True)
        return False
    return True


async def validate_ok_or_alert(query, ok: bool) -> bool:
    from . import templates

    if not ok:
        await query.answer(templates.stale_button_message(), show_alert=True)
        return False
    return True


async def validate_uncat_pending_or_alert(
    query,
    cur,
    *,
    pid: str,
    now_ts: int,
    stage: str | None = None,
) -> bool:
    from . import templates

    if cur is None or cur.pending_id != pid or cur.used or cur.is_expired(now_ts):
        await query.answer(templates.stale_button_message(), show_alert=True)
        return False
    if stage is not None and getattr(cur, "stage", None) != stage:
        await query.answer(templates.stale_button_message(), show_alert=True)
        return False
    return True
