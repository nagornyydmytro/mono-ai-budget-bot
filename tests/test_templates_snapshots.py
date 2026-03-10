from mono_ai_budget_bot.bot import templates


def test_templates_taxonomy_preset_prompt_snapshot():
    assert (
        templates.taxonomy_preset_prompt()
        == "\n".join(
            [
                "🗂️ Обери пресет категорій витрат/доходів:",
                "",
                "⚡ Мінімальний — базові категорії + MCC-мапа.",
                "🧠 Максимальний — більш деталізована структура (2 рівні) + MCC-мапа.",
                "🛠️ Custom — порожня структура, налаштуєш потім кнопками.",
            ]
        ).strip()
    )


def test_templates_reports_preset_prompt_snapshot():
    assert (
        templates.reports_preset_prompt()
        == "\n".join(
            [
                "📊 Обери пресет звітів:",
                "",
                "⚡ Мінімальний — коротко (основні суми та порівняння).",
                "🧠 Максимальний — додає тренди/аномалії/what-if.",
                "🛠️ Custom — налаштуєш блоки пізніше.",
            ]
        ).strip()
    )


def test_templates_activity_mode_prompt_snapshot():
    assert (
        templates.activity_mode_prompt()
        == "\n".join(
            [
                "🧩 Обери режим активності:",
                "",
                "🔊 Loud — більше авто-фіч (звітність/нагадування/підказки) — потім ще налаштуємо.",
                "🔕 Quiet — мінімум проактивних повідомлень.",
                "🛠️ Custom — будеш вмикати/вимикати фічі окремо.",
            ]
        ).strip()
    )


def test_templates_uncat_frequency_prompt_snapshot():
    assert (
        templates.uncat_frequency_prompt()
        == "\n".join(
            [
                "❓ Як часто питати про некатегоризовані покупки?",
                "",
                "⚡ Одразу — після кожної синхронізації/оновлення.",
                "🗓️ Раз на день — списком.",
                "📅 Раз на тиждень — списком.",
                "🧾 Перед звітом — тільки коли формуємо weekly/monthly.",
            ]
        ).strip()
    )


def test_templates_persona_prompt_snapshot():
    assert (
        templates.persona_prompt()
        == "\n".join(
            [
                "🧑‍🎤 Обери стиль спілкування (persona):",
                "",
                "🤝 Supportive — м’якше, підтримка і спокійні інсайти.",
                "🧠 Rational — коротко, структурно, без емоцій.",
                "🔥 Motivator — енергійно, фокус на діях і дисципліні.",
            ]
        ).strip()
    )


def test_templates_bootstrap_started_message_snapshot():
    assert (
        templates.bootstrap_started_message(30)
        == "\n".join(
            [
                "📥 Запустив завантаження історії за *30 днів* у фоні…",
                "Це може зайняти час через ліміти Monobank API.",
            ]
        ).strip()
    )


def test_templates_menu_data_bootstrap_message_snapshot():
    assert (
        templates.menu_data_bootstrap_message()
        == "\n".join(
            [
                "📥 *Bootstrap history*",
                "",
                "Обери, за який період завантажити історію транзакцій.",
            ]
        ).strip()
    )


def test_templates_menu_data_bootstrap_started_message_snapshot():
    assert (
        templates.menu_data_bootstrap_started_message("3 місяці")
        == "\n".join(
            [
                "📥 Запустив bootstrap history за *3 місяці* у фоні…",
                "Це може зайняти час через ліміти Monobank API.",
            ]
        ).strip()
    )


def test_templates_menu_data_bootstrap_done_message_snapshot():
    assert (
        templates.menu_data_bootstrap_done_message(
            months_label="6 місяців",
            accounts=2,
            fetched_requests=7,
            appended=123,
        )
        == "\n".join(
            [
                "✅ Bootstrap history завершено.",
                "",
                "Період: 6 місяців",
                "Карток: 2",
                "Запитів до API: 7",
                "Додано транзакцій: 123",
            ]
        ).strip()
    )


def test_templates_menu_data_wipe_confirm_message_snapshot():
    assert (
        templates.menu_data_wipe_confirm_message()
        == "\n".join(
            [
                "🧹 *Wipe cache*",
                "",
                "Це очистить локальний фінансовий кеш користувача:",
                "• транзакції",
                "• coverage / last sync metadata",
                "• збережені facts/reports",
                "• rules / uncat / pending",
                "",
                "Підключення Monobank і вибрані картки не будуть видалені.",
                "",
                "Підтвердити очищення?",
            ]
        ).strip()
    )


