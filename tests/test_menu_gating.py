import asyncio
from pathlib import Path
from types import SimpleNamespace

import mono_ai_budget_bot.bot.handlers as handlers
import mono_ai_budget_bot.bot.handlers_menu as handlers_menu
import mono_ai_budget_bot.bot.templates as templates
import mono_ai_budget_bot.llm.openai_client as openai_client_module
import mono_ai_budget_bot.nlq.memory_store as ms
from mono_ai_budget_bot.bot.onboarding_flow import show_data_status
from mono_ai_budget_bot.reports.config import build_reports_preset
from mono_ai_budget_bot.storage.report_store import ReportStore
from mono_ai_budget_bot.storage.reports_store import ReportsStore
from mono_ai_budget_bot.storage.rules_store import RulesStore
from mono_ai_budget_bot.storage.tx_store import TxStore
from mono_ai_budget_bot.storage.uncat_store import UncatStore
from mono_ai_budget_bot.storage.user_store import UserConfig
from mono_ai_budget_bot.uncat.pending import UncatPendingStore


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
        self.chat = SimpleNamespace(id=user_id)
        self.text = text
        self.answers: list[tuple[str, object | None]] = []

    async def answer(self, text: str, reply_markup=None):
        self.answers.append((text, reply_markup))

    async def edit_text(self, text: str, reply_markup=None):
        self.answers.append((text, reply_markup))


class DummyCallbackQuery:
    def __init__(self, user_id: int, data: str, message: DummyMessage):
        self.from_user = SimpleNamespace(id=user_id)
        self.data = data
        self.message = message
        self.answer_calls: list[tuple[str | None, bool, object | None]] = []

    async def answer(self, text: str | None = None, show_alert: bool = False, reply_markup=None):
        self.answer_calls.append((text, show_alert, reply_markup))


class DummyUserStore:
    def __init__(self, cfg: UserConfig | None):
        self.cfg = cfg

    def save(self, telegram_user_id: int, **kwargs):
        return None

    def load(self, telegram_user_id: int):
        return self.cfg


class DummyProfileStore:
    def __init__(self, profile: dict | None = None):
        self.profile = dict(profile or {})

    def load(self, telegram_user_id: int):
        return dict(self.profile)

    def save(self, telegram_user_id: int, profile: dict):
        self.profile = dict(profile)


class DummyTaxonomyStore:
    def load(self, telegram_user_id: int):
        return {"version": 1}


class DummyReportsStore:
    def __init__(self):
        self.cfg = build_reports_preset("min")

    def load(self, telegram_user_id: int):
        return self.cfg

    def save(self, telegram_user_id: int, cfg):
        self.cfg = cfg


class DummyReportStore:
    def __init__(self, root_dir: Path | None = None):
        self.root_dir = root_dir or Path(".")

    def load(self, telegram_user_id: int, period_key: str):
        return object()


class DummyUncatPendingStore:
    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or Path(".")

    def load(self, telegram_user_id: int):
        return None


class DummyUncatStore:
    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or Path(".")


class DummyRulesStore:
    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or Path(".")

    def load(self, telegram_user_id: int):
        return None


def _kb_dump(kb) -> list[list[tuple[str, str]]]:
    return [[(button.text, button.callback_data) for button in row] for row in kb.inline_keyboard]


def _build_dispatcher(
    *,
    cfg: UserConfig | None,
    profile: dict | None,
    tx_store: TxStore,
    sync_user_ledger=None,
    store=None,
    rules_store=None,
    uncat_store=None,
    uncat_pending_store=None,
    settings=None,
    render_report_for_user=None,
    profile_store=None,
    reports_store=None,
):
    dp = DummyDispatcher()
    handlers.register_handlers(
        dp,
        bot=object(),
        settings=settings or SimpleNamespace(openai_api_key=None, openai_model="gpt"),
        users=DummyUserStore(cfg),
        store=store or DummyReportStore(),
        tx_store=tx_store,
        profile_store=profile_store or DummyProfileStore(profile),
        taxonomy_store=DummyTaxonomyStore(),
        reports_store=reports_store or DummyReportsStore(),
        uncat_store=uncat_store or DummyUncatStore(),
        rules_store=rules_store or DummyRulesStore(),
        uncat_pending_store=uncat_pending_store or DummyUncatPendingStore(),
        user_locks={},
        logger=SimpleNamespace(info=lambda *a, **k: None),
        sync_user_ledger=sync_user_ledger or (lambda *a, **k: None),
        render_report_for_user=render_report_for_user or (lambda *a, **k: "REPORT"),
    )
    return dp


def test_menu_reports_guides_to_finish_onboarding(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    tx_store.update_coverage_window(
        1,
        "acc1",
        coverage_from_ts=1_699_900_000,
        coverage_to_ts=1_700_000_000,
    )

    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={},
        tx_store=tx_store,
    )

    cb_menu_reports = dp.callback_query.handlers["cb_menu_reports"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data="menu:reports", message=message)

    asyncio.run(cb_menu_reports(query))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.menu_finish_onboarding_message()
    assert _kb_dump(kb) == [
        [("➡️ Продовжити онбординг", "onb_resume")],
        [("⬅️ Назад", "onb_back_main")],
    ]
    assert query.answer_calls[-1] == (None, False, None)


