import asyncio
from dataclasses import dataclass
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


class DummyReportStore:
    def load(self, telegram_user_id: int, period_key: str):
        return object()


class DummyProfileStore:
    def __init__(self):
        self.data = {
            "activity_mode": "quiet",
            "uncategorized_prompt_frequency": "before_report",
            "persona": "rational",
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


@dataclass
class FlowHarness:
    handle_plain_text: object
    cb_cov_sync: object
    cb_cov_cancel: object
    sync_calls: list[int]
    nlq_calls: list[str]


def _build_harness(monkeypatch, tmp_path, *, coverage_status: str) -> FlowHarness:
    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")

    dp = DummyDispatcher()
    sync_calls: list[int] = []
    nlq_calls: list[str] = []

    async def sync_user_ledger(user_id: int, cfg, *, days_back: int):
        sync_calls.append(days_back)

    def fake_handle_nlq(req):
        nlq_calls.append(req.text)
        if len(nlq_calls) == 1:
            mem = ms.load_memory(req.telegram_user_id)
            mem["last_coverage_status"] = coverage_status
            mem["last_coverage_days_back"] = 30
            ms.save_memory(req.telegram_user_id, mem)
            return SimpleNamespace(result=SimpleNamespace(text=f"Coverage {coverage_status}"))
        return SimpleNamespace(result=SimpleNamespace(text="Final answer"))

    monkeypatch.setattr(handlers, "handle_nlq", fake_handle_nlq)

    handlers.register_handlers(
        dp,
        bot=object(),
        settings=object(),
        users=DummyUserStore(),
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
        sync_user_ledger=sync_user_ledger,
        render_report_for_user=lambda *a, **k: None,
    )

    return FlowHarness(
        handle_plain_text=dp.message.handlers["handle_plain_text"],
        cb_cov_sync=dp.callback_query.handlers["cb_cov_sync"],
        cb_cov_cancel=dp.callback_query.handlers["cb_cov_cancel"],
        sync_calls=sync_calls,
        nlq_calls=nlq_calls,
    )


def test_missing_coverage_sync_reruns_with_separate_success_and_answer_messages(
    monkeypatch, tmp_path
):
    harness = _build_harness(monkeypatch, tmp_path, coverage_status="missing")

    message = DummyMessage(user_id=1, text="Скільки я витратив?")
    asyncio.run(harness.handle_plain_text(message))

    pending_id = ms.get_pending_id(1)
    assert isinstance(pending_id, str) and pending_id
    assert message.answers[0][0] == "Coverage missing"

    query = DummyCallbackQuery(user_id=1, data=f"cov_sync:{pending_id}", message=message)
    asyncio.run(harness.cb_cov_sync(query))

    assert harness.sync_calls == [30]
    assert harness.nlq_calls == ["Скільки я витратив?", "Скільки я витратив?"]
    assert [text for text, _ in message.answers] == [
        "Coverage missing",
        templates.ledger_refresh_progress_message(),
        templates.coverage_sync_done_message(),
        "Final answer",
    ]
    mem = ms.load_memory(1)
    assert mem.get("pending_intent") is None
    assert mem.get("pending_id") is None
    assert query.answer_calls[-1] == ("Ок", False)


def test_partial_coverage_sync_reruns_with_separate_success_and_answer_messages(
    monkeypatch, tmp_path
):
    harness = _build_harness(monkeypatch, tmp_path, coverage_status="partial")

    message = DummyMessage(user_id=1, text="Скільки я витратив?")
    asyncio.run(harness.handle_plain_text(message))

    pending_id = ms.get_pending_id(1)
    assert isinstance(pending_id, str) and pending_id
    assert message.answers[0][0] == "Coverage partial"

    query = DummyCallbackQuery(user_id=1, data=f"cov_sync:{pending_id}", message=message)
    asyncio.run(harness.cb_cov_sync(query))

    assert harness.sync_calls == [30]
    assert harness.nlq_calls == ["Скільки я витратив?", "Скільки я витратив?"]
    assert [text for text, _ in message.answers] == [
        "Coverage partial",
        templates.ledger_refresh_progress_message(),
        templates.coverage_sync_done_message(),
        "Final answer",
    ]
    mem = ms.load_memory(1)
    assert mem.get("pending_intent") is None
    assert mem.get("pending_id") is None
    assert query.answer_calls[-1] == ("Ок", False)


def test_coverage_cancel_clears_pending_without_sync_or_rerun(monkeypatch, tmp_path):
    harness = _build_harness(monkeypatch, tmp_path, coverage_status="missing")

    message = DummyMessage(user_id=1, text="Скільки я витратив?")
    asyncio.run(harness.handle_plain_text(message))

    pending_id = ms.get_pending_id(1)
    assert isinstance(pending_id, str) and pending_id

    query = DummyCallbackQuery(user_id=1, data=f"cov_cancel:{pending_id}", message=message)
    asyncio.run(harness.cb_cov_cancel(query))

    mem = ms.load_memory(1)
    assert mem.get("pending_intent") is None
    assert mem.get("pending_id") is None
    assert harness.sync_calls == []
    assert harness.nlq_calls == ["Скільки я витратив?"]
    assert "Final answer" not in [text for text, _ in message.answers]
    assert query.answer_calls[-1] == ("Скасовано", False)


def test_coverage_sync_rejects_stale_pending_id_without_executing(monkeypatch, tmp_path):
    harness = _build_harness(monkeypatch, tmp_path, coverage_status="missing")

    ms.set_pending_intent(
        1,
        payload={"action": "coverage_sync", "days_back": 30, "nlq_text": "Q"},
        kind="coverage_cta",
        options=None,
    )
    message = DummyMessage(user_id=1, text="")

    query = DummyCallbackQuery(user_id=1, data="cov_sync:deadbeef", message=message)
    asyncio.run(harness.cb_cov_sync(query))

    assert harness.sync_calls == []
    assert harness.nlq_calls == []
    assert message.answers == []
    assert query.answer_calls[-1] == (templates.stale_button_message(), True)


def test_coverage_sync_rejects_expired_pending_without_executing(monkeypatch, tmp_path):
    harness = _build_harness(monkeypatch, tmp_path, coverage_status="missing")

    ms.set_pending_intent(
        1,
        payload={"action": "coverage_sync", "days_back": 30, "nlq_text": "Q"},
        kind="coverage_cta",
        options=None,
    )
    pending_id = ms.get_pending_id(1)
    assert isinstance(pending_id, str) and pending_id

    mem = ms.load_memory(1)
    mem["pending_created_ts"] = int(mem["pending_created_ts"]) - 601
    mem["pending_ttl_sec"] = 600
    ms.save_memory(1, mem)

    message = DummyMessage(user_id=1, text="")
    query = DummyCallbackQuery(user_id=1, data=f"cov_sync:{pending_id}", message=message)
    asyncio.run(harness.cb_cov_sync(query))

    assert harness.sync_calls == []
    assert harness.nlq_calls == []
    assert message.answers == []
    assert query.answer_calls[-1] == (templates.stale_button_message(), True)
