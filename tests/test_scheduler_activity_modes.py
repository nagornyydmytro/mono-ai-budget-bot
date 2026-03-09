import asyncio
import logging
from types import SimpleNamespace

import pytest

import mono_ai_budget_bot.bot.scheduler as sched
from mono_ai_budget_bot.bot.scheduler import (
    build_activity_proactive_messages,
    build_scheduled_auto_report_text,
    mark_proactive_output_sent,
    maybe_send_activity_proactive_messages,
    maybe_send_guarded_proactive_output,
    maybe_send_scheduled_auto_report,
    should_send_proactive_output,
)


class DummyBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id: int, text: str, parse_mode=None):
        self.sent.append((chat_id, text, parse_mode))


class DummyProfileStore:
    def __init__(self, profile: dict):
        self.profile = profile

    def load(self, telegram_user_id: int):
        return dict(self.profile)


class DummyReportStore:
    def __init__(self, facts: dict | None):
        self.facts = facts

    def load(self, telegram_user_id: int, period: str):
        if self.facts is None:
            return None
        return SimpleNamespace(facts=self.facts)


@pytest.fixture(autouse=True)
def reset_proactive_state():
    sched._PROACTIVE_COOLDOWN_STATE.clear()
    sched._PROACTIVE_DEDUPE_STATE.clear()


def _facts() -> dict:
    return {
        "trends": {
            "growing": [{"label": "Кафе", "delta_uah": 200.0, "pct": 25.0}],
            "declining": [{"label": "Таксі", "delta_uah": -120.0, "pct": -15.0}],
        },
        "anomalies": [
            {
                "label": "WOLT",
                "last_day_uah": 500.0,
                "baseline_median_uah": 120.0,
                "reason": "spike_vs_median",
            }
        ],
        "totals": {"real_spend_total_uah": 456.0},
        "whatif_suggestions": [
            {
                "title": "Таксі",
                "scenarios": [{"pct": 10, "monthly_savings_uah": 120.0}],
            }
        ],
    }


def test_build_activity_proactive_messages_quiet_returns_no_messages():
    profile = {
        "activity_mode": "quiet",
        "activity": {
            "mode": "quiet",
            "toggles": {
                "auto_reports": False,
                "uncat_prompts": False,
                "trends_alerts": False,
                "anomalies_alerts": False,
                "forecast_alerts": False,
                "coach_nudges": False,
            },
            "custom_toggles": {
                "auto_reports": True,
                "uncat_prompts": True,
                "trends_alerts": True,
                "anomalies_alerts": True,
                "forecast_alerts": True,
                "coach_nudges": True,
            },
        },
    }

    assert build_activity_proactive_messages(profile, _facts()) == []


def test_build_activity_proactive_messages_loud_returns_all_expected_messages():
    profile = {
        "activity_mode": "loud",
        "activity": {
            "mode": "loud",
            "toggles": {
                "auto_reports": True,
                "uncat_prompts": True,
                "trends_alerts": True,
                "anomalies_alerts": True,
                "forecast_alerts": True,
                "coach_nudges": True,
            },
            "custom_toggles": {
                "auto_reports": True,
                "uncat_prompts": True,
                "trends_alerts": False,
                "anomalies_alerts": False,
                "forecast_alerts": False,
                "coach_nudges": False,
            },
        },
    }

    msgs = build_activity_proactive_messages(profile, _facts())
    assert len(msgs) == 4
    assert any("📈 Trends nudge" in x for x in msgs)
    assert any("🚨 Anomaly nudge" in x for x in msgs)
    assert any("🔮 Forecast nudge" in x for x in msgs)
    assert any("🧮 Coach nudge" in x for x in msgs)


def test_build_activity_proactive_messages_custom_respects_selected_toggles_only():
    profile = {
        "activity_mode": "custom",
        "activity": {
            "mode": "custom",
            "toggles": {
                "auto_reports": True,
                "uncat_prompts": True,
                "trends_alerts": True,
                "anomalies_alerts": False,
                "forecast_alerts": True,
                "coach_nudges": False,
            },
            "custom_toggles": {
                "auto_reports": True,
                "uncat_prompts": True,
                "trends_alerts": True,
                "anomalies_alerts": False,
                "forecast_alerts": True,
                "coach_nudges": False,
            },
        },
    }

    msgs = build_activity_proactive_messages(profile, _facts())
    assert len(msgs) == 2
    assert any("📈 Trends nudge" in x for x in msgs)
    assert any("🔮 Forecast nudge" in x for x in msgs)
    assert all("🚨 Anomaly nudge" not in x for x in msgs)
    assert all("🧮 Coach nudge" not in x for x in msgs)


