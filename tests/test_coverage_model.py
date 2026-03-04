from mono_ai_budget_bot.analytics.coverage import compute_coverage


def test_compute_coverage_basic():
    timestamps = [
        1700000000,
        1700003600,
        1700086400,
    ]

    cov = compute_coverage(timestamps)

    assert cov is not None
    assert cov.start_ts == 1700000000
    assert cov.end_ts == 1700086400


def test_compute_coverage_empty():
    cov = compute_coverage([])

    assert cov is None
