import asyncio
from pathlib import Path
from types import SimpleNamespace

import mono_ai_budget_bot.bot.handlers as handlers
import mono_ai_budget_bot.bot.handlers_menu as handlers_menu
import mono_ai_budget_bot.bot.templates as templates
from mono_ai_budget_bot.bot.onboarding_flow import show_data_status
from mono_ai_budget_bot.storage.report_store import ReportStore
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
    def load(self, telegram_user_id: int):
        return {"preset": "min"}


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
):
    dp = DummyDispatcher()
    handlers.register_handlers(
        dp,
        bot=object(),
        settings=SimpleNamespace(openai_api_key=None, openai_model="gpt"),
        users=DummyUserStore(cfg),
        store=store or DummyReportStore(),
        tx_store=tx_store,
        profile_store=DummyProfileStore(profile),
        taxonomy_store=DummyTaxonomyStore(),
        reports_store=DummyReportsStore(),
        uncat_store=uncat_store or DummyUncatStore(),
        rules_store=rules_store or DummyRulesStore(),
        uncat_pending_store=uncat_pending_store or DummyUncatPendingStore(),
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


def test_menu_reports_custom_placeholder_is_stable(tmp_path: Path):
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
    assert text == templates.menu_reports_custom_placeholder_message()
    assert _kb_dump(kb) == [[("⬅️ Назад", "menu:reports")]]
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