def test_maybe_send_activity_proactive_messages_sends_only_allowed_outputs():
    bot = DummyBot()
    profile_store = DummyProfileStore(
        {
            "activity_mode": "custom",
            "activity": {
                "mode": "custom",
                "toggles": {
                    "auto_reports": True,
                    "uncat_prompts": True,
                    "trends_alerts": False,
                    "anomalies_alerts": True,
                    "forecast_alerts": False,
                    "coach_nudges": True,
                },
                "custom_toggles": {
                    "auto_reports": True,
                    "uncat_prompts": True,
                    "trends_alerts": False,
                    "anomalies_alerts": True,
                    "forecast_alerts": False,
                    "coach_nudges": True,
                },
            },
        }
    )
    report_store = DummyReportStore(_facts())
    user = SimpleNamespace(telegram_user_id=1, autojobs_enabled=True, chat_id=777)

    asyncio.run(
        maybe_send_activity_proactive_messages(
            user,
            bot=bot,
            profile_store=profile_store,
            report_store=report_store,
            logger=logging.getLogger("test"),
        )
    )

    assert len(bot.sent) == 2
    texts = [x[1] for x in bot.sent]
    assert any("🚨 Anomaly nudge" in x for x in texts)
    assert any("🧮 Coach nudge" in x for x in texts)
    assert all("📈 Trends nudge" not in x for x in texts)
    assert all("🔮 Forecast nudge" not in x for x in texts)


def test_maybe_send_activity_proactive_messages_skips_when_autojobs_disabled():
    bot = DummyBot()
    profile_store = DummyProfileStore({"activity_mode": "loud"})
    report_store = DummyReportStore(_facts())
    user = SimpleNamespace(telegram_user_id=1, autojobs_enabled=False, chat_id=777)

    asyncio.run(
        maybe_send_activity_proactive_messages(
            user,
            bot=bot,
            profile_store=profile_store,
            report_store=report_store,
            logger=logging.getLogger("test"),
        )
    )

    assert bot.sent == []


def test_build_scheduled_auto_report_text_quiet_returns_none():
    profile_store = DummyProfileStore(
        {
            "activity_mode": "quiet",
            "activity": {
                "mode": "quiet",
                "toggles": {
                    "auto_reports": False,
                    "uncat_prompts": False,
                    "trends_alerts": False,
                    "anomalies_alerts": False,
                    "forecast_alerts": False,
                    "coach_nudges": False,
                },
                "custom_toggles": {
                    "auto_reports": True,
                    "uncat_prompts": True,
                    "trends_alerts": True,
                    "anomalies_alerts": True,
                    "forecast_alerts": True,
                    "coach_nudges": True,
                },
            },
        }
    )
    report_store = DummyReportStore(_facts())
    user = SimpleNamespace(telegram_user_id=1, autojobs_enabled=True, chat_id=777)

    text = build_scheduled_auto_report_text(
        user,
        period="week",
        profile_store=profile_store,
        report_store=report_store,
        render_report_text=lambda user_id,
        period,
        facts: f"{period}:{facts['totals']['real_spend_total_uah']}",
    )

    assert text is None


def test_build_scheduled_auto_report_text_loud_returns_rendered_text():
    profile_store = DummyProfileStore(
        {
            "activity_mode": "loud",
            "activity": {
                "mode": "loud",
                "toggles": {
                    "auto_reports": True,
                    "uncat_prompts": True,
                    "trends_alerts": True,
                    "anomalies_alerts": True,
                    "forecast_alerts": True,
                    "coach_nudges": True,
                },
                "custom_toggles": {
                    "auto_reports": False,
                    "uncat_prompts": False,
                    "trends_alerts": False,
                    "anomalies_alerts": False,
                    "forecast_alerts": False,
                    "coach_nudges": False,
                },
            },
        }
    )
    report_store = DummyReportStore(_facts())
    user = SimpleNamespace(telegram_user_id=1, autojobs_enabled=True, chat_id=777)

    text = build_scheduled_auto_report_text(
        user,
        period="month",
        profile_store=profile_store,
        report_store=report_store,
        render_report_text=lambda user_id,
        period,
        facts: f"REPORT:{period}:{facts['totals']['real_spend_total_uah']}",
    )

    assert text == "REPORT:month:456.0"


