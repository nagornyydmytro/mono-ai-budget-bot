from datetime import datetime, timezone

from mono_ai_budget_bot.nlq.periods import parse_period_range


def _ts(y, m, d, hh=0, mm=0, ss=0):
    return int(datetime(y, m, d, hh, mm, ss, tzinfo=timezone.utc).timestamp())


def test_today_range():
    now = _ts(2026, 2, 27, 13, 0, 0)
    pr = parse_period_range("сьогодні", now)
    assert pr is not None
    assert pr.start_ts == _ts(2026, 2, 27, 0, 0, 0)
    assert pr.end_ts == now


def test_yesterday_range():
    now = _ts(2026, 2, 27, 13, 0, 0)
    pr = parse_period_range("вчора", now)
    assert pr is not None
    assert pr.start_ts == _ts(2026, 2, 26, 0, 0, 0)
    assert pr.end_ts == _ts(2026, 2, 27, 0, 0, 0)


def test_last_n_days_range():
    now = _ts(2026, 2, 27, 13, 0, 0)
    pr = parse_period_range("за останні 5 днів", now)
    assert pr is not None
    assert pr.end_ts == now
    assert pr.start_ts == now - 5 * 86400


def test_month_name_range():
    now = _ts(2026, 2, 27, 13, 0, 0)
    pr = parse_period_range("за січень", now)
    assert pr is not None
    assert pr.start_ts == _ts(2026, 1, 1, 0, 0, 0)
    assert pr.end_ts == _ts(2026, 2, 1, 0, 0, 0)


def test_last_month_range():
    now = _ts(2026, 2, 27, 13, 0, 0)
    pr = parse_period_range("за минулий місяць", now)
    assert pr is not None
    assert pr.start_ts == _ts(2026, 1, 1, 0, 0, 0)
    assert pr.end_ts == _ts(2026, 2, 1, 0, 0, 0)