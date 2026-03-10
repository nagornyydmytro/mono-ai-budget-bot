from __future__ import annotations

from aiogram.types import CallbackQuery, Message

from mono_ai_budget_bot.storage.wipe import wipe_user_financial_cache


def resolve_start_text(*, users, tg_id: int, start_text: str, connected_text: str) -> str:
    cfg = users.load(tg_id)
    if cfg is not None and cfg.mono_token:
        return connected_text
    return start_text


async def send_start_screen(
    message: Message,
    *,
    users,
    tg_id: int,
    start_text: str,
    connected_text: str,
    reply_markup,
) -> None:
    text = resolve_start_text(
        users=users,
        tg_id=tg_id,
        start_text=start_text,
        connected_text=connected_text,
    )
    await message.edit_text(text, reply_markup=reply_markup)


async def begin_manual_token_entry(
    query: CallbackQuery,
    *,
    tg_id: int,
    set_pending_manual_mode,
    hint: str,
    source: str,
    prompt_text: str,
    reply_markup,
    answer_text: str | None = None,
) -> None:
    set_pending_manual_mode(
        tg_id,
        expected="mono_token",
        hint=hint,
        source=source,
        ttl_sec=900,
    )
    if query.message:
        await query.message.answer(prompt_text, reply_markup=reply_markup)
    await query.answer(answer_text or "")


async def open_accounts_picker(
    query: CallbackQuery,
    *,
    tg_id: int,
    users,
    monobank_client_cls,
    render_accounts_screen,
    load_memory,
    save_memory,
) -> None:
    cfg = users.load(tg_id)
    if cfg is None or not cfg.mono_token:
        await query.answer("Monobank не підключено", show_alert=True)
        return

    mb = monobank_client_cls(token=cfg.mono_token)
    try:
        info = mb.client_info()
    finally:
        mb.close()

    accounts = [
        {"id": a.id, "currencyCode": a.currencyCode, "maskedPan": a.maskedPan}
        for a in info.accounts
    ]
    selected_ids = set(cfg.selected_account_ids or [])
    mem = load_memory(tg_id)
    mem["accounts_picker"] = {
        "source": "data_menu",
        "prev_selected": sorted(selected_ids),
    }
    save_memory(tg_id, mem)

    text, kb = render_accounts_screen(accounts, selected_ids)
    if query.message:
        await query.message.edit_text(text, reply_markup=kb)
    await query.answer()


async def show_data_status(
    query: CallbackQuery,
    *,
    tg_id: int,
    users,
    tx_store,
    status_message_builder,
    reply_markup,
) -> None:
    from datetime import UTC, datetime

    cfg = users.load(tg_id)
    connected = bool(cfg is not None and cfg.mono_token)
    account_ids = list(cfg.selected_account_ids or []) if cfg is not None else []
    acc_n = len(account_ids)

    coverage_summary = "немає даних"
    cov = tx_store.aggregated_coverage_window(tg_id, account_ids)
    if cov is not None:
        d1 = datetime.fromtimestamp(int(cov[0]), UTC).strftime("%Y-%m-%d")
        d2 = datetime.fromtimestamp(int(cov[1]), UTC).strftime("%Y-%m-%d")
        coverage_summary = f"{d1} → {d2}"

    last_sync_summary = "—"
    last_sync_values: list[float] = []
    for account_id in account_ids:
        meta = tx_store._meta.get(tg_id, account_id)
        if meta.last_sync_at is not None:
            last_sync_values.append(float(meta.last_sync_at))
    if last_sync_values:
        last_sync_summary = datetime.fromtimestamp(max(last_sync_values), UTC).strftime(
            "%Y-%m-%d %H:%M UTC"
        )

    text = status_message_builder(
        connected=connected,
        accounts_selected=acc_n,
        coverage_summary=coverage_summary,
        last_sync_summary=last_sync_summary,
    )

    if query.message:
        await query.message.edit_text(text, reply_markup=reply_markup)
    await query.answer()


async def submit_manual_token(
    message: Message,
    *,
    user_id: int,
    text_raw: str,
    text_lower: str,
    users,
    monobank_client_cls,
    sync_onboarding_progress,
    pop_pending_manual_mode,
    map_monobank_error,
    connect_validation_error_text: str,
    validation_progress_text: str,
    connect_success_confirm_text: str,
    render_accounts_screen,
    error_text_factory,
    manual_source: str | None,
    profile_store,
    tx_store,
    report_store,
    rules_store,
    uncat_store,
    uncat_pending_store,
    load_memory,
    save_memory,
) -> bool:
    if text_lower == "cancel":
        pop_pending_manual_mode(user_id)
        await message.answer("Ок, скасовано.")
        return True

    mono_token = text_raw
    if len(mono_token) < 20:
        await message.answer(connect_validation_error_text)
        return True

    await message.answer(validation_progress_text)

    try:
        mb = monobank_client_cls(token=mono_token)
        try:
            info = mb.client_info()
        finally:
            mb.close()
    except Exception as e:
        mapped = map_monobank_error(e)
        await message.answer(mapped or error_text_factory("Помилка перевірки токена."))
        return True

    manual_source = str(manual_source or "").strip()
    is_token_reset_flow = manual_source == "data_menu"

    if is_token_reset_flow:
        wipe_user_financial_cache(
            user_id,
            tx_store=tx_store,
            report_store=report_store,
            rules_store=rules_store,
            uncat_store=uncat_store,
            uncat_pending_store=uncat_pending_store,
        )

    users.save(user_id, mono_token=mono_token, selected_account_ids=[])

    sync_onboarding_progress(user_id)
    pop_pending_manual_mode(user_id)

    if is_token_reset_flow:
        prof = profile_store.load(user_id) or {}
        onb = prof.get("onboarding")
        if not isinstance(onb, dict):
            onb = {}

        onb["accounts_confirmed"] = False
        onb["bootstrap_requested"] = False
        onb.pop("bootstrap_days", None)
        onb["completed"] = False

        prof["onboarding"] = onb
        prof["onboarding_completed"] = False
        profile_store.save(user_id, prof)

        mem = load_memory(user_id)
        mem["accounts_picker"] = {
            "source": "token_reset",
            "prev_selected": [],
        }
        save_memory(user_id, mem)

    accounts = [
        {"id": a.id, "currencyCode": a.currencyCode, "maskedPan": a.maskedPan}
        for a in info.accounts
    ]
    text, kb = render_accounts_screen(accounts, set())
    await message.answer(f"{connect_success_confirm_text}\n\n{text}", reply_markup=kb)
    return True


