import asyncio
from pathlib import Path
from types import SimpleNamespace

import mono_ai_budget_bot.bot.handlers as handlers
import mono_ai_budget_bot.bot.templates as templates
import mono_ai_budget_bot.nlq.memory_store as ms
from mono_ai_budget_bot.reports.config import build_reports_preset
from mono_ai_budget_bot.reports.renderer import render_report_for_user
from mono_ai_budget_bot.storage.report_store import StoredReport
from mono_ai_budget_bot.storage.reports_store import ReportsStore
from mono_ai_budget_bot.storage.user_store import UserConfig


class DummyRegistry:
    def __init__(self):
        self.handlers = {}

    def __call__(self, *args, **kwargs):
        def decorator(func):
            self.handlers[func.__name__] = func
            return func

        return decorator


class DummyDispatcher:
    def __init__(self):
        self.message = DummyRegistry()
        self.callback_query = DummyRegistry()


class DummyMessage:
    def __init__(self, user_id: int, text: str = ""):
        self.from_user = SimpleNamespace(id=user_id)
        self.text = text
        self.answers: list[tuple[str, object | None]] = []
        self.reply_markup_edits: list[object | None] = []

    async def answer(self, text: str, reply_markup=None):
        self.answers.append((text, reply_markup))

    async def edit_reply_markup(self, reply_markup=None):
        self.reply_markup_edits.append(reply_markup)


class DummyCallbackQuery:
    def __init__(self, user_id: int, data: str, message: DummyMessage):
        self.from_user = SimpleNamespace(id=user_id)
        self.data = data
        self.message = message
        self.answer_calls: list[tuple[str | None, bool]] = []

    async def answer(self, text: str | None = None, show_alert: bool = False):
        self.answer_calls.append((text, show_alert))


class DummyUserStore:
    def load(self, telegram_user_id: int):
        return UserConfig(
            telegram_user_id=telegram_user_id,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        )


class DummyProfileStore:
    def __init__(self):
        self.data = {
            "activity_mode": "quiet",
            "uncategorized_prompt_frequency": "before_report",
            "persona": "rational",
            "onboarding_completed": True,
        }

    def load(self, telegram_user_id: int):
        return dict(self.data)

    def save(self, telegram_user_id: int, profile: dict):
        self.data = dict(profile)


class DummyTaxonomyStore:
    def load(self, telegram_user_id: int):
        return {"version": 1}


class DummyReportsStore:
    def load(self, telegram_user_id: int):
        return {"preset": "min"}


class DummyUncatPendingStore:
    def load(self, telegram_user_id: int):
        return None


class DummyUncatStore:
    pass


class DummyRulesStore:
    pass


class DummyReportStoreMissingCoverage:
    def load(self, telegram_user_id: int, period_key: str):
        return StoredReport(
            period=period_key,
            generated_at=0.0,
            facts={
                "totals": {
                    "real_spend_total_uah": 111.0,
                    "spend_total_uah": 111.0,
                    "income_total_uah": 0.0,
                    "transfer_in_total_uah": 0.0,
                    "transfer_out_total_uah": 0.0,
                },
                "coverage": {
                    "coverage_from_ts": 500,
                    "coverage_to_ts": 600,
                    "requested_from_ts": 100,
                    "requested_to_ts": 200,
                },
            },
        )


def test_full_coverage_report_has_no_warning(tmp_path: Path) -> None:
    reports_store = ReportsStore(tmp_path / "reports_cfg")
    reports_store.save(1, build_reports_preset("minimal"))

    facts = {
        "totals": {
            "real_spend_total_uah": 1000.0,
            "spend_total_uah": 1200.0,
            "income_total_uah": 300.0,
            "transfer_in_total_uah": 50.0,
            "transfer_out_total_uah": 20.0,
        },
        "coverage": {
            "coverage_from_ts": 100,
            "coverage_to_ts": 400,
            "requested_from_ts": 150,
            "requested_to_ts": 350,
        },
    }

    text = render_report_for_user(reports_store, 1, "week", facts)

    assert "📊 Останні 7 днів" in text
    assert "⚠️ Дані неповні для запитаного періоду." not in text
    assert "Coverage:" not in text
    assert "💸 Реальні витрати" in text


def test_partial_coverage_report_has_warning_in_header_area(tmp_path: Path) -> None:
    reports_store = ReportsStore(tmp_path / "reports_cfg")
    reports_store.save(1, build_reports_preset("minimal"))

    facts = {
        "totals": {
            "real_spend_total_uah": 1000.0,
            "spend_total_uah": 1200.0,
            "income_total_uah": 300.0,
            "transfer_in_total_uah": 50.0,
            "transfer_out_total_uah": 20.0,
        },
        "coverage": {
            "coverage_from_ts": 200,
            "coverage_to_ts": 300,
            "requested_from_ts": 100,
            "requested_to_ts": 400,
        },
    }

    text = render_report_for_user(reports_store, 1, "week", facts)

    assert "📊 Останні 7 днів" in text
    assert "⚠️ Дані неповні для запитаного періоду." in text
    assert "Coverage:" in text
    assert "💸 Реальні витрати" in text


def test_missing_coverage_menu_report_goes_to_sync_cta_and_not_fake_report(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")

    dp = DummyDispatcher()
    fake_render_calls: list[tuple[int, str]] = []

    def fake_render_report_for_user(*args, **kwargs):
        fake_render_calls.append((args[1], args[2]))
        return "FAKE REPORT"

    handlers.register_handlers(
        dp,
        bot=object(),
        settings=SimpleNamespace(openai_api_key=None, openai_model="gpt"),
        users=DummyUserStore(),
        store=DummyReportStoreMissingCoverage(),
        tx_store=object(),
        profile_store=DummyProfileStore(),
        taxonomy_store=DummyTaxonomyStore(),
        reports_store=DummyReportsStore(),
        uncat_store=DummyUncatStore(),
        rules_store=DummyRulesStore(),
        uncat_pending_store=DummyUncatPendingStore(),
        user_locks={},
        logger=SimpleNamespace(info=lambda *a, **k: None),
        sync_user_ledger=lambda *a, **k: None,
        render_report_for_user=fake_render_report_for_user,
    )

    cb_menu_week = dp.callback_query.handlers["cb_menu_week"]

    message = DummyMessage(user_id=1, text="")
    query = DummyCallbackQuery(user_id=1, data="menu_week", message=message)

    asyncio.run(cb_menu_week(query))

    assert fake_render_calls == []
    assert len(message.answers) == 1

    text, reply_markup = message.answers[0]
    assert text == templates.warning("Немає даних для запитаного періоду.")
    assert reply_markup is not None
    assert "FAKE REPORT" not in text

    mem = ms.load_memory(1)
    assert mem.get("pending_intent") == {
        "action": "coverage_sync",
        "days_back": 7,
    }
    assert isinstance(mem.get("pending_id"), str) and mem.get("pending_id")
    assert query.answer_calls[-1] == (None, False)
