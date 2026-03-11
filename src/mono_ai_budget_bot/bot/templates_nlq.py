from __future__ import annotations


def uncat_prompt_message_daily_weekly(*, n: int, last_lines: list[str], more: int) -> str:
    lines: list[str] = []
    lines.append("🧩 Є некатегоризовані покупки:")
    lines.append(f"• Кількість: {n}")
    lines.append("")
    lines.append("Останні:")
    lines.extend(last_lines)
    if more > 0:
        lines.append(f"• …ще {more}")
    lines.append("")
    lines.append("Натисни кнопку нижче, щоб розкласти по категоріях.")
    return "\n".join(lines)


def uncat_prompt_message_generic(*, n: int) -> str:
    return "\n".join(
        [
            "🧩 Є некатегоризовані покупки.",
            f"• Кількість: {n}",
            "",
            "Натисни кнопку нижче, щоб розкласти по категоріях.",
        ]
    )


def nlq_unsupported_message() -> str:
    return "Я можу відповідати лише на питання про твої витрати."


def nlq_need_connect() -> str:
    return "Спочатку підключи Monobank через кнопку Connect."


def nlq_need_accounts() -> str:
    return "Спочатку обери картки для аналізу через кнопки бота."


def nlq_profile_refreshed() -> str:
    return "Профіль оновлено."


def nlq_not_implemented_yet() -> str:
    return "Поки що цей тип запиту не реалізовано."


def nlq_recipient_ambiguous_with_options(*, alias: str, options: list[str]) -> str:
    lines: list[str] = [f"Кого саме маєш на увазі під '{alias}'?"]
    lines.append("Вибери номер або напиши точне ім'я як у виписці:")
    for i, opt in enumerate(options, start=1):
        lines.append(f"{i}) {opt}")
    return "\n".join(lines)


def nlq_recipient_ambiguous_no_options(*, alias: str) -> str:
    return f"Кого саме маєш на увазі під '{alias}'? Напиши точне ім'я отримувача як у виписці."


def nlq_recipient_not_found(*, alias: str) -> str:
    return f"Не знайшов отримувача '{alias}' у твоїй виписці за цей період."


def nlq_clarify_scope_message() -> str:
    return (
        "Уточни, будь ласка, що саме проаналізувати: витрати, доходи чи перекази. "
        "Можеш також додати період, наприклад за місяць або за 7 днів."
    )


def nlq_last_time_line(*, when_text: str, description: str, amount: str) -> str:
    return f"Остання операція була {when_text}: {description} — {amount}."


def nlq_recurrence_line(
    *, prefix: str, operations: int, active_days: int, median_gap_days: int
) -> str:
    return (
        f"{prefix}: {operations} операцій у {active_days} активних днях. "
        f"Медіанний інтервал — {median_gap_days} дн."
    )


def nlq_share_line(*, prefix: str, label: str, amount: str, share_percent: str) -> str:
    return f"{prefix}: {label} — {amount}, це {share_percent}% від усіх витрат."


def nlq_compare_previous_money_line(
    *,
    prefix: str,
    current_amount: str,
    previous_amount: str,
    delta_amount: str,
    verdict: str,
) -> str:
    return (
        f"{prefix}: {current_amount}. "
        f"За попередній такий самий період: {previous_amount}. "
        f"Різниця: {delta_amount} грн. "
        f"Висновок: витрати {verdict}."
    )


def nlq_compare_previous_count_line(
    *,
    prefix: str,
    current_count: int,
    previous_count: int,
    delta_count: int,
    verdict: str,
) -> str:
    sign = "+" if delta_count >= 0 else ""
    return (
        f"{prefix}: {current_count} операцій. "
        f"За попередній такий самий період: {previous_count}. "
        f"Різниця: {sign}{delta_count}. "
        f"Висновок: подій {verdict}."
    )


def nlq_prefix_today() -> str:
    return "Сьогодні"


def nlq_prefix_yesterday() -> str:
    return "Вчора"


def nlq_prefix_for_label(label: str) -> str:
    return f"За {label}"


def nlq_prefix_last_days(days: int) -> str:
    return f"За останні {days} днів"


def nlq_spend_sum_line(prefix: str, amount: str) -> str:
    return f"{prefix} ти витратив {amount}."


def nlq_spend_count_line(prefix: str, n: int) -> str:
    return f"{prefix} було {n} витрат."


def nlq_income_sum_line(prefix: str, amount: str) -> str:
    return f"{prefix} було поповнень на {amount}."


def nlq_income_count_line(prefix: str, n: int) -> str:
    return f"{prefix} було {n} поповнень."


def nlq_transfer_out_sum_line(prefix: str, amount: str) -> str:
    return f"{prefix} ти переказав {amount}."


def nlq_transfer_out_count_line(prefix: str, n: int) -> str:
    return f"{prefix} було {n} вихідних переказів."


def nlq_transfer_in_sum_line(prefix: str, amount: str) -> str:
    return f"{prefix} ти отримав {amount}."


def nlq_transfer_in_count_line(prefix: str, n: int) -> str:
    return f"{prefix} було {n} вхідних переказів."


def nlq_paging_hint() -> str:
    return "Напиши 1 або 'далі', щоб показати ще."


def nlq_unknown_alias_prompt_header(alias_raw: str) -> str:
    return f"Я поки що не знаю, що для тебе означає '{alias_raw}'."


def nlq_unknown_alias_prompt_choose_merchants() -> str:
    return "Вибери мерчанти, які до цього відносяться:"


def nlq_unknown_alias_prompt_input_hint() -> str:
    return "Напиши номери через кому (наприклад: 1,3) або 0 щоб скасувати."


def nlq_unknown_alias_option_line(*, idx: int, name: str, amount: str) -> str:
    return f"{idx}) {name} — {amount}"


def uncat_saved_mapping_message(*, description: str, leaf_name: str) -> str:
    return f"✅ Збережено: {description} → {leaf_name}"


def manual_mode_hint_recipient() -> str:
    return "Приклад: 'Олександр Іванов', 'MonoMarket', 'GETMANCAR'. Введи як у виписці."


def manual_mode_hint_category_alias() -> str:
    return (
        "Введи назву мерчанта як у виписці (можна частину). Приклад: 'Getmancar', 'Aston express'."
    )


def manual_mode_hint_default() -> str:
    return "Введи назву мерчанта/отримувача як у виписці (можна частину)."


def nlq_coverage_warning(d1: str, d2: str) -> str:
    return f"⚠️ Дані неповні для запитаного періоду. Coverage: {d1} — {d2}."


def nlq_top_merchants_title() -> str:
    return "Топ мерчанти"


def nlq_top_categories_title() -> str:
    return "Топ категорії"


def nlq_paging_option_show_more() -> str:
    return "Показати ще"


def nlq_compare_to_baseline_line(
    *,
    prefix: str,
    current: str,
    baseline: str,
    delta_grn: str,
    sign: str,
) -> str:
    return f"{prefix}: {current}. Зазвичай (медіана): {baseline}. Різниця: {sign}{delta_grn} грн."
