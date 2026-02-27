from dataclasses import dataclass
from mono_ai_budget_bot.analytics.profile import compute_baseline


@dataclass
class Row:
    time: int
    amount: int
    mcc: int | None
    description: str


def test_compute_baseline_basic():
    rows = [
        Row(time=86400 * 1 + 10, amount=-1000, mcc=5411, description="ATB"),
        Row(time=86400 * 1 + 20, amount=-2000, mcc=5411, description="ATB"),
        Row(time=86400 * 2 + 10, amount=-500, mcc=5411, description="ATB"),
        Row(time=86400 * 2 + 20, amount=10000, mcc=None, description="Top up"),
    ]
    b = compute_baseline(rows, window_days=7)
    assert b.total_spend_cents == 3500
    assert b.daily_avg_cents == 500
    assert b.daily_median_cents == 0