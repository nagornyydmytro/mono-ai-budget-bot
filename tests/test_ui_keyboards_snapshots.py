from mono_ai_budget_bot.bot.ui import (
    build_bootstrap_picker_keyboard,
    build_currency_screen_keyboard,
    build_main_menu_keyboard,
)


def _kb_dump(kb) -> list[list[tuple[str, str]]]:
    return [[(b.text, b.callback_data) for b in row] for row in kb.inline_keyboard]


def test_main_menu_keyboard_snapshot():
    kb = build_main_menu_keyboard()
    assert _kb_dump(kb) == [
        [("📊 Звіти", "menu:reports"), ("⚙️ Дані", "menu:data")],
        [("🗂️ Категорії", "menu:categories"), ("🧩 Uncat", "menu_uncat")],
        [("💱 Курси", "menu_currency"), ("📘 Help", "menu_help")],
    ]


def test_currency_screen_keyboard_snapshot():
    kb = build_currency_screen_keyboard()
    assert _kb_dump(kb) == [
        [("🔄 Оновити", "currency_refresh"), ("⬅️ Назад", "currency_back")],
    ]


def test_bootstrap_picker_keyboard_snapshot():
    kb = build_bootstrap_picker_keyboard()
    assert _kb_dump(kb) == [
        [("📥 Bootstrap 1 місяць", "boot_30")],
        [("📥 Bootstrap 3 місяці", "boot_90")],
        [("📥 Bootstrap 6 місяців", "boot_180")],
        [("📥 Bootstrap 12 місяців", "boot_365")],
        [("➡️ Skip", "boot_skip")],
    ]
