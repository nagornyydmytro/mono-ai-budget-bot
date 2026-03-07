from mono_ai_budget_bot.bot.ui import (
    build_bootstrap_history_keyboard,
    build_coverage_cta_keyboard,
    build_currency_screen_keyboard,
    build_data_menu_keyboard,
    build_main_menu_keyboard,
)


def _kb_dump(kb) -> list[list[tuple[str, str]]]:
    return [[(b.text, b.callback_data) for b in row] for row in kb.inline_keyboard]


def test_main_menu_keyboard_snapshot():
    kb = build_main_menu_keyboard()
    assert _kb_dump(kb) == [
        [("📊 Звіти", "menu:reports"), ("💬 Ask", "menu:ask")],
        [("🧩 Uncat", "menu:uncat"), ("🗂️ Категорії", "menu:categories")],
        [("✨ Insights", "menu:insights"), ("🎛️ Персоналізація", "menu:personalization")],
        [("⚙️ Мої дані", "menu:mydata")],
        [("💱 Курси", "menu:currency"), ("📘 Help", "menu:help")],
    ]


def test_currency_screen_keyboard_snapshot():
    kb = build_currency_screen_keyboard()
    assert _kb_dump(kb) == [
        [("🔄 Оновити", "currency_refresh"), ("⬅️ Назад", "currency_back")],
    ]


def test_bootstrap_history_keyboard_snapshot():
    kb = build_bootstrap_history_keyboard()
    assert _kb_dump(kb) == [
        [("📥 Bootstrap 1 місяць", "boot_30")],
        [("📥 Bootstrap 3 місяці", "boot_90")],
        [("📥 Bootstrap 6 місяців", "boot_180")],
        [("📥 Bootstrap 12 місяців", "boot_365")],
        [("⬅️ Назад", "menu:mydata")],
    ]


def test_coverage_cta_keyboard_snapshot():
    kb = build_coverage_cta_keyboard(pending_id="deadbeef")
    assert _kb_dump(kb) == [
        [("⬇️ Завантажити цей період", "cov_sync:deadbeef")],
        [("❌ Скасувати", "cov_cancel:deadbeef")],
    ]


def test_data_menu_keyboard_snapshot():
    kb = build_data_menu_keyboard()
    assert _kb_dump(kb) == [
        [("🔑 Change token", "menu:data:new_token")],
        [("💳 Change accounts", "menu:data:accounts")],
        [("🔄 Refresh latest", "menu:data:refresh")],
        [("📥 Bootstrap history", "menu:data:bootstrap")],
        [("📊 Status", "menu:data:status")],
        [("🧹 Wipe cache", "menu:data:wipe")],
        [("⬅️ Назад", "menu:root")],
    ]
