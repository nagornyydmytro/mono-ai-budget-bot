from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

try:
    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder
except Exception:
    InlineKeyboardBuilder = None
    InlineKeyboardButton = None


BTN_BACK = "⬅️ Назад"
BTN_OTHER = "✍️ Інший варіант"
BTN_CANCEL = "❌ Скасувати"
BTN_CONFIRM = "✅ Підтвердити"
BTN_REFRESH = "🔄 Оновити"
BTN_SKIP = "➡️ Skip"
BTN_NEXT = "➡️ Далі"
BTN_PREV = "⬅️ Назад"
BTN_DONE = "✅ Done"


MENU_CONNECT = "🔐 Connect"
MENU_WEEK = "📊 Week"
MENU_MONTH = "📅 Month"
MENU_HELP = "📘 Help"
MENU_UNCAT = "🧩 Uncat"
MENU_CURRENCY = "💱 Курси"
MENU_ASK = "💬 Ask"
MENU_INSIGHTS = "✨ Insights"
MENU_PERSONALIZATION = "🎛️ Персоналізація"
MENU_MY_DATA = "⚙️ Мої дані"


@dataclass(frozen=True)
class _SimpleButton:
    text: str
    callback_data: str


@dataclass(frozen=True)
class _SimpleMarkup:
    inline_keyboard: list[list[_SimpleButton]]


def _build_rows(rows: Sequence[Sequence[tuple[str, str]]]) -> Any:
    if InlineKeyboardBuilder is None or InlineKeyboardButton is None:
        kb_rows: list[list[_SimpleButton]] = []
        for row in rows:
            kb_rows.append([_SimpleButton(text=str(t), callback_data=str(cb)) for t, cb in row])
        return _SimpleMarkup(inline_keyboard=kb_rows)

    kb = InlineKeyboardBuilder()
    for row in rows:
        kb.row(*[InlineKeyboardButton(text=str(t), callback_data=str(cb)) for t, cb in row])
    return kb.as_markup()


def build_rows_keyboard(rows: Sequence[Sequence[tuple[str, str]]]) -> Any:
    return _build_rows(rows)


def build_main_menu_keyboard(*, uncat_enabled: bool = True) -> Any:
    rows = [
        [("📊 Звіти", "menu:reports"), (MENU_ASK, "menu:ask")],
        [(MENU_UNCAT, "menu:uncat"), ("🗂️ Категорії", "menu:categories")],
        [(MENU_INSIGHTS, "menu:insights"), (MENU_PERSONALIZATION, "menu:personalization")],
        [(MENU_MY_DATA, "menu:mydata")],
        [(MENU_CURRENCY, "menu:currency"), (MENU_HELP, "menu:help")],
    ]

    return _build_rows(rows)


def build_accounts_picker_keyboard(accounts: list[dict], selected_ids: set[str]) -> Any:
    rows: list[list[tuple[str, str]]] = []

    for acc in accounts:
        acc_id = str(acc["id"])
        masked = " / ".join(acc.get("maskedPan") or []) or "без картки"
        cur = str(acc.get("currencyCode", ""))
        mark = "✅" if acc_id in selected_ids else "⬜️"
        text = f"{mark} {masked} ({cur})"
        rows.append([(text, f"acc_toggle:{acc_id}")])

    rows.append([("🧹 Clear", "acc_clear"), (BTN_DONE, "acc_done")])

    return _build_rows(rows)


def build_onboarding_resume_keyboard() -> Any:
    return _build_rows(
        [
            [("➡️ Продовжити онбординг", "onb_resume")],
            [(BTN_BACK, "onb_back_main")],
        ]
    )


def build_start_menu_keyboard() -> Any:
    return _build_rows(
        [
            [(MENU_CONNECT, "menu_connect"), (MENU_HELP, "menu:help")],
            [(MENU_CURRENCY, "menu:currency")],
        ]
    )


def build_reports_menu_keyboard() -> Any:
    return _build_rows(
        [
            [("📅 Today", "menu:reports:today")],
            [("📊 Last 7 days", "menu:reports:week")],
            [("🗓️ Last 30 days", "menu:reports:month")],
            [("🛠️ Custom", "menu:reports:custom")],
            [(BTN_BACK, "menu:root")],
        ]
    )