async def send_onboarding_next(
    chat: Message | CallbackQuery,
    *,
    users,
    profile_store,
    taxonomy_store,
    reports_store,
    monobank_client_cls,
    render_accounts_screen,
    start_message_text: str,
    connect_success_confirm_text: str,
    accounts_after_done_with_count_text,
    taxonomy_preset_prompt_text: str,
    reports_preset_labels,
    reports_preset_prompt_text: str,
    activity_mode_labels,
    activity_mode_prompt_text: str,
    uncat_frequency_labels,
    uncat_frequency_prompt_text: str,
    persona_labels,
    persona_prompt_text: str,
    menu_root_message_text: str,
    build_start_menu_keyboard,
    build_bootstrap_picker_keyboard,
    build_vertical_options_keyboard,
    build_main_menu_keyboard,
) -> None:
    message_obj = getattr(chat, "message", None)
    if message_obj is not None:
        tg_id = chat.from_user.id if chat.from_user else None
        msg = message_obj
    else:
        tg_id = chat.from_user.id if chat.from_user else None
        msg = chat

    if tg_id is None or msg is None:
        return

    cfg = users.load(tg_id)
    prof = profile_store.load(tg_id) or {}
    onb = prof.get("onboarding")
    if not isinstance(onb, dict):
        onb = {}

    if cfg is None or not cfg.mono_token:
        kb = build_start_menu_keyboard()
        await msg.answer(start_message_text, reply_markup=kb)
        return

    accounts_confirmed = bool(onb.get("accounts_confirmed"))
    if not cfg.selected_account_ids or not accounts_confirmed:
        mb = monobank_client_cls(token=cfg.mono_token)
        try:
            info = mb.client_info()
        finally:
            mb.close()

        accounts = [
            {"id": a.id, "currencyCode": a.currencyCode, "maskedPan": a.maskedPan}
            for a in info.accounts
        ]
        selected_ids = set(cfg.selected_account_ids or [])
        text, kb = render_accounts_screen(accounts, selected_ids)
        await msg.answer(f"{connect_success_confirm_text}\n\n{text}", reply_markup=kb)
        return

    if taxonomy_store.load(tg_id) is None:
        bootstrap_requested = bool(onb.get("bootstrap_requested"))

        if not bootstrap_requested:
            count = len(cfg.selected_account_ids)
            kb = build_bootstrap_picker_keyboard(include_skip=False)
            await msg.answer(accounts_after_done_with_count_text(count), reply_markup=kb)
            return

        kb = build_vertical_options_keyboard(
            [
                ("⚡ Мінімальний", "tax_preset_min"),
                ("🧠 Максимальний (детально)", "tax_preset_max"),
                ("🛠️ Custom — налаштую потім", "tax_preset_custom"),
            ]
        )
        await msg.answer(taxonomy_preset_prompt_text, reply_markup=kb)
        return

    reports_configured = bool(onb.get("reports_configured"))
    if not reports_configured:
        l1, l2, l3 = reports_preset_labels()
        kb = build_vertical_options_keyboard(
            [
                (l1, "rep_preset_min"),
                (l2, "rep_preset_max"),
                (l3, "rep_preset_custom"),
            ]
        )
        await msg.answer(reports_preset_prompt_text, reply_markup=kb)
        return

    if not prof.get("activity_mode"):
        l1, l2, l3 = activity_mode_labels()
        kb = build_vertical_options_keyboard(
            [
                (l1, "act_loud"),
                (l2, "act_quiet"),
                (l3, "act_custom"),
            ]
        )
        await msg.answer(activity_mode_prompt_text, reply_markup=kb)
        return

    if not prof.get("uncategorized_prompt_frequency"):
        l1, l2, l3, l4 = uncat_frequency_labels()
        kb = build_vertical_options_keyboard(
            [
                (l1, "uncat_immediate"),
                (l2, "uncat_daily"),
                (l3, "uncat_weekly"),
                (l4, "uncat_before_report"),
            ]
        )
        await msg.answer(uncat_frequency_prompt_text, reply_markup=kb)
        return

    if not prof.get("persona"):
        l1, l2, l3 = persona_labels()
        kb = build_vertical_options_keyboard(
            [
                (l1, "persona_supportive"),
                (l2, "persona_rational"),
                (l3, "persona_motivator"),
            ]
        )
        await msg.answer(persona_prompt_text, reply_markup=kb)
        return

    kb = build_main_menu_keyboard(uncat_enabled=True)
    await msg.answer(menu_root_message_text, reply_markup=kb)
