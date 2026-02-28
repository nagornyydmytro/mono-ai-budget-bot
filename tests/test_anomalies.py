from dataclasses import dataclass

from mono_ai_budget_bot.analytics.anomalies import detect_anomalies


@dataclass
class Row:
    time: int
    amount: int
    mcc: int | None
    description: str


def test_detects_spike_and_first_time():
    now = 100 * 86400

    rows = []

    for d in range(10, 0, -1):
        rows.append(
            Row(
                time=now - (d + 1) * 86400 + 10,
                amount=-10000,
                mcc=5814,
                description="mcd",
            )
        )

    rows.append(
        Row(
            time=now - 1 * 86400 + 10,
            amount=-30000,
            mcc=5814,
            description="mcd",
        )
    )

    rows.append(
        Row(
            time=now - 1 * 86400 + 20,
            amount=-50000,
            mcc=5814,
            description="new_merchant",
        )
    )

    out = detect_anomalies(
        rows,
        now_ts=now,
        lookback_days=28,
        min_threshold_cents=20000,
    )

    assert any(x.label.startswith("mcd") and x.reason == "spike_vs_median" for x in out)
    assert any(x.label.startswith("new_merchant") and x.reason == "first_time_large" for x in out)


def test_detects_category_spike():
    now = 200 * 86400

    rows = []

    for d in range(10, 0, -1):
        rows.append(
            Row(
                time=now - (d + 1) * 86400 + 10,
                amount=-12000,
                mcc=5814,
                description=f"merchant_{d}",
            )
        )

    rows.append(
        Row(
            time=now - 1 * 86400 + 10,
            amount=-60000,
            mcc=5814,
            description="one_off",
        )
    )

    out = detect_anomalies(
        rows,
        now_ts=now,
        lookback_days=28,
        min_threshold_cents=20000,
    )

    assert any(x.label.startswith("категорія:") and "Кафе/Ресторани" in x.label for x in out)
