from dataclasses import dataclass
from mono_ai_budget_bot.analytics.trends import compute_trends


@dataclass
class Row:
    time: int
    amount: int
    mcc: int | None
    description: str


def test_compute_trends_top_growing_and_declining():
    now = 100 * 86400

    prev = [
        Row(time=now - 10 * 86400 + 1, amount=-1000, mcc=5411, description="atb"),
        Row(time=now - 10 * 86400 + 2, amount=-500, mcc=5411, description="atb"),
        Row(time=now - 9 * 86400 + 1, amount=-2000, mcc=5814, description="mcd"),
    ]
    last = [
        Row(time=now - 3 * 86400 + 1, amount=-6000, mcc=5814, description="mcd"),
        Row(time=now - 2 * 86400 + 1, amount=-300, mcc=5411, description="atb"),
    ]

    r = compute_trends(prev + last, now_ts=now, window_days=7)

    assert len(r.top_growing) >= 1
    assert any(x.label.startswith("mcd") for x in r.top_growing)

    assert len(r.top_declining) >= 1
    assert any(x.label.startswith("atb") for x in r.top_declining)