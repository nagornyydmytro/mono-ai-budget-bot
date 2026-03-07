import asyncio
from pathlib import Path
from types import SimpleNamespace

import mono_ai_budget_bot.bot.handlers as handlers
import mono_ai_budget_bot.bot.templates as templates
from mono_ai_budget_bot.storage.tx_store import TxStore
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
    def load(self, telegram_user_id: int):
        return {"preset": "min"}


class DummyReportStore:
    def load(self, telegram_user_id: int, period_key: str):
        return object()


class DummyUncatPendingStore:
    def load(self, telegram_user_id: int):
        return None


class DummyUncatStore:
    pass


class DummyRulesStore:
    pass


def _kb_dump(kb) -> list[list[tuple[str, str]]]:
    return [[(button.text, button.callback_data) for button in row] for row in kb.inline_keyboard]


def _build_dispatcher(
    *,
    cfg: UserConfig | None,
    profile: dict | None,
    tx_store: TxStore,
    sync_user_ledger=None,
):
    dp = DummyDispatcher()
    handlers.register_handlers(
        dp,
        bot=object(),
        settings=SimpleNamespace(openai_api_key=None, openai_model="gpt"),
        users=DummyUserStore(cfg),
        store=DummyReportStore(),
        tx_store=tx_store,
        profile_store=DummyProfileStore(profile),
        taxonomy_store=DummyTaxonomyStore(),
        reports_store=DummyReportsStore(),
        uncat_store=DummyUncatStore(),
        rules_store=DummyRulesStore(),
        uncat_pending_store=DummyUncatPendingStore(),
        user_locks={},
        logger=SimpleNamespace(info=lambda *a, **k: None),
        sync_user_ledger=sync_user_ledger or (lambda *a, **k: None),
        render_report_for_user=lambda *a, **k: "REPORT",
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


def test_menu_personalization_placeholder_guides_back_to_root(tmp_path: Path):
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

    cb_menu_placeholder_sections = dp.callback_query.handlers["cb_menu_placeholder_sections"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data="menu:personalization", message=message)

    asyncio.run(cb_menu_placeholder_sections(query))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.menu_section_placeholder_message("🎛️ *Персоналізація*")
    assert _kb_dump(kb) == [[("⬅️ Назад", "menu:root")]]
    assert query.answer_calls[-1] == (None, False, None)
