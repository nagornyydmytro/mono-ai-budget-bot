from __future__ import annotations


def menu_insights_message() -> str:
    return "\n".join(
        [
            "✨ *Insights*",
            "",
            "Обери тип інсайту.",
            "",
            "Доступні розділи:",
            "• Trends",
            "• Anomalies",
            "• What-if",
            "• Forecast",
            "• Explain",
        ]
    ).strip()


def menu_insights_needs_data_message(section_label: str) -> str:
    return "\n".join(
        [
            f"{section_label}",
            "",
            "Поки що недостатньо підготовлених даних для цього інсайту.",
            "Спочатку онови транзакції або відкрий звіти, щоб підготувати facts.",
        ]
    ).strip()


def menu_insight_placeholder_message(section_label: str) -> str:
    return "\n".join(
        [
            f"{section_label}",
            "",
            "🚧 Цей insights-розділ ще в розробці.",
        ]
    ).strip()


def menu_insight_result_message(section_label: str, intro: str, body: str) -> str:
    return "\n".join(
        [
            section_label,
            "",
            intro,
            "",
            body.strip(),
        ]
    ).strip()


def menu_insights_whatif_message() -> str:
    return "\n".join(
        [
            "🧮 *What-if*",
            "",
            "Обери сценарій скорочення витрат.",
            "Це button-first режим на основі вже порахованих what-if facts.",
        ]
    ).strip()


def menu_insights_forecast_message() -> str:
    return "\n".join(
        [
            "🔮 *Forecast*",
            "",
            "Обери тип проєкції.",
            "Це deterministic projection, а не prediction magic.",
        ]
    ).strip()


def ai_insights_progress_message() -> str:
    return "🤖 Генерую AI інсайти…"