def build_report_mode_keyboard(*, det_callback: str, ai_callback: str, back_callback: str) -> Any:
    return _build_rows(
        [
            [("📄 Лише звіт", det_callback)],
            [("🤖 З AI-поясненням", ai_callback)],
            [(BTN_BACK, back_callback)],
        ]
    )


def build_data_menu_keyboard() -> Any:
    return _build_rows(
        [
            [("🔑 Change token", "menu:data:new_token")],
            [("💳 Change accounts", "menu:data:accounts")],
            [("🔄 Refresh latest", "menu:data:refresh")],
            [("📥 Bootstrap history", "menu:data:bootstrap")],
            [("📊 Status", "menu:data:status")],
            [("🧹 Wipe cache", "menu:data:wipe")],
            [(BTN_BACK, "menu:root")],
        ]
    )


def build_personalization_menu_keyboard() -> Any:
    return _build_rows(
        [
            [("🧑 Persona", "menu:personalization:persona")],
            [("⚡ Activity mode", "menu:personalization:activity")],
            [("🧩 Report blocks", "menu:personalization:reports")],
            [("🧾 Uncategorized prompts", "menu:personalization:uncat")],
            [("🤖 AI features", "menu:personalization:ai")],
            [(BTN_BACK, "menu:root")],
        ]
    )


def build_activity_mode_keyboard(current_mode: str) -> Any:
    rows = [
        [
            (
                "✅ Loud" if current_mode == "loud" else "⬜️ Loud",
                "menu:personalization:activity:loud",
            )
        ],
        [
            (
                "✅ Quiet" if current_mode == "quiet" else "⬜️ Quiet",
                "menu:personalization:activity:quiet",
            )
        ],
        [
            (
                "✅ Custom" if current_mode == "custom" else "⬜️ Custom",
                "menu:personalization:activity:custom",
            )
        ],
        [(BTN_BACK, "menu:personalization")],
    ]
    return _build_rows(rows)


def build_activity_custom_toggles_keyboard(enabled: dict[str, bool]) -> Any:
    labels = {
        "auto_reports": "Auto reports",
        "uncat_prompts": "Uncategorized prompts",
        "trends_alerts": "Trend nudges",
        "anomalies_alerts": "Anomaly nudges",
        "forecast_alerts": "Forecast nudges",
        "coach_nudges": "Coach nudges",
    }
    order = [
        "auto_reports",
        "uncat_prompts",
        "trends_alerts",
        "anomalies_alerts",
        "forecast_alerts",
        "coach_nudges",
    ]

    rows: list[list[tuple[str, str]]] = []
    for key in order:
        mark = "✅" if enabled.get(key, False) else "❌"
        rows.append([(f"{mark} {labels[key]}", f"menu:personalization:activity:toggle:{key}")])

    rows.append([(BTN_BACK, "menu:personalization:activity")])
    return _build_rows(rows)


def build_uncat_frequency_keyboard(current_value: str) -> Any:
    rows = [
        [
            (
                "✅ Одразу" if current_value == "immediate" else "⬜️ Одразу",
                "menu:personalization:uncat:immediate",
            )
        ],
        [
            (
                "✅ Раз на день" if current_value == "daily" else "⬜️ Раз на день",
                "menu:personalization:uncat:daily",
            )
        ],
        [
            (
                "✅ Раз на тиждень" if current_value == "weekly" else "⬜️ Раз на тиждень",
                "menu:personalization:uncat:weekly",
            )
        ],
        [
            (
                "✅ Перед звітом" if current_value == "before_report" else "⬜️ Перед звітом",
                "menu:personalization:uncat:before_report",
            )
        ],
        [(BTN_BACK, "menu:personalization")],
    ]
    return _build_rows(rows)


def build_reports_preset_keyboard() -> Any:
    return _build_rows(
        [
            [("⚡ Min", "menu:personalization:reports:min")],
            [("🧠 Max", "menu:personalization:reports:max")],
            [("🛠️ Custom", "menu:personalization:reports:custom")],
            [(BTN_BACK, "menu:personalization")],
        ]
    )