def test_menu_reports_guides_to_connect_when_token_missing(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    dp = _build_dispatcher(
        cfg=None,
        profile={"onboarding_completed": True},
        tx_store=tx_store,
    )

    cb_menu_reports = dp.callback_query.handlers["cb_menu_reports"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data="menu:reports", message=message)

    asyncio.run(cb_menu_reports(query))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.menu_missing_token_message()
    assert _kb_dump(kb) == [
        [("🔐 Connect", "menu_connect")],
        [("⬅️ Назад", "menu:root")],
    ]
    assert query.answer_calls[-1] == (None, False, None)


def test_menu_reports_guides_to_accounts_when_selection_missing(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=[],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={"onboarding_completed": True},
        tx_store=tx_store,
    )

    cb_menu_reports = dp.callback_query.handlers["cb_menu_reports"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data="menu:reports", message=message)

    asyncio.run(cb_menu_reports(query))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.menu_missing_accounts_message()
    assert _kb_dump(kb) == [
        [("⚙️ Мої дані", "menu:mydata")],
        [("⬅️ Назад", "menu:root")],
    ]
    assert query.answer_calls[-1] == (None, False, None)


def test_menu_reports_guides_to_refresh_when_ledger_missing(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={"onboarding_completed": True},
        tx_store=tx_store,
    )

    cb_menu_reports = dp.callback_query.handlers["cb_menu_reports"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data="menu:reports", message=message)

    asyncio.run(cb_menu_reports(query))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.menu_missing_ledger_message()
    assert _kb_dump(kb) == [
        [("🔄 Refresh latest", "menu:data:refresh")],
        [("⬅️ Назад", "menu:root")],
    ]
    assert query.answer_calls[-1] == (None, False, None)


def test_refresh_latest_from_guided_gating_runs_even_if_onboarding_not_completed(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    sync_calls: list[tuple[int, int]] = []

    async def fake_sync_user_ledger(telegram_user_id: int, cfg, *, days_back: int):
        sync_calls.append((telegram_user_id, days_back))

    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={},
        tx_store=tx_store,
        sync_user_ledger=fake_sync_user_ledger,
    )

    cb_menu_reports = dp.callback_query.handlers["cb_menu_reports"]
    cb_data_refresh = dp.callback_query.handlers["cb_data_refresh"]

    message = DummyMessage(user_id=1)
    reports_query = DummyCallbackQuery(user_id=1, data="menu:reports", message=message)
    asyncio.run(cb_menu_reports(reports_query))

    assert len(message.answers) == 1
    assert message.answers[0][0] == templates.menu_missing_ledger_message()

    refresh_query = DummyCallbackQuery(user_id=1, data="menu:data:refresh", message=message)
    asyncio.run(cb_data_refresh(refresh_query))

    assert len(message.answers) == 2
    assert message.answers[1][0] == templates.ledger_refresh_progress_message()
    assert refresh_query.answer_calls[-1] == (None, False, None)
    assert sync_calls == [(1, 30)]


def test_menu_root_opens_after_onboarding(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={
            "onboarding_completed": True,
            "activity_mode": "balanced",
            "uncategorized_prompt_frequency": "always",
            "persona": "neutral",
        },
        tx_store=tx_store,
    )

    cb_menu_root = dp.callback_query.handlers["cb_menu_root"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data="menu:root", message=message)

    asyncio.run(cb_menu_root(query))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.menu_root_message()
    assert _kb_dump(kb) == [
        [("📊 Звіти", "menu:reports"), ("💬 Ask", "menu:ask")],
        [("🧩 Uncat", "menu:uncat"), ("🗂️ Категорії", "menu:categories")],
        [("✨ Insights", "menu:insights"), ("🎛️ Персоналізація", "menu:personalization")],
        [("⚙️ Мої дані", "menu:mydata")],
        [("💱 Курси", "menu:currency"), ("📘 Help", "menu:help")],
    ]
    assert query.answer_calls[-1] == (None, False, None)


def test_menu_reports_run_det_uses_existing_report_engine_without_ai(tmp_path: Path):
    captured: dict[str, object] = {}

    class StoreWithFacts:
        def load(self, telegram_user_id: int, period_key: str):
            return SimpleNamespace(
                facts={
                    "totals": {"real_spend_total_uah": 456.0},
                    "coverage": {
                        "coverage_from_ts": 1_700_000_000,
                        "coverage_to_ts": 1_700_086_400,
                        "requested_from_ts": 1_700_000_000,
                        "requested_to_ts": 1_700_086_400,
                    },
                }
            )

    def fake_render_report_for_user(tg_id, period, facts, *, ai_block=None):
        captured["render_period"] = period
        captured["render_facts"] = facts
        captured["ai_block"] = ai_block
        return "REPORT"

    tx_store = TxStore(tmp_path / "tx")
    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={
            "onboarding_completed": True,
            "activity_mode": "balanced",
            "uncategorized_prompt_frequency": "always",
            "persona": "neutral",
        },
        tx_store=tx_store,
        store=StoreWithFacts(),
        render_report_for_user=fake_render_report_for_user,
    )

    cb_menu_run_report_mode = dp.callback_query.handlers["cb_menu_run_report_mode"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data="menu:reports:run:week:det", message=message)

    asyncio.run(cb_menu_run_report_mode(query))

    assert len(message.answers) == 1
    assert message.answers[0][0] == "REPORT"
    assert captured["render_period"] == "week"
    assert captured["render_facts"] == {
        "totals": {"real_spend_total_uah": 456.0},
        "coverage": {
            "coverage_from_ts": 1_700_000_000,
            "coverage_to_ts": 1_700_086_400,
            "requested_from_ts": 1_700_000_000,
            "requested_to_ts": 1_700_086_400,
        },
    }
    assert captured["ai_block"] is None
    assert query.answer_calls[-1] == (None, False, None)


def test_menu_reports_today_opens_mode_picker(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    tx_store.update_coverage_window(
        1,
        "acc1",
        coverage_from_ts=1_699_900_000,
        coverage_to_ts=1_700_000_000,
    )

    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={
            "onboarding_completed": True,
            "activity_mode": "balanced",
            "uncategorized_prompt_frequency": "always",
            "persona": "neutral",
        },
        tx_store=tx_store,
    )

    cb_menu_today = dp.callback_query.handlers["cb_menu_today"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data="menu:reports:today", message=message)

    asyncio.run(cb_menu_today(query))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.menu_reports_mode_message("Today")
    assert _kb_dump(kb) == [
        [("📄 Лише звіт", "menu:reports:run:today:det")],
        [("🤖 З AI-поясненням", "menu:reports:run:today:ai")],
        [("⬅️ Назад", "menu:reports")],
    ]
    assert query.answer_calls[-1] == (None, False, None)


def test_menu_reports_opens_canonical_period_picker_after_onboarding(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    tx_store.update_coverage_window(
        1,
        "acc1",
        coverage_from_ts=1_699_900_000,
        coverage_to_ts=1_700_000_000,
    )

    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={
            "onboarding_completed": True,
            "activity_mode": "balanced",
            "uncategorized_prompt_frequency": "always",
            "persona": "neutral",
        },
        tx_store=tx_store,
    )

    cb_menu_reports = dp.callback_query.handlers["cb_menu_reports"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data="menu:reports", message=message)

    asyncio.run(cb_menu_reports(query))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.menu_reports_message()
    assert _kb_dump(kb) == [
        [("📅 Today", "menu:reports:today")],
        [("📊 Last 7 days", "menu:reports:week")],
        [("🗓️ Last 30 days", "menu:reports:month")],
        [("🛠️ Custom", "menu:reports:custom")],
        [("⬅️ Назад", "menu:root")],
    ]
    assert query.answer_calls[-1] == (None, False, None)