def test_build_scheduled_auto_report_text_custom_respects_auto_reports_toggle():
    profile_store = DummyProfileStore(
        {
            "activity_mode": "custom",
            "activity": {
                "mode": "custom",
                "toggles": {
                    "auto_reports": False,
                    "uncat_prompts": True,
                    "trends_alerts": True,
                    "anomalies_alerts": False,
                    "forecast_alerts": False,
                    "coach_nudges": False,
                },
                "custom_toggles": {
                    "auto_reports": False,
                    "uncat_prompts": True,
                    "trends_alerts": True,
                    "anomalies_alerts": False,
                    "forecast_alerts": False,
                    "coach_nudges": False,
                },
            },
        }
    )
    report_store = DummyReportStore(_facts())
    user = SimpleNamespace(telegram_user_id=1, autojobs_enabled=True, chat_id=777)

    text = build_scheduled_auto_report_text(
        user,
        period="week",
        profile_store=profile_store,
        report_store=report_store,
        render_report_text=lambda user_id, period, facts: "SHOULD NOT HAPPEN",
    )

    assert text is None


def test_maybe_send_scheduled_auto_report_sends_when_enabled():
    bot = DummyBot()
    profile_store = DummyProfileStore(
        {
            "activity_mode": "custom",
            "activity": {
                "mode": "custom",
                "toggles": {
                    "auto_reports": True,
                    "uncat_prompts": False,
                    "trends_alerts": False,
                    "anomalies_alerts": True,
                    "forecast_alerts": False,
                    "coach_nudges": True,
                },
                "custom_toggles": {
                    "auto_reports": True,
                    "uncat_prompts": False,
                    "trends_alerts": False,
                    "anomalies_alerts": True,
                    "forecast_alerts": False,
                    "coach_nudges": True,
                },
            },
        }
    )
    report_store = DummyReportStore(_facts())
    user = SimpleNamespace(telegram_user_id=1, autojobs_enabled=True, chat_id=777)

    sent = asyncio.run(
        maybe_send_scheduled_auto_report(
            user,
            period="week",
            bot=bot,
            profile_store=profile_store,
            report_store=report_store,
            render_report_text=lambda user_id, period, facts: f"SEND:{period}",
            logger=logging.getLogger("test"),
        )
    )

    assert sent is True
    assert bot.sent == [(777, "SEND:week", None)]


def test_maybe_send_scheduled_auto_report_skips_when_autojobs_disabled():
    bot = DummyBot()
    profile_store = DummyProfileStore({"activity_mode": "loud"})
    report_store = DummyReportStore(_facts())
    user = SimpleNamespace(telegram_user_id=1, autojobs_enabled=False, chat_id=777)

    sent = asyncio.run(
        maybe_send_scheduled_auto_report(
            user,
            period="month",
            bot=bot,
            profile_store=profile_store,
            report_store=report_store,
            render_report_text=lambda user_id, period, facts: "SEND:month",
            logger=logging.getLogger("test"),
        )
    )

    assert sent is False
    assert bot.sent == []


def test_should_send_proactive_output_rejects_empty_text():
    assert (
        should_send_proactive_output(
            user_id=1,
            kind="activity",
            text="   ",
            now_ts=1000,
        )
        is False
    )


def test_mark_proactive_output_sent_enforces_dedupe_for_same_trigger():
    assert (
        should_send_proactive_output(
            user_id=1,
            kind="activity",
            text="🚨 Anomaly nudge\nWOLT spike",
            now_ts=1000,
        )
        is True
    )

    mark_proactive_output_sent(
        user_id=1,
        kind="activity",
        text="🚨 Anomaly nudge\nWOLT spike",
        now_ts=1000,
    )

    assert (
        should_send_proactive_output(
            user_id=1,
            kind="activity",
            text="🚨 Anomaly nudge\nWOLT spike",
            now_ts=1001,
        )
        is False
    )