def build_reports_custom_period_menu_keyboard() -> Any:
    return _build_rows(
        [
            [("🗓️ Daily", "menu:personalization:reports:period:daily")],
            [("📅 Weekly", "menu:personalization:reports:period:weekly")],
            [("🗓️ Monthly", "menu:personalization:reports:period:monthly")],
            [(BTN_BACK, "menu:personalization:reports")],
        ]
    )


def build_reports_custom_blocks_menu_keyboard(period: str, enabled: dict[str, bool]) -> Any:
    order = ["totals", "breakdowns", "compare_baseline", "trends", "anomalies", "what_if"]
    titles = {
        "totals": "Факти (суми/оборот)",
        "breakdowns": "Розбивки (категорії/мерчанти)",
        "compare_baseline": "Порівняння (baseline)",
        "trends": "Тренди",
        "anomalies": "Аномалії",
        "what_if": "What-if",
    }

    rows: list[list[tuple[str, str]]] = []
    for key in order:
        if key not in enabled:
            continue
        mark = "✅" if enabled.get(key) else "❌"
        rows.append(
            [
                (
                    f"{mark} {titles.get(key, key)}",
                    f"menu:personalization:reports:toggle:{period}:{key}",
                )
            ]
        )

    rows.append([(BTN_BACK, "menu:personalization:reports:custom")])
    return _build_rows(rows)


def build_categories_menu_keyboard() -> Any:
    return _build_rows(
        [
            [("➕ Додати категорію", "menu:categories:add")],
            [("✏️ Перейменувати", "menu:categories:rename")],
            [("🗑️ Видалити", "menu:categories:delete")],
            [(BTN_BACK, "menu:root")],
        ]
    )


def build_vertical_options_keyboard(options: Iterable[tuple[str, str]]) -> Any:
    rows: list[list[tuple[str, str]]] = [[(t, cb)] for t, cb in options]
    return _build_rows(rows)


def build_nlq_clarify_keyboard(
    options: Iterable[str],
    *,
    pending_id: str | None = None,
    limit: int = 8,
    include_other: bool = True,
    include_cancel: bool = True,
    pick_prefix_base: str = "nlq_pick",
    other_base: str = "nlq_other",
    cancel_base: str = "nlq_cancel",
) -> Any:
    opts = [str(x).strip() for x in options if isinstance(x, str) and str(x).strip()]
    if not opts:
        return None

    limit = max(1, min(int(limit), 15))
    opts = opts[:limit]

    pid = (pending_id or "").strip()
    if pid:
        pick_prefix = f"{pick_prefix_base}:{pid}:"
        other_data = f"{other_base}:{pid}"
        cancel_data = f"{cancel_base}:{pid}"
    else:
        pick_prefix = f"{pick_prefix_base}:"
        other_data = other_base
        cancel_data = cancel_base

    rows: list[list[tuple[str, str]]] = []
    for i, opt in enumerate(opts, start=1):
        text = opt
        if len(text) > 32:
            text = text[:29].rstrip() + "…"
        rows.append([(f"{i}) {text}", f"{pick_prefix}{i}")])

    if include_other:
        rows.append([(BTN_OTHER, other_data)])

    if include_cancel:
        rows.append([(BTN_CANCEL, cancel_data)])

    return _build_rows(rows)


def build_coverage_cta_keyboard(*, pending_id: str) -> Any:
    pid = (pending_id or "").strip()
    if not pid:
        return None

    return _build_rows(
        [
            [("⬇️ Завантажити цей період", f"cov_sync:{pid}")],
            [("❌ Скасувати", f"cov_cancel:{pid}")],
        ]
    )


def build_back_keyboard(callback_data: str, *, text: str = BTN_BACK) -> Any:
    return _build_rows([[(text, callback_data)]])


def build_back_cancel_keyboard(back_cb: str, cancel_cb: str) -> Any:
    return _build_rows([[(BTN_BACK, back_cb), (BTN_CANCEL, cancel_cb)]])