def test_menu_reports_custom_opens_mode_picker(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")

    tx_store = TxStore(tmp_path / "tx")
    tx_store.update_coverage_window(
        1,
        "acc1",
        coverage_from_ts=1_699_900_000,
        coverage_to_ts=1_700_000_000,
    )

    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={
            "onboarding_completed": True,
            "activity_mode": "balanced",
            "uncategorized_prompt_frequency": "always",
            "persona": "neutral",
        },
        tx_store=tx_store,
    )

    cb_menu_reports_custom = dp.callback_query.handlers["cb_menu_reports_custom"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data="menu:reports:custom", message=message)

    asyncio.run(cb_menu_reports_custom(query))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.menu_reports_mode_message("Custom")
    assert _kb_dump(kb) == [
        [("📄 Лише звіт", "menu:reports:custom:det")],
        [("🤖 З AI-поясненням", "menu:reports:custom:ai")],
        [("⬅️ Назад", "menu:reports")],
    ]
    assert query.answer_calls[-1] == (None, False, None)


def test_menu_reports_custom_ai_starts_manual_flow(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")

    tx_store = TxStore(tmp_path / "tx")
    tx_store.update_coverage_window(
        1,
        "acc1",
        coverage_from_ts=1_699_900_000,
        coverage_to_ts=1_700_000_000,
    )

    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={
            "onboarding_completed": True,
            "activity_mode": "balanced",
            "uncategorized_prompt_frequency": "always",
            "persona": "neutral",
        },
        tx_store=tx_store,
    )

    cb_menu_reports_custom_mode = dp.callback_query.handlers["cb_menu_reports_custom_mode"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data="menu:reports:custom:ai", message=message)

    asyncio.run(cb_menu_reports_custom_mode(query))

    mem = ms.load_memory(1)

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.menu_reports_custom_start_prompt()
    assert _kb_dump(kb) == [[("⬅️ Назад", "menu:reports")]]
    assert mem["pending_manual_mode"] == {
        "expected": "report_custom_start",
        "hint": "YYYY-MM-DD",
        "source": "reports_custom",
    }
    assert mem["reports_custom"] == {"want_ai": True}
    assert query.answer_calls[-1] == (None, False, None)


def test_menu_reports_custom_det_starts_manual_flow(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")

    tx_store = TxStore(tmp_path / "tx")
    tx_store.update_coverage_window(
        1,
        "acc1",
        coverage_from_ts=1_699_900_000,
        coverage_to_ts=1_700_000_000,
    )

    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={
            "onboarding_completed": True,
            "activity_mode": "balanced",
            "uncategorized_prompt_frequency": "always",
            "persona": "neutral",
        },
        tx_store=tx_store,
    )

    cb_menu_reports_custom_mode = dp.callback_query.handlers["cb_menu_reports_custom_mode"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data="menu:reports:custom:det", message=message)

    asyncio.run(cb_menu_reports_custom_mode(query))

    mem = ms.load_memory(1)

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.menu_reports_custom_start_prompt()
    assert _kb_dump(kb) == [[("⬅️ Назад", "menu:reports")]]
    assert mem["pending_manual_mode"] == {
        "expected": "report_custom_start",
        "hint": "YYYY-MM-DD",
        "source": "reports_custom",
    }
    assert mem["reports_custom"] == {"want_ai": False}
    assert query.answer_calls[-1] == (None, False, None)


def test_menu_root_blocked_before_onboarding(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={},
        tx_store=tx_store,
    )

    cb_menu_root = dp.callback_query.handlers["cb_menu_root"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data="menu:root", message=message)

    asyncio.run(cb_menu_root(query))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.menu_finish_onboarding_message()
    assert _kb_dump(kb) == [
        [("➡️ Продовжити онбординг", "onb_resume")],
        [("⬅️ Назад", "onb_back_main")],
    ]
    assert query.answer_calls[-1] == (None, False, None)


def test_menu_ask_guides_to_refresh_when_ledger_missing(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={"onboarding_completed": True},
        tx_store=tx_store,
    )

    cb_menu_placeholder_sections = dp.callback_query.handlers["cb_menu_placeholder_sections"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data="menu:ask", message=message)

    asyncio.run(cb_menu_placeholder_sections(query))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.menu_missing_ledger_message()
    assert _kb_dump(kb) == [
        [("🔄 Refresh latest", "menu:data:refresh")],
        [("⬅️ Назад", "menu:root")],
    ]
    assert query.answer_calls[-1] == (None, False, None)


def test_menu_reports_run_ai_uses_aggregated_facts_only(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    class StoreWithFacts:
        def load(self, telegram_user_id: int, period_key: str):
            return SimpleNamespace(
                facts={
                    "totals": {"real_spend_total_uah": 123.0},
                    "coverage": {
                        "coverage_from_ts": 1_700_000_000,
                        "coverage_to_ts": 1_700_086_400,
                        "requested_from_ts": 1_700_000_000,
                        "requested_to_ts": 1_700_086_400,
                    },
                }
            )

    class FakeOpenAIClient:
        def __init__(self, api_key: str, model: str):
            captured["api_key"] = api_key
            captured["model"] = model

        def generate_report_v2(self, system: str, user: str, *, max_tokens: int = 700):
            captured["system"] = system
            captured["user"] = user
            return SimpleNamespace(
                summary="ok",
                changes=["c1"],
                recs=["r1"],
                next_step="n1",
            )

        def close(self):
            return None

    def fake_render_report_for_user(tg_id, period, facts, *, ai_block=None):
        captured["render_period"] = period
        captured["render_facts"] = facts
        captured["ai_block"] = ai_block
        return "REPORT"

    monkeypatch.setattr(openai_client_module, "OpenAIClient", FakeOpenAIClient)

    tx_store = TxStore(tmp_path / "tx")
    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={
            "onboarding_completed": True,
            "activity_mode": "balanced",
            "uncategorized_prompt_frequency": "always",
            "persona": "neutral",
        },
        tx_store=tx_store,
        store=StoreWithFacts(),
        settings=SimpleNamespace(openai_api_key="key", openai_model="gpt"),
        render_report_for_user=fake_render_report_for_user,
    )

    cb_menu_run_report_mode = dp.callback_query.handlers["cb_menu_run_report_mode"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data="menu:reports:run:today:ai", message=message)

    asyncio.run(cb_menu_run_report_mode(query))

    assert len(message.answers) == 2
    assert message.answers[0][0] == templates.ai_insights_progress_message()
    assert message.answers[1][0] == "REPORT"
    assert captured["render_period"] == "today"
    assert captured["render_facts"] == {
        "totals": {"real_spend_total_uah": 123.0},
        "coverage": {
            "coverage_from_ts": 1_700_000_000,
            "coverage_to_ts": 1_700_086_400,
            "requested_from_ts": 1_700_000_000,
            "requested_to_ts": 1_700_086_400,
        },
    }
    assert isinstance(captured["ai_block"], str)
    assert "Факти:" in str(captured["user"])
    assert "raw transactions" not in str(captured["user"])
    assert "description" not in str(captured["user"])
    assert query.answer_calls[-1] == (None, False, None)


