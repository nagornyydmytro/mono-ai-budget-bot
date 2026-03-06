import asyncio
from types import SimpleNamespace

import mono_ai_budget_bot.bot.handlers as handlers
import mono_ai_budget_bot.bot.templates as templates
import mono_ai_budget_bot.nlq.memory_store as ms
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
    def __init__(self, cfg: UserConfig | None = None):
        self.cfg = cfg

    def save(self, telegram_user_id: int, **kwargs):
        existing_ids: list[str] = []
        existing_chat_id = None
        existing_autojobs = False
        existing_updated_at = 0.0
        existing_token = None

        if self.cfg is not None:
            existing_ids = list(self.cfg.selected_account_ids)
            existing_chat_id = self.cfg.chat_id
            existing_autojobs = self.cfg.autojobs_enabled
            existing_updated_at = self.cfg.updated_at
            existing_token = self.cfg.mono_token

        self.cfg = UserConfig(
            telegram_user_id=telegram_user_id,
            mono_token=kwargs.get("mono_token", existing_token),
            selected_account_ids=kwargs.get("selected_account_ids", existing_ids),
            chat_id=kwargs.get("chat_id", existing_chat_id),
            autojobs_enabled=kwargs.get("autojobs_enabled", existing_autojobs),
            updated_at=kwargs.get("updated_at", existing_updated_at),
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

    def save(self, telegram_user_id: int, value):
        self.value = value


class DummyReportsStore:
    def __init__(self, value=None):
        self.value = value

    def load(self, telegram_user_id: int):
        return self.value

    def save(self, telegram_user_id: int, value):
        self.value = value


class DummyReportStore:
    def load(self, telegram_user_id: int, period_key: str):
        return object()


class DummyUncatPendingStore:
    def load(self, telegram_user_id: int):
        return None


class DummyUncatStore:
    def load(self, telegram_user_id: int):
        return []


class DummyRulesStore:
    def add(self, telegram_user_id: int, rule):
        return None


class DummyMonoAccount:
    def __init__(self, account_id: str, currency_code: int, masked_pan: list[str]):
        self.id = account_id
        self.currencyCode = currency_code
        self.maskedPan = masked_pan


class DummyMonoInfo:
    def __init__(self, accounts):
        self.accounts = accounts


class DummyMonobankClientSuccess:
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


class DummyMonobankClientInvalid:
    def __init__(self, token: str):
        self.token = token

    def client_info(self):
        raise RuntimeError("Monobank API error: 401 Unauthorized")

    def close(self):
        return None


def _kb_dump(kb) -> list[list[tuple[str, str]]]:
    return [[(button.text, button.callback_data) for button in row] for row in kb.inline_keyboard]


def _build_dispatcher(*, monkeypatch, tmp_path, users: DummyUserStore):
    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")

    dp = DummyDispatcher()
    handlers.register_handlers(
        dp,
        bot=object(),
        settings=SimpleNamespace(openai_api_key=None, openai_model="gpt"),
        users=users,
        store=DummyReportStore(),
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
        render_report_for_user=lambda *a, **k: "REPORT",
    )
    return dp


def test_onb_token_opens_button_first_manual_entry_screen(monkeypatch, tmp_path):
    users = DummyUserStore()
    dp = _build_dispatcher(monkeypatch=monkeypatch, tmp_path=tmp_path, users=users)

    cb_onb_token = dp.callback_query.handlers["cb_onb_token"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data="onb_token", message=message)

    asyncio.run(cb_onb_token(query))

    manual = ms.get_pending_manual_mode(1, now_ts=ms.load_memory(1)["pending_created_ts"])
    assert manual is not None
    assert manual["expected"] == "mono_token"
    assert manual["source"] == "onboarding"
    assert manual["hint"] == templates.token_paste_hint_connect()

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.onboarding_token_paste_prompt()
    assert _kb_dump(kb) == [[("⬅️ Назад", "onb_back_main")]]
    assert query.answer_calls[-1] == ("Ок", False, None)


def test_back_from_token_entry_clears_pending_and_plain_text_is_not_captured_as_token(
    monkeypatch, tmp_path
):
    users = DummyUserStore()
    dp = _build_dispatcher(monkeypatch=monkeypatch, tmp_path=tmp_path, users=users)

    cb_onb_token = dp.callback_query.handlers["cb_onb_token"]
    cb_onb_back_main = dp.callback_query.handlers["cb_onb_back_main"]
    handle_plain_text = dp.message.handlers["handle_plain_text"]

    open_message = DummyMessage(user_id=1)
    open_query = DummyCallbackQuery(user_id=1, data="onb_token", message=open_message)
    asyncio.run(cb_onb_token(open_query))

    back_query = DummyCallbackQuery(user_id=1, data="onb_back_main", message=open_message)
    asyncio.run(cb_onb_back_main(back_query))

    assert ms.get_pending_manual_mode(1, now_ts=9999999999) is None

    typed = DummyMessage(user_id=1, text="token-12345678901234567890")
    asyncio.run(handle_plain_text(typed))

    assert users.load(1) is None
    assert typed.answers == [(templates.err_not_connected(), None)]


def test_invalid_token_keeps_wizard_alive_and_next_valid_token_completes_flow(
    monkeypatch, tmp_path
):
    users = DummyUserStore()
    dp = _build_dispatcher(monkeypatch=monkeypatch, tmp_path=tmp_path, users=users)

    cb_onb_token = dp.callback_query.handlers["cb_onb_token"]
    handle_plain_text = dp.message.handlers["handle_plain_text"]

    query_message = DummyMessage(user_id=1)
    open_query = DummyCallbackQuery(user_id=1, data="onb_token", message=query_message)
    asyncio.run(cb_onb_token(open_query))

    monkeypatch.setattr(handlers, "MonobankClient", DummyMonobankClientInvalid)

    invalid_message = DummyMessage(user_id=1, text="token-12345678901234567890")
    asyncio.run(handle_plain_text(invalid_message))

    assert invalid_message.answers[0][0] == templates.connect_token_validation_progress()
    assert invalid_message.answers[1][0] == templates.monobank_invalid_token_message()

    manual_after_invalid = ms.get_pending_manual_mode(
        1, now_ts=ms.load_memory(1)["pending_created_ts"]
    )
    assert manual_after_invalid is not None
    assert manual_after_invalid["expected"] == "mono_token"
    assert users.load(1) is None

    monkeypatch.setattr(handlers, "MonobankClient", DummyMonobankClientSuccess)

    valid_message = DummyMessage(user_id=1, text="token-12345678901234567890")
    asyncio.run(handle_plain_text(valid_message))

    saved = users.load(1)
    assert saved is not None
    assert saved.mono_token == "token-12345678901234567890"
    assert saved.selected_account_ids == []

    assert ms.get_pending_manual_mode(1, now_ts=9999999999) is None
    assert valid_message.answers[0][0] == templates.connect_token_validation_progress()
    assert templates.connect_success_confirm() in valid_message.answers[1][0]
    assert "💳 Обери рахунки" in valid_message.answers[1][0]
    assert valid_message.answers[1][1] is not None
