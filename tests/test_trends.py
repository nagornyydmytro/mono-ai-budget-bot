from dataclasses import dataclass

from mono_ai_budget_bot.analytics.trends import compute_trends


@dataclass
class Row:
    ts: int
    amount: int
    mcc: int
    description: str
    kind: str = "spend"


def test_trends_growing_category_detected():
    now = 30 * 86400
    rows: list[Row] = []

    for d in range(14, 7, -1):
        rows.append(Row(ts=now - d * 86400 + 10, amount=-10000, mcc=5812, description="Cafe A"))

    for d in range(7, 0, -1):
        rows.append(Row(ts=now - d * 86400 + 10, amount=-30000, mcc=5812, description="Cafe A"))

    out = compute_trends(rows, now_ts=now, window_days=7, min_prev_uah=50, min_abs_delta_uah=50)

    assert "growing" in out
    assert any(x.get("kind") == "category" for x in out["growing"])


def test_trends_filters_one_day_noise_by_active_days():
    now = 50 * 86400
    rows: list[Row] = []

    rows.append(Row(ts=now - 2 * 86400 + 10, amount=-50000, mcc=5812, description="Cafe X"))
    rows.append(Row(ts=now - 9 * 86400 + 10, amount=-10000, mcc=5812, description="Cafe X"))

    out = compute_trends(rows, now_ts=now, window_days=7, min_prev_uah=50, min_abs_delta_uah=50)

    assert out["growing"] == []
    assert out["declining"] == []