def test_menu_reports_run_ai_without_key_falls_back_to_deterministic(tmp_path: Path):
    captured: dict[str, object] = {}

    class StoreWithFacts:
        def load(self, telegram_user_id: int, period_key: str):
            return SimpleNamespace(
                facts={
                    "totals": {"real_spend_total_uah": 321.0},
                    "coverage": {
                        "coverage_from_ts": 1_700_000_000,
                        "coverage_to_ts": 1_700_086_400,
                        "requested_from_ts": 1_700_000_000,
                        "requested_to_ts": 1_700_086_400,
                    },
                }
            )

    def fake_render_report_for_user(tg_id, period, facts, *, ai_block=None):
        captured["render_period"] = period
        captured["render_facts"] = facts
        captured["ai_block"] = ai_block
        return "REPORT"

    tx_store = TxStore(tmp_path / "tx")
    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={
            "onboarding_completed": True,
            "activity_mode": "balanced",
            "uncategorized_prompt_frequency": "always",
            "persona": "neutral",
        },
        tx_store=tx_store,
        store=StoreWithFacts(),
        settings=SimpleNamespace(openai_api_key=None, openai_model="gpt"),
        render_report_for_user=fake_render_report_for_user,
    )

    cb_menu_run_report_mode = dp.callback_query.handlers["cb_menu_run_report_mode"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data="menu:reports:run:month:ai", message=message)

    asyncio.run(cb_menu_run_report_mode(query))

    assert len(message.answers) == 2
    assert message.answers[0][0] == templates.ai_disabled_missing_key_message()
    assert message.answers[1][0] == "REPORT"
    assert captured["render_period"] == "month"
    assert captured["render_facts"] == {
        "totals": {"real_spend_total_uah": 321.0},
        "coverage": {
            "coverage_from_ts": 1_700_000_000,
            "coverage_to_ts": 1_700_086_400,
            "requested_from_ts": 1_700_000_000,
            "requested_to_ts": 1_700_086_400,
        },
    }
    assert captured["ai_block"] is None
    assert query.answer_calls[-1] == (None, False, None)


def test_reports_custom_invalid_order_guides_correction(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")

    tx_store = TxStore(tmp_path / "tx")
    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={
            "onboarding_completed": True,
            "activity_mode": "balanced",
            "uncategorized_prompt_frequency": "always",
            "persona": "neutral",
        },
        tx_store=tx_store,
    )

    mem = ms.load_memory(1)
    mem["reports_custom"] = {
        "start_date": "2026-03-10",
        "start_ts": 1773100800,
    }
    ms.save_memory(1, mem)
    ms.set_pending_manual_mode(
        1,
        expected="report_custom_end",
        hint="YYYY-MM-DD",
        source="reports_custom",
        ttl_sec=900,
    )

    handle_plain_text = dp.message.handlers["handle_plain_text"]
    message = DummyMessage(user_id=1, text="2026-03-01")

    asyncio.run(handle_plain_text(message))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.menu_reports_custom_invalid_order_message(
        "2026-03-10",
        "2026-03-01",
    )
    assert _kb_dump(kb) == [[("⬅️ Назад", "menu:reports")]]

    mem2 = ms.load_memory(1)
    assert mem2["pending_manual_mode"] == {
        "expected": "report_custom_end",
        "hint": "YYYY-MM-DD",
        "source": "reports_custom",
    }


def test_reports_custom_builds_report_after_valid_range(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")

    tx_store = TxStore(tmp_path / "tx")
    tx_store.update_coverage_window(
        1,
        "acc1",
        coverage_from_ts=1772496000,
        coverage_to_ts=1773532800,
    )
    tx_store.append_many(
        1,
        "acc1",
        [
            {
                "id": "tx1",
                "time": 1772755200,
                "account_id": "acc1",
                "amount": -12000,
                "description": "Coffee",
                "mcc": 5814,
                "currencyCode": 980,
            }
        ],
    )

    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={
            "onboarding_completed": True,
            "activity_mode": "balanced",
            "uncategorized_prompt_frequency": "always",
            "persona": "neutral",
        },
        tx_store=tx_store,
    )

    mem = ms.load_memory(1)
    mem["reports_custom"] = {
        "start_date": "2026-03-03",
        "start_ts": 1772496000,
    }
    ms.save_memory(1, mem)
    ms.set_pending_manual_mode(
        1,
        expected="report_custom_end",
        hint="YYYY-MM-DD",
        source="reports_custom",
        ttl_sec=900,
    )

    handle_plain_text = dp.message.handlers["handle_plain_text"]
    message = DummyMessage(user_id=1, text="2026-03-05")

    asyncio.run(handle_plain_text(message))

    assert len(message.answers) == 2
    assert message.answers[0][0] == templates.menu_reports_custom_building_message(
        "2026-03-03", "2026-03-05"
    )
    assert message.answers[1][0] == "REPORT"

    mem2 = ms.load_memory(1)
    assert mem2.get("pending_manual_mode") is None
    assert mem2.get("reports_custom") is None


def test_menu_data_new_token_starts_manual_entry_with_mydata_back(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={
            "onboarding_completed": True,
            "activity_mode": "balanced",
            "uncategorized_prompt_frequency": "always",
            "persona": "neutral",
        },
        tx_store=tx_store,
    )

    captured: dict[str, object] = {}
    original_set_pending_manual_mode = handlers_menu.memory_store.set_pending_manual_mode

    def fake_set_pending_manual_mode(
        tg_id: int,
        *,
        expected: str,
        hint: str,
        source: str,
        ttl_sec: int,
    ) -> None:
        captured["tg_id"] = tg_id
        captured["expected"] = expected
        captured["hint"] = hint
        captured["source"] = source
        captured["ttl_sec"] = ttl_sec

    handlers_menu.memory_store.set_pending_manual_mode = fake_set_pending_manual_mode
    try:
        cb_data_new_token = dp.callback_query.handlers["cb_data_new_token"]
        message = DummyMessage(user_id=1)
        query = DummyCallbackQuery(user_id=1, data="menu:data:new_token", message=message)

        asyncio.run(cb_data_new_token(query))
    finally:
        handlers_menu.memory_store.set_pending_manual_mode = original_set_pending_manual_mode

    assert captured == {
        "tg_id": 1,
        "expected": "mono_token",
        "hint": templates.token_paste_hint_new_token(),
        "source": "data_menu",
        "ttl_sec": 900,
    }
    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.token_paste_prompt_new_token()
    assert _kb_dump(kb) == [[("⬅️ Назад", "menu:mydata")]]
    assert query.answer_calls[-1] == ("", False, None)


