import time

import mono_ai_budget_bot.nlq.executor as ex
import mono_ai_budget_bot.nlq.memory_store as ms
import mono_ai_budget_bot.nlq.pipeline as pl
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
        self.id = f"x{time_}"
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
            Tx(time_=1300, amount=-120000, mcc=4829, description="Переказ дівчині: Anna K."),
            Tx(time_=1400, amount=-80000, mcc=4829, description="Переказ дівчині: Anna K. (food)"),
            Tx(time_=1500, amount=-50000, mcc=4829, description="Переказ дівчині: Kate S."),
        ]

    def aggregated_coverage_window(
        self,
        telegram_user_id: int,
        account_ids: list[str],
    ) -> tuple[int, int] | None:
        return None


def _patch_stores(monkeypatch, tmp_path):
    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")
    monkeypatch.setattr(ex, "UserStore", lambda: DummyUserStore())
    monkeypatch.setattr(ex, "TxStore", lambda: DummyTxStore())
    monkeypatch.setattr(pl, "UserStore", lambda: DummyUserStore())
    monkeypatch.setattr(pl, "TxStore", lambda: DummyTxStore())
    monkeypatch.setattr(time, "time", lambda: 2000)


def test_manual_entry_recipient_alias_e2e(tmp_path, monkeypatch):
    _patch_stores(monkeypatch, tmp_path)

    msg = ex.execute_intent(
        1, {"intent": "transfer_out_sum", "days": 30, "recipient_alias": "дівчині"}
    )
    assert "Кого саме" in msg
    mem = ms.load_memory(1)
    assert mem.get("pending_kind") == "recipient"
    assert isinstance(mem.get("pending_intent"), dict)

    ms.set_pending_manual_mode(
        1,
        expected="recipient",
        hint="x",
        source="test",
        ttl_sec=600,
    )

    resp1 = handle_nlq(NLQRequest(telegram_user_id=1, text="anna", now_ts=2000))
    assert resp1.result is not None
    assert "Вибери номер" in resp1.result.text

    resp2 = handle_nlq(NLQRequest(telegram_user_id=1, text="1", now_ts=2000))
    assert resp2.result is not None

    mem2 = ms.load_memory(1)
    ra = mem2.get("recipient_aliases")
    assert isinstance(ra, dict)
    assert ra.get("дівчині")


def test_manual_entry_category_alias_e2e(tmp_path, monkeypatch):
    _patch_stores(monkeypatch, tmp_path)

    msg = ex.execute_intent(
        1, {"intent": "spend_sum", "days": 30, "merchant_contains": "каршерінг"}
    )
    assert "не знаю" in msg.lower()
    mem = ms.load_memory(1)
    assert mem.get("pending_kind") == "category_alias"
    opts = mem.get("pending_options")
    assert isinstance(opts, list) and opts

    ms.set_pending_manual_mode(
        1,
        expected="merchant_or_recipient",
        hint="x",
        source="test",
        ttl_sec=600,
    )

    resp1 = handle_nlq(NLQRequest(telegram_user_id=1, text="get", now_ts=2000))
    assert resp1.result is not None
    assert "Вибери номер" in resp1.result.text

    resp2 = handle_nlq(NLQRequest(telegram_user_id=1, text="1", now_ts=2000))
    assert resp2.result is not None

    mem2 = ms.load_memory(1)
    ca = mem2.get("category_aliases")
    assert isinstance(ca, dict)
    assert "каршерінг" in ca


def test_multi_mapping_recipient_alias_requires_choice_and_saves_after_pick(tmp_path, monkeypatch):
    _patch_stores(monkeypatch, tmp_path)

    ms.add_learned_mapping(1, bucket="recipient", alias="дівчині", value="anna k.")
    ms.add_learned_mapping(1, bucket="recipient", alias="дівчині", value="kate s.")

    msg = ex.execute_intent(
        1, {"intent": "transfer_out_sum", "days": 30, "recipient_alias": "дівчині"}
    )
    assert "Кого саме" in msg

    mem = ms.load_memory(1)
    assert mem.get("pending_kind") == "recipient"
    opts = mem.get("pending_options")
    assert isinstance(opts, list)
    assert set(opts) == {"anna k.", "kate s."}

    resp = handle_nlq(NLQRequest(telegram_user_id=1, text="1", now_ts=2000))
    assert resp.result is not None

    mem2 = ms.load_memory(1)
    ra = mem2.get("recipient_aliases")
    assert isinstance(ra, dict)
    assert ra.get("дівчині") in {"anna k.", "kate s."}


def test_recipient_alias_is_not_saved_without_ledger_evidence(tmp_path, monkeypatch):
    _patch_stores(monkeypatch, tmp_path)

    ms.set_pending_intent(
        1,
        payload={"intent": "transfer_out_sum", "days": 30, "recipient_alias": "дівчині"},
        kind="recipient",
        options=["Ghost Person"],
    )

    resp = handle_nlq(NLQRequest(telegram_user_id=1, text="Ghost Person", now_ts=2000))
    assert resp.result is not None
    assert "Не знайшов такого отримувача" in resp.result.text

    mem = ms.load_memory(1)
    ra = mem.get("recipient_aliases")
    assert not isinstance(ra, dict) or "дівчині" not in ra


def test_pending_clarify_is_abandoned_when_user_asks_new_full_question(tmp_path, monkeypatch):
    _patch_stores(monkeypatch, tmp_path)

    ms.set_pending_intent(
        1,
        payload={"intent": "spend_sum", "days": 30, "merchant_contains": "каршерінг"},
        kind="category_alias",
        options=["Getmancar", "Aston express"],
    )

    resp = handle_nlq(
        NLQRequest(
            telegram_user_id=1,
            text="Скільки я витратив на транспорт за останні 30 днів?",
            now_ts=2000,
        )
    )
    assert resp.result is not None
    assert "транспорт" in resp.result.text.lower() or "грн" in resp.result.text.lower()

    mem = ms.load_memory(1)
    assert mem.get("pending_kind") is None


def test_recipient_exact_text_followup_uses_same_pending_contract(tmp_path, monkeypatch):
    _patch_stores(monkeypatch, tmp_path)

    ms.set_pending_intent(
        1,
        payload={"intent": "transfer_out_sum", "days": 30, "recipient_alias": "дівчині"},
        kind="recipient",
        options=["Anna K.", "Kate S."],
    )

    resp = handle_nlq(NLQRequest(telegram_user_id=1, text="Anna K.", now_ts=2000))
    assert resp.result is not None
    assert "грн" in resp.result.text or "переказ" in resp.result.text.lower()

    mem = ms.load_memory(1)
    ra = mem.get("recipient_aliases")
    assert isinstance(ra, dict)
    assert ra.get("дівчині") == "anna k."
    assert mem.get("pending_kind") is None
