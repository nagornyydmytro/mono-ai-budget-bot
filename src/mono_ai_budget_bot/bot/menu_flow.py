from __future__ import annotations

from aiogram.types import CallbackQuery


async def render_menu_screen(
    query: CallbackQuery,
    *,
    text: str,
    reply_markup,
) -> None:
    if query.message:
        await query.message.edit_text(text, reply_markup=reply_markup)
    await query.answer()


async def render_placeholder_screen(
    query: CallbackQuery,
    *,
    text: str,
    reply_markup,
) -> None:
    if query.message:
        await query.message.edit_text(text, reply_markup=reply_markup)
    await query.answer()


async def show_placeholder_alert(query: CallbackQuery, *, text: str) -> None:
    await query.answer(text, show_alert=True)


async def gate_menu_query_or_resume(
    query: CallbackQuery,
    *,
    sync_onboarding_progress,
    onboarding_done,
    finish_onboarding_text: str,
    finish_onboarding_keyboard,
) -> bool:
    tg_id = query.from_user.id if query.from_user else None
    if tg_id is None:
        await query.answer()
        return False

    sync_onboarding_progress(tg_id)
    if onboarding_done(tg_id):
        return True

    if query.message:
        await query.message.edit_text(
            finish_onboarding_text,
            reply_markup=finish_onboarding_keyboard,
        )
    await query.answer()
    return False


async def gate_menu_dependencies(
    query: CallbackQuery,
    *,
    users,
    tx_store,
    sync_onboarding_progress,
    onboarding_done,
    require_token: bool = False,
    require_accounts: bool = False,
    require_ledger: bool = False,
    missing_token_text: str,
    missing_token_keyboard,
    missing_accounts_text: str,
    missing_accounts_keyboard,
    missing_ledger_text: str,
    missing_ledger_keyboard,
    finish_onboarding_text: str,
    finish_onboarding_keyboard,
) -> bool:
    tg_id = query.from_user.id if query.from_user else None
    if tg_id is None:
        await query.answer()
        return False

    sync_onboarding_progress(tg_id)
    cfg = users.load(tg_id)

    if require_token and (cfg is None or not cfg.mono_token):
        if query.message:
            await query.message.edit_text(
                missing_token_text,
                reply_markup=missing_token_keyboard,
            )
        await query.answer()
        return False

    if require_accounts and (cfg is None or not cfg.selected_account_ids):
        if query.message:
            await query.message.edit_text(
                missing_accounts_text,
                reply_markup=missing_accounts_keyboard,
            )
        await query.answer()
        return False

    if require_ledger:
        account_ids = list(cfg.selected_account_ids or []) if cfg is not None else []
        has_ledger = bool(account_ids) and (
            tx_store.aggregated_coverage_window(tg_id, account_ids) is not None
        )
        if not has_ledger:
            if query.message:
                await query.message.edit_text(
                    missing_ledger_text,
                    reply_markup=missing_ledger_keyboard,
                )
            await query.answer()
            return False

    if not onboarding_done(tg_id):
        if query.message:
            await query.message.edit_text(
                finish_onboarding_text,
                reply_markup=finish_onboarding_keyboard,
            )
        await query.answer()
        return False

    return True


async def gate_refresh_dependencies(
    query: CallbackQuery,
    *,
    users,
    missing_token_text: str,
    missing_token_keyboard,
    missing_accounts_text: str,
    missing_accounts_keyboard,
):
    tg_id = query.from_user.id if query.from_user else None
    if tg_id is None:
        await query.answer()
        return False, None

    cfg = users.load(tg_id)

    if cfg is None or not cfg.mono_token:
        if query.message:
            await query.message.edit_text(
                missing_token_text,
                reply_markup=missing_token_keyboard,
            )
        await query.answer()
        return False, None

    if not cfg.selected_account_ids:
        if query.message:
            await query.message.edit_text(
                missing_accounts_text,
                reply_markup=missing_accounts_keyboard,
            )
        await query.answer()
        return False, None

    return True, cfg
