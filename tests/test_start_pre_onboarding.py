import asyncio
from types import SimpleNamespace

import mono_ai_budget_bot.bot.handlers as handlers
import mono_ai_budget_bot.bot.templates as templates
from mono_ai_budget_bot.bot.ui import build_start_menu_keyboard
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

    async def answer(
        self,
        text: str | None = None,
        show_alert: bool = False,
        reply_markup=None,
    ):
        self.answer_calls.append((text, show_alert, reply_markup))


class DummyUserStore:
    def __init__(self, cfg: UserConfig | None):
        self.cfg = cfg
        self.saved_chat_ids: list[int] = []

    def save(self, telegram_user_id: int, **kwargs):
        chat_id = kwargs.get("chat_id")
        if isinstance(chat_id, int):
            self.saved_chat_ids.append(chat_id)
        if self.cfg is None:
            self.cfg = UserConfig(
                telegram_user_id=telegram_user_id,
                mono_token=None,
                selected_account_ids=[],
                chat_id=chat_id,
                autojobs_enabled=False,
                updated_at=0.0,
            )
            return
        self.cfg = UserConfig(
            telegram_user_id=self.cfg.telegram_user_id,
            mono_token=kwargs.get("mono_token", self.cfg.mono_token),
            selected_account_ids=kwargs.get("selected_account_ids", self.cfg.selected_account_ids),
            chat_id=chat_id if isinstance(chat_id, int) else self.cfg.chat_id,
            autojobs_enabled=self.cfg.autojobs_enabled,
            updated_at=self.cfg.updated_at,
        )

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
    def __init__(self, value=None):
        self.value = value

    def load(self, telegram_user_id: int):
        return self.value


class DummyReportsStore:
    def __init__(self, value=None):
        self.value = value

    def load(self, telegram_user_id: int):
        return self.value


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


class DummyMonoAccount:
    def __init__(self, account_id: str, currency_code: int, masked_pan: list[str]):
        self.id = account_id
        self.currencyCode = currency_code
        self.maskedPan = masked_pan


class DummyMonoInfo:
    def __init__(self, accounts):
        self.accounts = accounts


class DummyMonobankClient:
    def __init__(self, token: str):
        self.token = token

    def client_info(self):
        return DummyMonoInfo(
            [
                DummyMonoAccount(
                    account_id="acc1",
                    currency_code=980,
                    masked_pan=["4444********1111"],
                )
            ]
        )

    def close(self):
        return None


def _kb_dump(kb) -> list[list[tuple[str, str]]]:
    return [[(b.text, b.callback_data) for b in row] for row in kb.inline_keyboard]


def _build_dispatcher(
    *,
    cfg: UserConfig | None,
    profile: dict | None = None,
    taxonomy=None,
    reports=None,
):
    dp = DummyDispatcher()
    handlers.register_handlers(
        dp,
        bot=object(),
        settings=SimpleNamespace(openai_api_key=None, openai_model="gpt"),
        users=DummyUserStore(cfg),
        store=DummyReportStore(),
        tx_store=object(),
        profile_store=DummyProfileStore(profile),
        taxonomy_store=DummyTaxonomyStore(taxonomy),
        reports_store=DummyReportsStore(reports),
        uncat_store=DummyUncatStore(),
        rules_store=DummyRulesStore(),
        uncat_pending_store=DummyUncatPendingStore(),
        user_locks={},
        logger=SimpleNamespace(info=lambda *a, **k: None),
        sync_user_ledger=lambda *a, **k: None,
        render_report_for_user=lambda *a, **k: "REPORT",
    )
    return dp


def test_start_before_onboarding_shows_only_canonical_pre_onboarding_keyboard():
    dp = _build_dispatcher(cfg=None)

    cmd_start = dp.message.handlers["cmd_start"]
    message = DummyMessage(user_id=1)

    asyncio.run(cmd_start(message))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.start_message()
    assert _kb_dump(kb) == _kb_dump(build_start_menu_keyboard())


def test_start_keyboard_callbacks_match_registered_pre_onboarding_handlers():
    kb = build_start_menu_keyboard()
    rows = _kb_dump(kb)

    assert rows[0][0][1] == "menu_connect"
    assert rows[0][1][1] == "menu:help"
    assert rows[1][0][1] == "menu:currency"


def test_start_with_token_but_incomplete_onboarding_keeps_pre_onboarding_keyboard():
    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=[],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={},
        taxonomy=None,
        reports=None,
    )

    cmd_start = dp.message.handlers["cmd_start"]
    message = DummyMessage(user_id=1)

    asyncio.run(cmd_start(message))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.start_message_connected()
    assert _kb_dump(kb) == _kb_dump(build_start_menu_keyboard())


def test_menu_connect_resumes_onboarding_when_token_exists_but_not_completed(monkeypatch):
    monkeypatch.setattr(handlers, "MonobankClient", DummyMonobankClient)
    monkeypatch.setattr(handlers, "CallbackQuery", DummyCallbackQuery)

    dp = _build_dispatcher(
        cfg=UserConfig(
            telegram_user_id=1,
            mono_token="token",
            selected_account_ids=[],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        ),
        profile={},
        taxonomy=None,
        reports=None,
    )

    cb_menu_connect = dp.callback_query.handlers["cb_menu_connect"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data="menu_connect", message=message)

    asyncio.run(cb_menu_connect(query))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert templates.connect_instructions() not in text
    assert templates.connect_success_confirm() in text
    assert "💳 Обери рахунки" in text
    assert kb is not None
    assert query.answer_calls[-1] == (None, False, None)


def test_menu_help_is_available_before_onboarding_completion():
    dp = _build_dispatcher(cfg=None)

    cb_menu_help = dp.callback_query.handlers["cb_menu_help"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data="menu:help", message=message)

    asyncio.run(cb_menu_help(query))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.help_message()
    assert _kb_dump(kb) == [[("⬅️ Назад", "onb_back_main")]]
    assert query.answer_calls[-1] == (None, False, None)