def test_menu_data_accounts_opens_picker_and_marks_data_menu_source(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={
            "onboarding_completed": True,
            "activity_mode": "balanced",
            "uncategorized_prompt_frequency": "always",
            "persona": "neutral",
        },
        tx_store=tx_store,
    )

    memory_state: dict[int, dict] = {}

    def fake_load_memory(tg_id: int) -> dict:
        return dict(memory_state.get(tg_id, {}))

    def fake_save_memory(tg_id: int, data: dict) -> None:
        memory_state[tg_id] = dict(data)

    class FakeAccount:
        def __init__(self, acc_id: str, currency_code: int, masked_pan: list[str]):
            self.id = acc_id
            self.currencyCode = currency_code
            self.maskedPan = masked_pan

    class FakeInfo:
        def __init__(self):
            self.accounts = [
                FakeAccount("acc1", 980, ["1111"]),
                FakeAccount("acc2", 840, ["2222"]),
            ]

    class FakeMonobankClient:
        def __init__(self, token: str):
            self.token = token

        def client_info(self):
            return FakeInfo()

        def close(self):
            return None

    original_load_memory = handlers_menu.memory_store.load_memory
    original_save_memory = handlers_menu.memory_store.save_memory
    original_monobank_client = handlers_menu.MonobankClient

    handlers_menu.memory_store.load_memory = fake_load_memory
    handlers_menu.memory_store.save_memory = fake_save_memory
    handlers_menu.MonobankClient = FakeMonobankClient
    try:
        cb_data_accounts = dp.callback_query.handlers["cb_data_accounts"]
        message = DummyMessage(user_id=1)
        query = DummyCallbackQuery(user_id=1, data="menu:data:accounts", message=message)

        asyncio.run(cb_data_accounts(query))
    finally:
        handlers_menu.memory_store.load_memory = original_load_memory
        handlers_menu.memory_store.save_memory = original_save_memory
        handlers_menu.MonobankClient = original_monobank_client

    assert memory_state[1]["accounts_picker"] == {
        "source": "data_menu",
        "prev_selected": ["acc1"],
    }
    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert "💳 Обери рахунки" in text
    assert "Обрано: 1 з 2" in text
    assert _kb_dump(kb) == [
        [("✅ 1111 (980)", "acc_toggle:acc1")],
        [("⬜️ 2222 (840)", "acc_toggle:acc2")],
        [("🧹 Clear", "acc_clear"), ("✅ Done", "acc_done")],
    ]
    assert query.answer_calls[-1] == (None, False, None)


def test_menu_mydata_always_available_after_onboarding(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={
            "onboarding_completed": True,
            "activity_mode": "balanced",
            "uncategorized_prompt_frequency": "always",
            "persona": "neutral",
        },
        tx_store=tx_store,
    )

    cb_menu_data = dp.callback_query.handlers["cb_menu_data"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data="menu:mydata", message=message)

    asyncio.run(cb_menu_data(query))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.menu_data_message()
    assert _kb_dump(kb) == [
        [("🔑 Change token", "menu:data:new_token")],
        [("💳 Change accounts", "menu:data:accounts")],
        [("🔄 Refresh latest", "menu:data:refresh")],
        [("📥 Bootstrap history", "menu:data:bootstrap")],
        [("📊 Status", "menu:data:status")],
        [("🧹 Wipe cache", "menu:data:wipe")],
        [("⬅️ Назад", "menu:root")],
    ]
    assert query.answer_calls[-1] == (None, False, None)


def test_menu_data_status_shows_minimum_summary(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    tx_store.update_coverage_window(
        1,
        "acc1",
        coverage_from_ts=1704067200,
        coverage_to_ts=1706659200,
    )

    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={
            "onboarding_completed": True,
            "activity_mode": "balanced",
            "uncategorized_prompt_frequency": "always",
            "persona": "neutral",
        },
        tx_store=tx_store,
    )

    cb_data_status = dp.callback_query.handlers["cb_data_status"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data="menu:data:status", message=message)

    asyncio.run(cb_data_status(query))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert "Monobank: ✅ connected" in text
    assert "Карток вибрано: 1" in text
    assert "Coverage: 2024-01-01 → 2024-01-31" in text
    assert "Last sync: " in text
    assert _kb_dump(kb) == [[("⬅️ Назад", "menu:mydata")]]
    assert query.answer_calls[-1] == (None, False, None)


def test_data_status_shows_not_connected_state(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    users = DummyUserStore(None)
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data="menu:data:status", message=message)

    asyncio.run(
        show_data_status(
            query,
            tg_id=1,
            users=users,
            tx_store=tx_store,
            status_message_builder=templates.status_message,
            reply_markup=None,
        )
    )

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert "Monobank: ❌ not connected" in text
    assert "Карток вибрано: 0" in text
    assert "Coverage: немає даних" in text
    assert "Last sync: —" in text
    assert kb is None
    assert query.answer_calls[-1] == (None, False, None)


def test_menu_data_bootstrap_opens_standalone_picker(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={
            "onboarding_completed": True,
            "activity_mode": "balanced",
            "uncategorized_prompt_frequency": "always",
            "persona": "neutral",
        },
        tx_store=tx_store,
    )

    cb_data_bootstrap = dp.callback_query.handlers["cb_data_bootstrap"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data="menu:data:bootstrap", message=message)

    asyncio.run(cb_data_bootstrap(query))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.menu_data_bootstrap_message()
    assert _kb_dump(kb) == [
        [("📥 Bootstrap 1 місяць", "boot_30")],
        [("📥 Bootstrap 3 місяці", "boot_90")],
        [("📥 Bootstrap 6 місяців", "boot_180")],
        [("📥 Bootstrap 12 місяців", "boot_365")],
        [("⬅️ Назад", "menu:mydata")],
    ]
    assert query.answer_calls[-1] == (None, False, None)