def build_confirm_other_cancel_keyboard(
    *,
    confirm_cb: str,
    other_cb: str,
    cancel_cb: str,
    confirm_text: str = BTN_CONFIRM,
    other_text: str = BTN_OTHER,
    cancel_text: str = BTN_CANCEL,
) -> Any:
    return _build_rows(
        [[(confirm_text, confirm_cb)], [(other_text, other_cb)], [(cancel_text, cancel_cb)]]
    )


def build_currency_screen_keyboard() -> Any:
    return _build_rows([[(BTN_REFRESH, "currency_refresh"), (BTN_BACK, "currency_back")]])


def build_bootstrap_picker_keyboard(*, include_skip: bool = True) -> Any:
    rows: list[list[tuple[str, str]]] = [
        [("📥 Bootstrap 1 місяць", "boot_30")],
        [("📥 Bootstrap 3 місяці", "boot_90")],
        [("📥 Bootstrap 6 місяців", "boot_180")],
        [("📥 Bootstrap 12 місяців", "boot_365")],
    ]
    if include_skip:
        rows.append([(BTN_SKIP, "boot_skip")])
    return _build_rows(rows)


def build_bootstrap_history_keyboard() -> Any:
    return _build_rows(
        [
            [("📥 Bootstrap 1 місяць", "boot_30")],
            [("📥 Bootstrap 3 місяці", "boot_90")],
            [("📥 Bootstrap 6 місяців", "boot_180")],
            [("📥 Bootstrap 12 місяців", "boot_365")],
            [(BTN_BACK, "menu:mydata")],
        ]
    )


def build_uncat_leaf_picker_keyboard(
    *,
    pending_id: str,
    leaves: Iterable[tuple[str, str]],
) -> Any:
    rows: list[list[tuple[str, str]]] = []
    for name, leaf_id in leaves:
        rows.append([(name, f"uncat_pick:{pending_id}:{leaf_id}")])

    rows.append([("➕ Створити категорію", f"uncat_create:{pending_id}")])
    rows.append([(BTN_CANCEL, f"uncat_cancel:{pending_id}")])

    return _build_rows(rows)


def build_paging_keyboard(
    *,
    prev_cb: str | None = None,
    next_cb: str | None = None,
    back_cb: str | None = None,
    prev_text: str = BTN_PREV,
    next_text: str = BTN_NEXT,
    back_text: str = BTN_BACK,
) -> Any:
    row: list[tuple[str, str]] = []
    if prev_cb:
        row.append((prev_text, prev_cb))
    if next_cb:
        row.append((next_text, next_cb))

    rows: list[list[tuple[str, str]]] = []
    if row:
        rows.append(row)
    if back_cb:
        rows.append([(back_text, back_cb)])
    return _build_rows(rows)


def build_reports_custom_period_keyboard() -> Any:
    return build_vertical_options_keyboard(
        [
            ("🗓️ Daily", "rep_custom_period:daily"),
            ("📅 Weekly", "rep_custom_period:weekly"),
            ("🗓️ Monthly", "rep_custom_period:monthly"),
            ("✅ Готово", "rep_custom_done"),
        ]
    )


def build_reports_custom_blocks_keyboard(period: str, enabled: dict[str, bool]) -> Any:
    order = ["totals", "breakdowns", "compare_baseline", "trends", "anomalies", "what_if"]
    titles = {
        "totals": "Факти (суми/оборот)",
        "breakdowns": "Розбивки (категорії/мерчанти)",
        "compare_baseline": "Порівняння (baseline)",
        "trends": "Тренди",
        "anomalies": "Аномалії",
        "what_if": "What-if",
    }

    rows: list[tuple[str, str]] = []
    for k in order:
        if k not in enabled:
            continue
        mark = "✅" if enabled.get(k) else "❌"
        rows.append((f"{mark} {titles.get(k, k)}", f"rep_custom_toggle:{period}:{k}"))

    rows.append(("⬅️ Назад", "rep_custom_back"))
    return build_vertical_options_keyboard(rows)


def build_uncat_prompt_keyboard() -> Any:
    return build_vertical_options_keyboard([("🧩 Розкласти по категоріях", "menu:uncat")])
