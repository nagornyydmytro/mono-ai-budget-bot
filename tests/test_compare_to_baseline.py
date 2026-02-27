from dataclasses import dataclass

from mono_ai_budget_bot.analytics.compare import compare_yesterday_to_baseline


@dataclass
class Row:
    time: int
    amount: int
    mcc: int | None
    description: str


def test_compare_yesterday_to_baseline():
    now = 100 * 86400 + 10
    today0 = (now // 86400) * 86400
    y0 = today0 - 86400

    rows: list[Row] = []
    for i in range(10):
        rows.append(
            Row(time=today0 - (i + 2) * 86400 + 1, amount=-1000, mcc=5814, description="mcd")
        )
    rows.append(Row(time=y0 + 10, amount=-3000, mcc=5814, description="mcd"))

    r = compare_yesterday_to_baseline(rows, now_ts=now, merchant_contains="mcd", lookback_days=28)
    assert r.yesterday_cents == 3000
    assert r.baseline_median_cents == 1000
    assert r.delta_cents == 2000
