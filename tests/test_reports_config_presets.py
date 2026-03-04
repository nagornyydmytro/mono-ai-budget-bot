from mono_ai_budget_bot.reports.config import build_reports_preset


def test_reports_preset_min_blocks():
    cfg = build_reports_preset("min")

    assert cfg.preset == "min"
    assert cfg.daily == {"totals": True}
    assert cfg.weekly == {"totals": True, "breakdowns": True, "compare_baseline": True}
    assert cfg.monthly == {"totals": True, "breakdowns": True}


def test_reports_preset_max_blocks():
    cfg = build_reports_preset("max")

    assert cfg.preset == "max"
    assert cfg.daily == {"totals": True, "breakdowns": True}
    assert cfg.weekly == {
        "totals": True,
        "breakdowns": True,
        "compare_baseline": True,
        "trends": True,
    }
    assert cfg.monthly == {
        "totals": True,
        "breakdowns": True,
        "trends": True,
        "anomalies": True,
        "what_if": True,
    }


def test_reports_preset_custom_is_empty():
    cfg = build_reports_preset("custom")

    assert cfg.preset == "custom"
    assert cfg.daily == {}
    assert cfg.weekly == {}
    assert cfg.monthly == {}