def test_templates_menu_data_wipe_done_message_snapshot():
    assert (
        templates.menu_data_wipe_done_message()
        == "\n".join(
            [
                "✅ Кеш очищено.",
                "",
                "Фінансові дані видалено локально. Monobank token і вибрані картки збережені.",
            ]
        ).strip()
    )


def test_templates_menu_reports_message_snapshot():
    assert templates.menu_reports_message() == "📊 *Звіти*\n\nОбери період:"


def test_templates_menu_reports_mode_message_snapshot():
    assert (
        templates.menu_reports_mode_message("Last 7 days")
        == "📊 *Звіти*\n\nПеріод: *Last 7 days*\nОбери режим побудови:"
    )


def test_templates_menu_personalization_message_snapshot():
    assert (
        templates.menu_personalization_message(
            persona_label="Rational",
            activity_label="Quiet",
            reports_label="Min",
            uncat_label="Перед звітом",
            ai_label="AI explanations ON",
        )
        == "\n".join(
            [
                "🎛️ *Персоналізація*",
                "",
                "Усі ці налаштування зберігаються в єдиному профілі користувача.",
                "",
                "Persona: Rational",
                "Activity mode: Quiet",
                "Report blocks: Min",
                "Uncategorized prompts: Перед звітом",
                "AI features: AI explanations ON",
                "",
                "Обери розділ:",
            ]
        ).strip()
    )


def test_templates_menu_personalization_item_message_snapshot():
    assert (
        templates.menu_personalization_item_message(
            title="🧑 *Persona*",
            current_value="Rational",
        )
        == "\n".join(
            [
                "🧑 *Persona*",
                "",
                "Поточне значення: Rational",
                "",
                "Повне редагування цього пункту буде додано в наступних комітах.",
            ]
        ).strip()
    )


def test_templates_menu_activity_mode_message_snapshot():
    assert (
        templates.menu_activity_mode_message("Quiet")
        == "\n".join(
            [
                "⚡ *Activity mode*",
                "",
                "Поточний режим: Quiet",
                "",
                "Loud — увімкнені всі proactive outputs.",
                "Quiet — proactive outputs тимчасово вимкнені.",
                "Custom — можна окремо керувати behavior flags.",
            ]
        ).strip()
    )


def test_templates_menu_activity_custom_message_snapshot():
    assert (
        templates.menu_activity_custom_message()
        == "\n".join(
            [
                "🛠️ *Custom activity flags*",
                "",
                "Тут можна окремо керувати behavior flags.",
                "Quiet не видаляє ці налаштування — лише тимчасово вимикає proactive outputs.",
            ]
        ).strip()
    )


def test_templates_menu_uncat_frequency_message_snapshot():
    assert (
        templates.menu_uncat_frequency_message("Перед звітом")
        == "\n".join(
            [
                "🧾 *Uncategorized prompts*",
                "",
                "Поточний режим: Перед звітом",
                "",
                "Це той самий параметр, що використовується і в onboarding, і після нього.",
                "",
                "Обери частоту:",
            ]
        ).strip()
    )


def test_templates_menu_categories_message_snapshot():
    assert (
        templates.menu_categories_message("*Витрати*\n• Їжа\n  — Кафе")
        == "\n".join(
            [
                "🗂️ *Категорії*",
                "",
                "Коротке дерево:",
                "*Витрати*\n• Їжа\n  — Кафе",
                "",
                "Обери дію:",
            ]
        ).strip()
    )


def test_templates_menu_categories_action_placeholder_message_snapshot():
    assert (
        templates.menu_categories_action_placeholder_message("додати підкатегорію")
        == "🗂️ *Категорії*\n\n🚧 Зараз недоступно: додати підкатегорію."
    )


def test_templates_taxonomy_migration_prompt_message_snapshot():
    assert (
        templates.taxonomy_migration_prompt_message(
            parent_name="Їжа",
            new_subcategory_name="Кафе",
        )
        == "\n".join(
            [
                "⚠️ *Потрібна міграція категорії*",
                "",
                "Категорія *Їжа* зараз є leaf.",
                "Якщо додати підкатегорію *Кафе*, вона стане parent і більше не зможе напряму тримати транзакції.",
                "",
                "Можна безпечно перенести існуючі транзакції в *Кафе* або скасувати дію.",
            ]
        ).strip()
    )