def test_menu_data_wipe_confirm_screen_renders(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={
            "onboarding_completed": True,
            "activity_mode": "balanced",
            "uncategorized_prompt_frequency": "always",
            "persona": "neutral",
        },
        tx_store=tx_store,
    )

    cb_data_wipe = dp.callback_query.handlers["cb_data_wipe"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data="menu:data:wipe", message=message)

    asyncio.run(cb_data_wipe(query))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.menu_data_wipe_confirm_message()
    assert _kb_dump(kb) == [
        [("✅ Підтвердити", "menu:data:wipe:confirm")],
        [("❌ Скасувати", "menu:data:wipe:cancel")],
    ]
    assert query.answer_calls[-1] == (None, False, None)


def test_menu_data_wipe_confirm_removes_only_financial_cache(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    report_store = ReportStore(root_dir=tmp_path / "reports")
    rules_store = RulesStore(base_dir=tmp_path / "rules")
    uncat_store = UncatStore(base_dir=tmp_path / "uncat")
    uncat_pending_store = UncatPendingStore(base_dir=tmp_path / "uncat_pending")

    (tx_store.root_dir / "1").mkdir(parents=True, exist_ok=True)
    (tx_store.root_dir / "1" / "acc1.jsonl").write_text("{}", encoding="utf-8")
    (tx_store.root_dir / "1" / "_meta.json").write_text("{}", encoding="utf-8")
    (report_store.root_dir / "1").mkdir(parents=True, exist_ok=True)
    (report_store.root_dir / "1" / "facts_week.json").write_text("{}", encoding="utf-8")
    (rules_store.base_dir / "1.json").write_text("{}", encoding="utf-8")
    (uncat_store.base_dir / "1.json").write_text("{}", encoding="utf-8")
    (uncat_pending_store.base_dir / "1.json").write_text("{}", encoding="utf-8")

    cfg = UserConfig(
        telegram_user_id=1,
        mono_token="token",
        selected_account_ids=["acc1"],
        chat_id=None,
        autojobs_enabled=False,
        updated_at=0.0,
    )

    dp = _build_dispatcher(
        cfg=cfg,
        profile={
            "onboarding_completed": True,
            "activity_mode": "balanced",
            "uncategorized_prompt_frequency": "always",
            "persona": "neutral",
        },
        tx_store=tx_store,
        store=report_store,
        rules_store=rules_store,
        uncat_store=uncat_store,
        uncat_pending_store=uncat_pending_store,
    )

    cb_data_wipe_confirm = dp.callback_query.handlers["cb_data_wipe_confirm"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data="menu:data:wipe:confirm", message=message)

    asyncio.run(cb_data_wipe_confirm(query))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.menu_data_wipe_done_message()
    assert _kb_dump(kb) == [[("⬅️ Назад", "menu:mydata")]]
    assert query.answer_calls[-1] == (None, False, None)

    assert not (tx_store.root_dir / "1").exists()
    assert not (report_store.root_dir / "1").exists()
    assert not (rules_store.base_dir / "1.json").exists()
    assert not (uncat_store.base_dir / "1.json").exists()
    assert not (uncat_pending_store.base_dir / "1.json").exists()
    assert cfg.mono_token == "token"
    assert cfg.selected_account_ids == ["acc1"]


def test_menu_data_wipe_cancel_returns_to_mydata(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={
            "onboarding_completed": True,
            "activity_mode": "balanced",
            "uncategorized_prompt_frequency": "always",
            "persona": "neutral",
        },
        tx_store=tx_store,
    )

    cb_data_wipe_cancel = dp.callback_query.handlers["cb_data_wipe_cancel"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data="menu:data:wipe:cancel", message=message)

    asyncio.run(cb_data_wipe_cancel(query))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.menu_data_message()
    assert _kb_dump(kb) == [
        [("🔑 Change token", "menu:data:new_token")],
        [("💳 Change accounts", "menu:data:accounts")],
        [("🔄 Refresh latest", "menu:data:refresh")],
        [("📥 Bootstrap history", "menu:data:bootstrap")],
        [("📊 Status", "menu:data:status")],
        [("🧹 Wipe cache", "menu:data:wipe")],
        [("⬅️ Назад", "menu:root")],
    ]
    assert query.answer_calls[-1] == (None, False, None)


def test_menu_categories_action_placeholder_renders_consistent_screen(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={
            "onboarding_completed": True,
            "activity_mode": "balanced",
            "uncategorized_prompt_frequency": "always",
            "persona": "neutral",
        },
        tx_store=tx_store,
    )

    cb_menu_categories_placeholders = dp.callback_query.handlers["cb_menu_categories_placeholders"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data="menu:categories:add", message=message)

    asyncio.run(cb_menu_categories_placeholders(query))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.menu_categories_action_placeholder_message()
    assert _kb_dump(kb) == [[("⬅️ Назад", "menu:categories")]]
    assert query.answer_calls[-1] == (None, False, None)


def test_menu_personalization_opens_canonical_submenu(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={
            "onboarding_completed": True,
            "activity_mode": "quiet",
            "uncategorized_prompt_frequency": "before_report",
            "persona": "rational",
        },
        tx_store=tx_store,
    )

    cb_menu_personalization = dp.callback_query.handlers["cb_menu_personalization"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data="menu:personalization", message=message)

    asyncio.run(cb_menu_personalization(query))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.menu_personalization_message(
        persona_label="Rational",
        activity_label="Quiet",
        reports_label="Min",
        uncat_label="Перед звітом",
        ai_label="AI explanations ON",
    )
    assert _kb_dump(kb) == [
        [("🧑 Persona", "menu:personalization:persona")],
        [("⚡ Activity mode", "menu:personalization:activity")],
        [("🧩 Report blocks", "menu:personalization:reports")],
        [("🧾 Uncategorized prompts", "menu:personalization:uncat")],
        [("🤖 AI features", "menu:personalization:ai")],
        [("⬅️ Назад", "menu:root")],
    ]
    assert query.answer_calls[-1] == (None, False, None)


def test_menu_personalization_item_reads_from_profile_store(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={
            "onboarding_completed": True,
            "activity_mode": "quiet",
            "uncategorized_prompt_frequency": "before_report",
            "persona": "rational",
            "ai_features": {"report_explanations": False},
            "reports_preset": "custom",
        },
        tx_store=tx_store,
    )

    cb_menu_personalization_items = dp.callback_query.handlers["cb_menu_personalization_items"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(
        user_id=1,
        data="menu:personalization:ai",
        message=message,
    )

    asyncio.run(cb_menu_personalization_items(query))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.menu_personalization_item_message(
        title="🤖 *AI features*",
        current_value="AI explanations OFF",
    )
    assert _kb_dump(kb) == [[("⬅️ Назад", "menu:personalization")]]
    assert query.answer_calls[-1] == (None, False, None)


def test_menu_personalization_activity_opens_mode_screen(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={
            "onboarding_completed": True,
            "activity_mode": "quiet",
            "uncategorized_prompt_frequency": "before_report",
            "persona": "rational",
        },
        tx_store=tx_store,
    )

    cb_menu_personalization_items = dp.callback_query.handlers["cb_menu_personalization_items"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(
        user_id=1,
        data="menu:personalization:activity",
        message=message,
    )

    asyncio.run(cb_menu_personalization_items(query))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.menu_activity_mode_message("Quiet")
    assert _kb_dump(kb) == [
        [("⬜️ Loud", "menu:personalization:activity:loud")],
        [("✅ Quiet", "menu:personalization:activity:quiet")],
        [("⬜️ Custom", "menu:personalization:activity:custom")],
        [("⬅️ Назад", "menu:personalization")],
    ]
    assert query.answer_calls[-1] == (None, False, None)


def test_menu_personalization_activity_quiet_preserves_custom_flags(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    profile_store = DummyProfileStore(
        {
            "onboarding_completed": True,
            "activity_mode": "custom",
            "uncategorized_prompt_frequency": "before_report",
            "persona": "rational",
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
    )

    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile=None,
        tx_store=tx_store,
        profile_store=profile_store,
    )

    cb_menu_personalization_activity_mode = dp.callback_query.handlers[
        "cb_menu_personalization_activity_mode"
    ]

    message = DummyMessage(user_id=1)
    query_quiet = DummyCallbackQuery(
        user_id=1,
        data="menu:personalization:activity:quiet",
        message=message,
    )
    asyncio.run(cb_menu_personalization_activity_mode(query_quiet))

    assert profile_store.profile["activity_mode"] == "quiet"
    assert profile_store.profile["activity"]["toggles"]["auto_reports"] is False
    assert profile_store.profile["activity"]["toggles"]["uncat_prompts"] is False
    assert profile_store.profile["activity"]["custom_toggles"]["auto_reports"] is True
    assert profile_store.profile["activity"]["custom_toggles"]["forecast_alerts"] is True

    query_custom = DummyCallbackQuery(
        user_id=1,
        data="menu:personalization:activity:custom",
        message=message,
    )
    asyncio.run(cb_menu_personalization_activity_mode(query_custom))

    assert profile_store.profile["activity_mode"] == "custom"
    assert len(message.answers) == 2
    text2, kb2 = message.answers[1]
    assert text2 == templates.menu_activity_custom_message()
    assert _kb_dump(kb2) == [
        [("✅ Auto reports", "menu:personalization:activity:toggle:auto_reports")],
        [("✅ Uncategorized prompts", "menu:personalization:activity:toggle:uncat_prompts")],
        [("✅ Trend nudges", "menu:personalization:activity:toggle:trends_alerts")],
        [("❌ Anomaly nudges", "menu:personalization:activity:toggle:anomalies_alerts")],
        [("✅ Forecast nudges", "menu:personalization:activity:toggle:forecast_alerts")],
        [("❌ Coach nudges", "menu:personalization:activity:toggle:coach_nudges")],
        [("⬅️ Назад", "menu:personalization:activity")],
    ]


def test_menu_personalization_activity_toggle_updates_custom_flags(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    profile_store = DummyProfileStore(
        {
            "onboarding_completed": True,
            "activity_mode": "custom",
            "uncategorized_prompt_frequency": "before_report",
            "persona": "rational",
            "activity": {
                "mode": "custom",
                "toggles": {
                    "auto_reports": True,
                    "uncat_prompts": True,
                    "trends_alerts": False,
                    "anomalies_alerts": False,
                    "forecast_alerts": False,
                    "coach_nudges": False,
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
    )

    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile=None,
        tx_store=tx_store,
        profile_store=profile_store,
    )

    cb_menu_personalization_activity_toggle = dp.callback_query.handlers[
        "cb_menu_personalization_activity_toggle"
    ]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(
        user_id=1,
        data="menu:personalization:activity:toggle:forecast_alerts",
        message=message,
    )

    asyncio.run(cb_menu_personalization_activity_toggle(query))

    assert profile_store.profile["activity_mode"] == "custom"
    assert profile_store.profile["activity"]["toggles"]["forecast_alerts"] is True
    assert profile_store.profile["activity"]["custom_toggles"]["forecast_alerts"] is True
    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.menu_activity_custom_message()
    assert _kb_dump(kb)[4] == [
        ("✅ Forecast nudges", "menu:personalization:activity:toggle:forecast_alerts")
    ]
    assert query.answer_calls[-1] == (None, False, None)


def test_menu_personalization_uncat_opens_frequency_screen(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={
            "onboarding_completed": True,
            "activity_mode": "quiet",
            "uncategorized_prompt_frequency": "before_report",
            "persona": "rational",
        },
        tx_store=tx_store,
    )

    cb_menu_personalization_items = dp.callback_query.handlers["cb_menu_personalization_items"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(
        user_id=1,
        data="menu:personalization:uncat",
        message=message,
    )

    asyncio.run(cb_menu_personalization_items(query))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.menu_uncat_frequency_message("Перед звітом")
    assert _kb_dump(kb) == [
        [("⬜️ Одразу", "menu:personalization:uncat:immediate")],
        [("⬜️ Раз на день", "menu:personalization:uncat:daily")],
        [("⬜️ Раз на тиждень", "menu:personalization:uncat:weekly")],
        [("✅ Перед звітом", "menu:personalization:uncat:before_report")],
        [("⬅️ Назад", "menu:personalization")],
    ]
    assert query.answer_calls[-1] == (None, False, None)


def test_menu_personalization_uncat_frequency_updates_shared_profile_setting(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    profile_store = DummyProfileStore(
        {
            "onboarding_completed": True,
            "activity_mode": "quiet",
            "uncategorized_prompt_frequency": "before_report",
            "persona": "rational",
        }
    )

    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile=None,
        tx_store=tx_store,
        profile_store=profile_store,
    )

    cb_menu_personalization_uncat_frequency = dp.callback_query.handlers[
        "cb_menu_personalization_uncat_frequency"
    ]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(
        user_id=1,
        data="menu:personalization:uncat:daily",
        message=message,
    )

    asyncio.run(cb_menu_personalization_uncat_frequency(query))

    assert profile_store.profile["uncategorized_prompt_frequency"] == "daily"
    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.menu_uncat_frequency_message("Раз на день")
    assert _kb_dump(kb) == [
        [("⬜️ Одразу", "menu:personalization:uncat:immediate")],
        [("✅ Раз на день", "menu:personalization:uncat:daily")],
        [("⬜️ Раз на тиждень", "menu:personalization:uncat:weekly")],
        [("⬜️ Перед звітом", "menu:personalization:uncat:before_report")],
        [("⬅️ Назад", "menu:personalization")],
    ]
    assert query.answer_calls[-1] == (None, False, None)


def test_menu_personalization_reports_opens_preset_screen(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    reports_store = ReportsStore(base_dir=tmp_path / "reports_cfg")
    reports_store.save(1, build_reports_preset("max"))

    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={
            "onboarding_completed": True,
            "activity_mode": "quiet",
            "uncategorized_prompt_frequency": "before_report",
            "persona": "rational",
        },
        tx_store=tx_store,
        reports_store=reports_store,
    )

    cb_menu_personalization_items = dp.callback_query.handlers["cb_menu_personalization_items"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(
        user_id=1,
        data="menu:personalization:reports",
        message=message,
    )

    asyncio.run(cb_menu_personalization_items(query))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.menu_reports_preset_message("Max")
    assert _kb_dump(kb) == [
        [("⚡ Min", "menu:personalization:reports:min")],
        [("🧠 Max", "menu:personalization:reports:max")],
        [("🛠️ Custom", "menu:personalization:reports:custom")],
        [("⬅️ Назад", "menu:personalization")],
    ]
    assert query.answer_calls[-1] == (None, False, None)


def test_menu_personalization_reports_max_updates_store_and_profile(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    reports_store = ReportsStore(base_dir=tmp_path / "reports_cfg")
    profile_store = DummyProfileStore(
        {
            "onboarding_completed": True,
            "activity_mode": "quiet",
            "uncategorized_prompt_frequency": "before_report",
            "persona": "rational",
            "reports_preset": "min",
        }
    )

    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile=None,
        tx_store=tx_store,
        reports_store=reports_store,
        profile_store=profile_store,
    )

    cb_menu_personalization_reports_preset = dp.callback_query.handlers[
        "cb_menu_personalization_reports_preset"
    ]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(
        user_id=1,
        data="menu:personalization:reports:max",
        message=message,
    )

    asyncio.run(cb_menu_personalization_reports_preset(query))

    cfg = reports_store.load(1)

    assert cfg.preset == "max"
    assert profile_store.profile["reports_preset"] == "max"
    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.menu_reports_preset_message("Max")
    assert _kb_dump(kb) == [
        [("⚡ Min", "menu:personalization:reports:min")],
        [("🧠 Max", "menu:personalization:reports:max")],
        [("🛠️ Custom", "menu:personalization:reports:custom")],
        [("⬅️ Назад", "menu:personalization")],
    ]
    assert query.answer_calls[-1] == (None, False, None)


def test_menu_personalization_reports_custom_opens_block_toggles(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    reports_store = ReportsStore(base_dir=tmp_path / "reports_cfg")
    profile_store = DummyProfileStore(
        {
            "onboarding_completed": True,
            "activity_mode": "quiet",
            "uncategorized_prompt_frequency": "before_report",
            "persona": "rational",
            "reports_preset": "min",
        }
    )

    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=["acc1"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile=None,
        tx_store=tx_store,
        reports_store=reports_store,
        profile_store=profile_store,
    )

    cb_menu_personalization_reports_preset = dp.callback_query.handlers[
        "cb_menu_personalization_reports_preset"
    ]
    cb_menu_personalization_reports_period = dp.callback_query.handlers[
        "cb_menu_personalization_reports_period"
    ]
    cb_menu_personalization_reports_toggle = dp.callback_query.handlers[
        "cb_menu_personalization_reports_toggle"
    ]
    message = DummyMessage(user_id=1)

    query_custom = DummyCallbackQuery(
        user_id=1,
        data="menu:personalization:reports:custom",
        message=message,
    )
    asyncio.run(cb_menu_personalization_reports_preset(query_custom))

    cfg1 = reports_store.load(1)
    assert cfg1.preset == "custom"
    assert profile_store.profile["reports_preset"] == "custom"
    assert len(message.answers) == 1
    assert message.answers[0][0] == templates.menu_reports_custom_period_message()

    query_period = DummyCallbackQuery(
        user_id=1,
        data="menu:personalization:reports:period:monthly",
        message=message,
    )
    asyncio.run(cb_menu_personalization_reports_period(query_period))

    assert len(message.answers) == 2
    text2, kb2 = message.answers[1]
    assert text2 == templates.menu_reports_custom_blocks_message("monthly")
    assert _kb_dump(kb2) == [
        [("✅ Факти (суми/оборот)", "menu:personalization:reports:toggle:monthly:totals")],
        [
            (
                "✅ Розбивки (категорії/мерчанти)",
                "menu:personalization:reports:toggle:monthly:breakdowns",
            )
        ],
        [("✅ Тренди", "menu:personalization:reports:toggle:monthly:trends")],
        [("✅ Аномалії", "menu:personalization:reports:toggle:monthly:anomalies")],
        [("✅ What-if", "menu:personalization:reports:toggle:monthly:what_if")],
        [("⬅️ Назад", "menu:personalization:reports:custom")],
    ]

    query_toggle = DummyCallbackQuery(
        user_id=1,
        data="menu:personalization:reports:toggle:monthly:anomalies",
        message=message,
    )
    asyncio.run(cb_menu_personalization_reports_toggle(query_toggle))

    cfg2 = reports_store.load(1)
    assert cfg2.preset == "custom"
    assert cfg2.monthly["anomalies"] is False
    assert profile_store.profile["reports_preset"] == "custom"
    assert len(message.answers) == 3
    text3, kb3 = message.answers[2]
    assert text3 == templates.menu_reports_custom_blocks_message("monthly")
    assert _kb_dump(kb3) == [
        [("✅ Факти (суми/оборот)", "menu:personalization:reports:toggle:monthly:totals")],
        [
            (
                "✅ Розбивки (категорії/мерчанти)",
                "menu:personalization:reports:toggle:monthly:breakdowns",
            )
        ],
        [("✅ Тренди", "menu:personalization:reports:toggle:monthly:trends")],
        [("❌ Аномалії", "menu:personalization:reports:toggle:monthly:anomalies")],
        [("✅ What-if", "menu:personalization:reports:toggle:monthly:what_if")],
        [("⬅️ Назад", "menu:personalization:reports:custom")],
    ]
