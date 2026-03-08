from mono_ai_budget_bot.bot.ui import (
    build_activity_custom_toggles_keyboard,
    build_activity_mode_keyboard,
    build_bootstrap_history_keyboard,
    build_categories_menu_keyboard,
    build_coverage_cta_keyboard,
    build_currency_screen_keyboard,
    build_data_menu_keyboard,
    build_main_menu_keyboard,
    build_personalization_menu_keyboard,
    build_report_mode_keyboard,
    build_reports_custom_blocks_menu_keyboard,
    build_reports_custom_period_menu_keyboard,
    build_reports_menu_keyboard,
    build_reports_preset_keyboard,
    build_rows_keyboard,
    build_taxonomy_migration_keyboard,
    build_uncat_empty_keyboard,
    build_uncat_frequency_keyboard,
    build_uncat_leaf_picker_keyboard,
    build_uncat_review_keyboard,
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


def test_reports_menu_keyboard_snapshot():
    kb = build_reports_menu_keyboard()
    assert _kb_dump(kb) == [
        [("📅 Today", "menu:reports:today")],
        [("📊 Last 7 days", "menu:reports:week")],
        [("🗓️ Last 30 days", "menu:reports:month")],
        [("🛠️ Custom", "menu:reports:custom")],
        [("⬅️ Назад", "menu:root")],
    ]


def test_personalization_menu_keyboard_snapshot():
    kb = build_personalization_menu_keyboard()
    assert _kb_dump(kb) == [
        [("🧑 Persona", "menu:personalization:persona")],
        [("⚡ Activity mode", "menu:personalization:activity")],
        [("🧩 Report blocks", "menu:personalization:reports")],
        [("🧾 Uncategorized prompts", "menu:personalization:uncat")],
        [("🤖 AI features", "menu:personalization:ai")],
        [("⬅️ Назад", "menu:root")],
    ]


def test_activity_mode_keyboard_snapshot():
    kb = build_activity_mode_keyboard("quiet")
    assert _kb_dump(kb) == [
        [("⬜️ Loud", "menu:personalization:activity:loud")],
        [("✅ Quiet", "menu:personalization:activity:quiet")],
        [("⬜️ Custom", "menu:personalization:activity:custom")],
        [("⬅️ Назад", "menu:personalization")],
    ]


def test_activity_custom_toggles_keyboard_snapshot():
    kb = build_activity_custom_toggles_keyboard(
        {
            "auto_reports": True,
            "uncat_prompts": False,
            "trends_alerts": True,
            "anomalies_alerts": False,
            "forecast_alerts": False,
            "coach_nudges": True,
        }
    )
    assert _kb_dump(kb) == [
        [("✅ Auto reports", "menu:personalization:activity:toggle:auto_reports")],
        [("❌ Uncategorized prompts", "menu:personalization:activity:toggle:uncat_prompts")],
        [("✅ Trend nudges", "menu:personalization:activity:toggle:trends_alerts")],
        [("❌ Anomaly nudges", "menu:personalization:activity:toggle:anomalies_alerts")],
        [("❌ Forecast nudges", "menu:personalization:activity:toggle:forecast_alerts")],
        [("✅ Coach nudges", "menu:personalization:activity:toggle:coach_nudges")],
        [("⬅️ Назад", "menu:personalization:activity")],
    ]


def test_uncat_frequency_keyboard_snapshot():
    kb = build_uncat_frequency_keyboard("before_report")
    assert _kb_dump(kb) == [
        [("⬜️ Одразу", "menu:personalization:uncat:immediate")],
        [("⬜️ Раз на день", "menu:personalization:uncat:daily")],
        [("⬜️ Раз на тиждень", "menu:personalization:uncat:weekly")],
        [("✅ Перед звітом", "menu:personalization:uncat:before_report")],
        [("⬅️ Назад", "menu:personalization")],
    ]


def test_uncat_review_keyboard_snapshot():
    kb = build_uncat_review_keyboard(
        pending_id="pid123",
        suggested_leaf=("Кафе", "cafe"),
    )
    assert _kb_dump(kb) == [
        [("✅ Призначити: Кафе", "uncat_suggest:pid123:cafe")],
        [("📂 Обрати категорію", "uncat_choose:pid123")],
        [("✍️ Ввести вручну", "uncat_create:pid123")],
        [("⏭️ Skip", "uncat_skip:pid123")],
        [("⬅️ Назад", "menu:root")],
    ]


def test_uncat_leaf_picker_keyboard_snapshot():
    kb = build_uncat_leaf_picker_keyboard(
        pending_id="pid123",
        leaves=[("Кафе", "cafe"), ("Таксі", "taxi")],
        back_callback="menu:uncat",
    )
    assert _kb_dump(kb) == [
        [("Кафе", "uncat_pick:pid123:cafe")],
        [("Таксі", "uncat_pick:pid123:taxi")],
        [("➕ Створити категорію", "uncat_create:pid123")],
        [("⬅️ Назад", "menu:uncat")],
    ]


def test_uncat_empty_keyboard_snapshot():
    kb = build_uncat_empty_keyboard()
    assert _kb_dump(kb) == [[("⬅️ Назад", "menu:root")]]


def test_categories_menu_keyboard_snapshot():
    kb = build_categories_menu_keyboard()
    assert _kb_dump(kb) == [
        [("➕ Додати категорію", "menu:categories:add")],
        [("↳ Додати підкатегорію", "menu:categories:add_subcategory")],
        [("✏️ Перейменувати", "menu:categories:rename")],
        [("🗑️ Видалити", "menu:categories:delete")],
        [("🧠 Rules / aliases", "menu:categories:rules")],
        [("⬅️ Назад", "menu:root")],
    ]


def test_taxonomy_migration_keyboard_snapshot():
    kb = build_taxonomy_migration_keyboard(
        target_label="Кафе",
        apply_callback="tax:migrate:apply",
        cancel_callback="tax:migrate:cancel",
    )
    assert _kb_dump(kb) == [
        [("➡️ Перенести в Кафе", "tax:migrate:apply")],
        [("❌ Скасувати", "tax:migrate:cancel")],
    ]


def test_reports_preset_keyboard_snapshot():
    kb = build_reports_preset_keyboard()
    assert _kb_dump(kb) == [
        [("⚡ Min", "menu:personalization:reports:min")],
        [("🧠 Max", "menu:personalization:reports:max")],
        [("🛠️ Custom", "menu:personalization:reports:custom")],
        [("⬅️ Назад", "menu:personalization")],
    ]


def test_reports_custom_period_menu_keyboard_snapshot():
    kb = build_reports_custom_period_menu_keyboard()
    assert _kb_dump(kb) == [
        [("🗓️ Daily", "menu:personalization:reports:period:daily")],
        [("📅 Weekly", "menu:personalization:reports:period:weekly")],
        [("🗓️ Monthly", "menu:personalization:reports:period:monthly")],
        [("⬅️ Назад", "menu:personalization:reports")],
    ]


def test_reports_custom_blocks_menu_keyboard_snapshot():
    kb = build_reports_custom_blocks_menu_keyboard(
        "monthly",
        {
            "totals": True,
            "breakdowns": True,
            "trends": True,
            "anomalies": False,
            "what_if": True,
        },
    )
    assert _kb_dump(kb) == [
        [("✅ Факти (суми/оборот)", "menu:personalization:reports:toggle:monthly:totals")],
        [
            (
                "✅ Розбивки (категорії/мерчанти)",
                "menu:personalization:reports:toggle:monthly:breakdowns",
            )
        ],
        [("✅ Тренди", "menu:personalization:reports:toggle:monthly:trends")],
        [("❌ Аномалії", "menu:personalization:reports:toggle:monthly:anomalies")],
        [("✅ What-if", "menu:personalization:reports:toggle:monthly:what_if")],
        [("⬅️ Назад", "menu:personalization:reports:custom")],
    ]


def test_report_mode_keyboard_snapshot():
    kb = build_report_mode_keyboard(
        det_callback="menu:reports:run:week:det",
        ai_callback="menu:reports:run:week:ai",
        back_callback="menu:reports",
    )
    assert _kb_dump(kb) == [
        [("📄 Лише звіт", "menu:reports:run:week:det")],
        [("🤖 З AI-поясненням", "menu:reports:run:week:ai")],
        [("⬅️ Назад", "menu:reports")],
    ]


def test_data_wipe_confirm_keyboard_snapshot():
    kb = build_rows_keyboard(
        [
            [("✅ Підтвердити", "menu:data:wipe:confirm")],
            [("❌ Скасувати", "menu:data:wipe:cancel")],
        ]
    )
    assert _kb_dump(kb) == [
        [("✅ Підтвердити", "menu:data:wipe:confirm")],
        [("❌ Скасувати", "menu:data:wipe:cancel")],
    ]
