import asyncio
from pathlib import Path

from test_menu_gating import DummyMessage, _build_dispatcher

import mono_ai_budget_bot.bot.handlers as handlers
import mono_ai_budget_bot.bot.templates as templates
from mono_ai_budget_bot.nlq.types import NLQRequest, NLQResponse, NLQResult
from mono_ai_budget_bot.storage.tx_store import TxStore
from mono_ai_budget_bot.storage.user_store import UserConfig


def _base_cfg() -> UserConfig:
    return UserConfig(
        telegram_user_id=1,
        mono_token="token",
        selected_account_ids=["acc1"],
        chat_id=None,
        autojobs_enabled=False,
        updated_at=0.0,
    )


def _base_profile() -> dict:
    return {
        "onboarding_completed": True,
        "activity_mode": "balanced",
        "uncategorized_prompt_frequency": "always",
        "persona": "neutral",
    }


def test_plain_text_nlq_query_executes_without_separate_menu_entry(tmp_path: Path, monkeypatch):
    def fake_handle_nlq(req: NLQRequest) -> NLQResponse:
        assert req.text == "Скільки я витратив на каву за 7 днів?"
        return NLQResponse(result=NLQResult(text="RESULT: 3 покупки, 120.00 грн"))

    monkeypatch.setattr(handlers, "handle_nlq", fake_handle_nlq)

    tx_store = TxStore(tmp_path / "tx")
    dp = _build_dispatcher(
        cfg=_base_cfg(),
        profile=_base_profile(),
        tx_store=tx_store,
    )

    handle_plain_text = dp.message.handlers["handle_plain_text"]
    message = DummyMessage(user_id=1, text="Скільки я витратив на каву за 7 днів?")

    asyncio.run(handle_plain_text(message))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == "RESULT: 3 покупки, 120.00 грн"
    assert kb is None


def test_plain_text_unknown_query_returns_unknown_nlq_message(tmp_path: Path):
    tx_store = TxStore(tmp_path / "tx")
    dp = _build_dispatcher(
        cfg=_base_cfg(),
        profile=_base_profile(),
        tx_store=tx_store,
    )

    handle_plain_text = dp.message.handlers["handle_plain_text"]
    message = DummyMessage(user_id=1, text="абракадабра незрозумілий запит 123")

    asyncio.run(handle_plain_text(message))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == templates.unknown_nlq_message()
    assert kb is None
