from pathlib import Path

from test_menu_gating import DummyCallbackQuery, DummyMessage, _build_dispatcher

import mono_ai_budget_bot.bot.handlers as handlers
import mono_ai_budget_bot.nlq.memory_store as ms
from mono_ai_budget_bot.bot.ui import build_nlq_clarify_keyboard
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


def test_build_nlq_clarify_keyboard_has_pick_other_cancel():
    kb = build_nlq_clarify_keyboard(
        ["Getmancar", "Aston express"],
        pending_id="deadbeef",
        limit=8,
    )
    assert kb is not None

    buttons = [b for row in kb.inline_keyboard for b in row]
    datas = [b.callback_data for b in buttons]

    assert "nlq_pick:deadbeef:1" in datas
    assert "nlq_pick:deadbeef:2" in datas
    assert "nlq_other:deadbeef" in datas
    assert "nlq_cancel:deadbeef" in datas


def test_standard_recipient_clarify_message_uses_pick_other_cancel(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")

    def fake_handle_nlq(req: NLQRequest) -> NLQResponse:
        ms.set_pending_intent(
            req.telegram_user_id,
            payload={"intent": "transfer_out_sum", "days": 30, "recipient_alias": "мамі"},
            kind="recipient",
            options=["Anna K.", "Kate S."],
        )
        return NLQResponse(result=NLQResult(text="Кого саме маєш на увазі?"))

    monkeypatch.setattr(handlers, "handle_nlq", fake_handle_nlq)

    tx_store = TxStore(tmp_path / "tx")
    dp = _build_dispatcher(
        cfg=_base_cfg(),
        profile=_base_profile(),
        tx_store=tx_store,
    )

    plain = dp.message.handlers["handle_plain_text"]
    message = DummyMessage(user_id=1, text="Скільки я переказав мамі?")
    import asyncio

    asyncio.run(plain(message))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == "Кого саме маєш на увазі?"
    labels = [b.text for row in kb.inline_keyboard for b in row]
    datas = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "1. Anna K." in labels
    assert "2. Kate S." in labels
    assert "✍️ Інше" in labels
    assert "❌ Скасувати" in labels
    assert any(x.startswith("nlq_pick:") for x in datas)
    assert any(x.startswith("nlq_other:") for x in datas)
    assert any(x.startswith("nlq_cancel:") for x in datas)


def test_standard_category_alias_clarify_message_uses_pick_other_cancel(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")

    def fake_handle_nlq(req: NLQRequest) -> NLQResponse:
        ms.set_pending_intent(
            req.telegram_user_id,
            payload={"intent": "spend_sum", "days": 30, "merchant_contains": "каршерінг"},
            kind="category_alias",
            options=["Getmancar", "Aston express"],
        )
        return NLQResponse(
            result=NLQResult(text="Я поки що не знаю, що для тебе означає 'каршерінг'.")
        )

    monkeypatch.setattr(handlers, "handle_nlq", fake_handle_nlq)

    tx_store = TxStore(tmp_path / "tx")
    dp = _build_dispatcher(
        cfg=_base_cfg(),
        profile=_base_profile(),
        tx_store=tx_store,
    )

    plain = dp.message.handlers["handle_plain_text"]
    message = DummyMessage(user_id=1, text="Скільки я витратив на каршерінг?")
    import asyncio

    asyncio.run(plain(message))

    assert len(message.answers) == 1
    text, kb = message.answers[0]
    assert text == "Я поки що не знаю, що для тебе означає 'каршерінг'."
    datas = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert any(x.startswith("nlq_pick:") for x in datas)
    assert any(x.startswith("nlq_other:") for x in datas)
    assert any(x.startswith("nlq_cancel:") for x in datas)


def test_nlq_other_standardizes_manual_mode_for_category_kind(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")

    tx_store = TxStore(tmp_path / "tx")
    dp = _build_dispatcher(
        cfg=_base_cfg(),
        profile=_base_profile(),
        tx_store=tx_store,
    )

    ms.set_pending_intent(
        1,
        payload={"intent": "spend_sum", "days": 30, "category": "Кафе/Ресторани"},
        kind="category",
        options=["Кафе/Ресторани", "Продукти"],
    )
    mem = ms.load_memory(1)
    pid = mem.get("pending_id")
    assert isinstance(pid, str)

    cb = dp.callback_query.handlers["cb_nlq_other"]
    message = DummyMessage(user_id=1)
    query = DummyCallbackQuery(user_id=1, data=f"nlq_other:{pid}", message=message)
    import asyncio

    asyncio.run(cb(query))

    manual = ms.get_pending_manual_mode(1, now_ts=10**9)
    assert manual is not None
    assert manual["expected"] == "category"
    assert manual["source"] == "nlq_other"
    assert len(message.answers) == 1
    assert "введи вручну" in message.answers[0][0].lower()
