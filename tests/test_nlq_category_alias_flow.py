import time

import mono_ai_budget_bot.nlq.executor as ex
import mono_ai_budget_bot.nlq.memory_store as ms
from mono_ai_budget_bot.nlq.pipeline import handle_nlq
from mono_ai_budget_bot.nlq.types import NLQRequest
from mono_ai_budget_bot.storage.user_store import UserConfig


class DummyUserStore:
    def load(self, telegram_user_id: int):
        return UserConfig(
            telegram_user_id=telegram_user_id,
            mono_token="t",
            selected_account_ids=["acc"],
            chat_id=None,
            autojobs_enabled=False,
            updated_at=0.0,
        )


class Tx:
    def __init__(self, time_: int, amount: int, mcc: int | None, description: str):
        self.id = "x"
        self.time = time_
        self.account_id = "acc"
        self.amount = amount
        self.description = description
        self.mcc = mcc
        self.currencyCode = 980


class DummyTxStore:
    def load_range(self, telegram_user_id: int, account_ids: list[str], ts_from: int, ts_to: int):
        return [
            Tx(time_=1000, amount=-504864, mcc=4121, description="Getmancar"),
            Tx(time_=1100, amount=-41800, mcc=4121, description="Aston express"),
            Tx(time_=1200, amount=-285994, mcc=5411, description="Фора"),
        ]

    def aggregated_coverage_window(
        self,
        telegram_user_id: int,
        account_ids: list[str],
    ) -> tuple[int, int] | None:
        return None


def test_unknown_alias_triggers_clarify_and_learns(tmp_path, monkeypatch):
    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")

    monkeypatch.setattr(ex, "UserStore", lambda: DummyUserStore())
    monkeypatch.setattr(ex, "TxStore", lambda: DummyTxStore())
    monkeypatch.setattr(time, "time", lambda: 2000)

    msg = ex.execute_intent(
        1, {"intent": "spend_sum", "days": 30, "merchant_contains": "каршерінг"}
    )
    assert "5048.64 ₴" in msg
    assert "не знаю" in msg.lower()
    mem = ms.load_memory(1)
    assert mem.get("pending_kind") == "category_alias"
    opts = mem.get("pending_options")
    assert isinstance(opts, list)
    assert any("getmancar" in str(x).lower() for x in opts)

    resp = handle_nlq(NLQRequest(telegram_user_id=1, text="1,3", now_ts=2000))
    assert resp.result is not None
    assert "5466.64" in resp.result.text


def test_category_alias_cancel_clears_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")

    monkeypatch.setattr(ex, "UserStore", lambda: DummyUserStore())
    monkeypatch.setattr(ex, "TxStore", lambda: DummyTxStore())
    monkeypatch.setattr(time, "time", lambda: 2000)

    _ = ex.execute_intent(1, {"intent": "spend_sum", "days": 30, "merchant_contains": "каршерінг"})
    mem = ms.load_memory(1)
    assert mem.get("pending_kind") == "category_alias"

    resp = handle_nlq(NLQRequest(telegram_user_id=1, text="0", now_ts=2000))
    assert resp.result is not None
    assert "не зберігаю" in resp.result.text.lower()

    mem2 = ms.load_memory(1)
    assert mem2.get("pending_kind") is None
    assert mem2.get("pending_intent") is None


def test_category_alias_range_selection(tmp_path, monkeypatch):
    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")

    monkeypatch.setattr(ex, "UserStore", lambda: DummyUserStore())
    monkeypatch.setattr(ex, "TxStore", lambda: DummyTxStore())
    monkeypatch.setattr(time, "time", lambda: 2000)

    _ = ex.execute_intent(1, {"intent": "spend_sum", "days": 30, "merchant_contains": "каршерінг"})
    resp = handle_nlq(NLQRequest(telegram_user_id=1, text="1-3", now_ts=2000))
    assert resp.result is not None

    mem = ms.load_memory(1)
    ca = mem.get("category_aliases")
    assert isinstance(ca, dict)
    assert "каршерінг" in ca
    terms = ca["каршерінг"]
    assert isinstance(terms, list)
    assert len(terms) >= 3


def test_category_alias_text_selection(tmp_path, monkeypatch):
    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")

    monkeypatch.setattr(ex, "UserStore", lambda: DummyUserStore())
    monkeypatch.setattr(ex, "TxStore", lambda: DummyTxStore())
    monkeypatch.setattr(time, "time", lambda: 2000)

    _ = ex.execute_intent(
        1,
        {"intent": "spend_sum", "days": 30, "merchant_contains": "каршерінг"},
    )

    resp = handle_nlq(NLQRequest(telegram_user_id=1, text="getmancar, aston", now_ts=2000))
    assert resp.result is not None
    assert "5466.64" in resp.result.text
