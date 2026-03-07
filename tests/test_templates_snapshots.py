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
