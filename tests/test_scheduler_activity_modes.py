import asyncio
import logging
from types import SimpleNamespace

from mono_ai_budget_bot.bot.scheduler import (
    build_activity_proactive_messages,
    maybe_send_activity_proactive_messages,
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