def test_templates_taxonomy_migration_applied_message_snapshot():
    assert (
        templates.taxonomy_migration_applied_message(
            source_name="Їжа",
            target_name="Кафе",
        )
        == "✅ Міграцію підтверджено: Їжа → Кафе"
    )


def test_templates_menu_reports_preset_message_snapshot():
    assert (
        templates.menu_reports_preset_message("Custom")
        == "\n".join(
            [
                "🧩 *Report blocks*",
                "",
                "Поточний preset: Custom",
                "",
                "Обери preset для рендерингу звітів:",
            ]
        ).strip()
    )


def test_templates_menu_reports_custom_period_message_snapshot():
    assert (
        templates.menu_reports_custom_period_message()
        == "\n".join(
            [
                "🛠️ *Custom report blocks*",
                "",
                "Обери період і налаштуй блоки для цього period.",
            ]
        ).strip()
    )


def test_templates_menu_reports_custom_blocks_message_snapshot():
    assert (
        templates.menu_reports_custom_blocks_message("weekly")
        == "\n".join(
            [
                "🧩 *Report blocks: Weekly*",
                "",
                "Тисни на блок, щоб перемкнути ✅/❌.",
            ]
        ).strip()
    )


def test_templates_menu_reports_custom_start_prompt_snapshot():
    assert (
        templates.menu_reports_custom_start_prompt()
        == "🛠️ *Custom report*\n\nОбери *start date* кнопками в календарі нижче.\nЗа потреби можеш також ввести дату вручну у форматі `YYYY-MM-DD`."
    )


def test_templates_menu_reports_custom_end_prompt_snapshot():
    assert (
        templates.menu_reports_custom_end_prompt("2026-03-01")
        == "🛠️ *Custom report*\n\nStart date: `2026-03-01`\nТепер обери *end date* кнопками в календарі нижче.\nЗа потреби можеш також ввести дату вручну у форматі `YYYY-MM-DD`."
    )


def test_templates_menu_reports_custom_invalid_date_message_snapshot():
    assert (
        templates.menu_reports_custom_invalid_date_message()
        == "⚠️ Некоректна дата.\n\nВикористай формат `YYYY-MM-DD`, наприклад `2026-03-07`."
    )


def test_templates_menu_reports_custom_invalid_order_message_snapshot():
    assert (
        templates.menu_reports_custom_invalid_order_message("2026-03-10", "2026-03-01")
        == "⚠️ Некоректний діапазон.\n\nStart date: `2026-03-10`\nEnd date: `2026-03-01`\n\nEnd date не може бути раніше за start date. Введи end date ще раз."
    )


def test_templates_menu_reports_custom_invalid_range_message_snapshot():
    assert (
        templates.menu_reports_custom_invalid_range_message(366)
        == "⚠️ Занадто великий діапазон.\n\nЗараз дозволено не більше *366* днів. Введи коротший період."
    )


def test_templates_menu_reports_custom_building_message_snapshot():
    assert (
        templates.menu_reports_custom_building_message("2026-03-01", "2026-03-07")
        == "📊 Будую custom report…\n\nПеріод: `2026-03-01` → `2026-03-07`"
    )


def test_templates_refresh_done_message_snapshot():
    assert (
        templates.refresh_done_message(accounts=2, fetched_requests=7, appended=123)
        == "\n".join(
            [
                "✅ Оновлено!",
                "Карток: 2",
                "Запитів до API: 7",
                "Додано транзакцій: 123",
                "",
                "Можеш дивитись: /today /week /month",
            ]
        ).strip()
    )


def test_templates_currency_screen_text_snapshot():
    assert (
        templates.currency_screen_text(
            "2026-03-03 12:00",
            "39.1234",
            None,
            "10.5000",
        )
        == "\n".join(
            [
                "*💱 Курси валют (Monobank)*",
                "Оновлено: 2026-03-03 12:00",
                "",
                "*USD/UAH*",
                "• 39.1234",
                "",
                "*EUR/UAH*",
                "• немає даних",
                "",
                "*PLN/UAH*",
                "• 10.5000",
            ]
        ).strip()
    )