def test_mark_proactive_output_sent_does_not_block_different_activity_output_in_same_window():
    mark_proactive_output_sent(
        user_id=1,
        kind="activity",
        text="📈 Trends nudge\nКафе росте",
        now_ts=1000,
    )

    assert (
        should_send_proactive_output(
            user_id=1,
            kind="activity",
            text="🚨 Anomaly nudge\nWOLT spike",
            now_ts=1001,
        )
        is True
    )


def test_mark_proactive_output_sent_enforces_cooldown_for_same_output():
    mark_proactive_output_sent(
        user_id=1,
        kind="activity",
        text="🚨 Anomaly nudge\nWOLT spike",
        now_ts=1000,
    )

    assert (
        should_send_proactive_output(
            user_id=1,
            kind="activity",
            text="🚨 Anomaly nudge\nWOLT spike",
            now_ts=1001,
        )
        is False
    )

    assert (
        should_send_proactive_output(
            user_id=1,
            kind="activity",
            text="🚨 Anomaly nudge\nWOLT spike",
            now_ts=1000 + 6 * 60 * 60 + 1,
        )
        is True
    )


def test_maybe_send_guarded_proactive_output_dedupes_repeated_alert():
    bot = DummyBot()

    first = asyncio.run(
        maybe_send_guarded_proactive_output(
            user_id=1,
            chat_id=777,
            kind="activity",
            text="🚨 Anomaly nudge\nWOLT spike",
            bot=bot,
            logger=logging.getLogger("test"),
            now_ts=1000,
        )
    )
    second = asyncio.run(
        maybe_send_guarded_proactive_output(
            user_id=1,
            chat_id=777,
            kind="activity",
            text="🚨 Anomaly nudge\nWOLT spike",
            bot=bot,
            logger=logging.getLogger("test"),
            now_ts=1001,
        )
    )

    assert first is True
    assert second is False
    assert bot.sent == [(777, "🚨 Anomaly nudge\nWOLT spike", None)]


def test_maybe_send_activity_proactive_messages_applies_cooldown_and_suppresses_repeat(monkeypatch):
    bot = DummyBot()
    profile_store = DummyProfileStore({"activity_mode": "loud"})
    report_store = DummyReportStore(_facts())
    user = SimpleNamespace(telegram_user_id=1, autojobs_enabled=True, chat_id=777)

    monkeypatch.setattr(sched.time, "time", lambda: 1000)
    asyncio.run(
        maybe_send_activity_proactive_messages(
            user,
            bot=bot,
            profile_store=profile_store,
            report_store=report_store,
            logger=logging.getLogger("test"),
        )
    )

    monkeypatch.setattr(sched.time, "time", lambda: 1001)
    asyncio.run(
        maybe_send_activity_proactive_messages(
            user,
            bot=bot,
            profile_store=profile_store,
            report_store=report_store,
            logger=logging.getLogger("test"),
        )
    )

    assert len(bot.sent) == 4


def test_maybe_send_scheduled_auto_report_dedupes_same_period_report(monkeypatch):
    bot = DummyBot()
    profile_store = DummyProfileStore({"activity_mode": "loud"})
    report_store = DummyReportStore(_facts())
    user = SimpleNamespace(telegram_user_id=1, autojobs_enabled=True, chat_id=777)

    monkeypatch.setattr(sched.time, "time", lambda: 2000)
    first = asyncio.run(
        maybe_send_scheduled_auto_report(
            user,
            period="week",
            bot=bot,
            profile_store=profile_store,
            report_store=report_store,
            render_report_text=lambda user_id, period, facts: "WEEK REPORT",
            logger=logging.getLogger("test"),
        )
    )

    monkeypatch.setattr(sched.time, "time", lambda: 2001)
    second = asyncio.run(
        maybe_send_scheduled_auto_report(
            user,
            period="week",
            bot=bot,
            profile_store=profile_store,
            report_store=report_store,
            render_report_text=lambda user_id, period, facts: "WEEK REPORT",
            logger=logging.getLogger("test"),
        )
    )

    assert first is True
    assert second is False
    assert bot.sent == [(777, "WEEK REPORT", None)]
