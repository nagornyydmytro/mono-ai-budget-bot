from mono_ai_budget_bot.analytics.coverage import CoverageStatus, classify_coverage


def test_classify_coverage_missing_when_no_window():
    status = classify_coverage(requested_from_ts=100, requested_to_ts=200, coverage_window=None)
    assert status == CoverageStatus.missing


def test_classify_coverage_ok_when_inside():
    status = classify_coverage(
        requested_from_ts=200, requested_to_ts=300, coverage_window=(100, 400)
    )
    assert status == CoverageStatus.ok


def test_classify_coverage_partial_when_overlaps_but_outside():
    status = classify_coverage(
        requested_from_ts=50, requested_to_ts=150, coverage_window=(100, 400)
    )
    assert status == CoverageStatus.partial


def test_classify_coverage_missing_when_no_overlap():
    status = classify_coverage(requested_from_ts=10, requested_to_ts=20, coverage_window=(100, 400))
    assert status == CoverageStatus.missing
