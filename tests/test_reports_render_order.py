from mono_ai_budget_bot.reports.config import ReportsConfig
from mono_ai_budget_bot.reports.render import render_report


def test_render_report_respects_enabled_blocks_order_daily():
    cfg = ReportsConfig(
        preset="custom",
        daily={"totals": True, "breakdowns": True},
        weekly={},
        monthly={},
    )

    def _totals(_: dict) -> str:
        return "TOTALS"

    def _breakdowns(_: dict) -> str:
        return "BREAKDOWNS"

    text = render_report(
        "daily",
        facts={},
        config=cfg,
        block_registry={"totals": _totals, "breakdowns": _breakdowns},
    )

    assert text == "TOTALS\n\nBREAKDOWNS"


def test_render_report_skips_unknown_blocks():
    cfg = ReportsConfig(
        preset="custom",
        daily={"totals": True, "unknown_block": True, "breakdowns": True},
        weekly={},
        monthly={},
    )

    def _totals(_: dict) -> str:
        return "TOTALS"

    def _breakdowns(_: dict) -> str:
        return "BREAKDOWNS"

    text = render_report(
        "daily",
        facts={},
        config=cfg,
        block_registry={"totals": _totals, "breakdowns": _breakdowns},
    )

    assert text == "TOTALS\n\nBREAKDOWNS"
