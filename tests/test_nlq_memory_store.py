import time

import mono_ai_budget_bot.nlq.executor as ex
import mono_ai_budget_bot.nlq.memory_store as ms
from mono_ai_budget_bot.nlq.memory_store import resolve_merchant_alias, save_memory
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
            Tx(time_=1000, amount=-15000, mcc=5814, description="McDonalds Kyiv"),
            Tx(time_=1100, amount=-5000, mcc=5411, description="ATB"),
        ]


def test_memory_file_created(tmp_path, monkeypatch):
    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")
    m = ms.load_memory(1)
    assert m["merchant_aliases"].get("мак") == "mcdonalds"
    assert "merchant_aliases" in m
    assert (ms.BASE_DIR / "1.json").exists()


def test_executor_merchant_alias_resolution(tmp_path, monkeypatch):
    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")

    m = ms.load_memory(1)
    m["merchant_aliases"]["мак"] = "mcdonalds"
    ms.save_memory(1, m)

    monkeypatch.setattr(ex, "UserStore", lambda: DummyUserStore())
    monkeypatch.setattr(ex, "TxStore", lambda: DummyTxStore())
    monkeypatch.setattr(time, "time", lambda: 2000)

    s = ex.execute_intent(1, {"intent": "spend_sum", "days": 30, "merchant_contains": "мак"})
    assert "150.00" in s


def test_auto_cache_alias(tmp_path, monkeypatch):
    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")

    m = ms.load_memory(1)
    ms.save_memory(1, m)

    r = ms.resolve_merchant_alias(1, "макдональдс")
    assert r == "mcdonalds"

    m2 = ms.load_memory(1)
    assert m2["merchant_aliases"].get("макдональдс") == "mcdonalds"


def test_transfer_requires_recipient_mapping_sets_pending(tmp_path, monkeypatch):
    import time as timemod

    import mono_ai_budget_bot.nlq.executor as exmod
    import mono_ai_budget_bot.nlq.memory_store as msmod

    monkeypatch.setattr(msmod, "BASE_DIR", tmp_path / "memory")
    monkeypatch.setattr(exmod, "load_memory", msmod.load_memory)
    monkeypatch.setattr(exmod, "set_pending_intent", msmod.set_pending_intent)

    monkeypatch.setattr(exmod, "UserStore", lambda: DummyUserStore())
    monkeypatch.setattr(exmod, "TxStore", lambda: DummyTxStore())
    monkeypatch.setattr(timemod, "time", lambda: 2000)

    s = exmod.execute_intent(
        1, {"intent": "transfer_out_sum", "days": 30, "recipient_alias": "дівчині"}
    )
    assert "Кого саме" in s

    mem = msmod.load_memory(1)
    assert isinstance(mem.get("pending_intent"), dict)


def test_followup_completes_and_saves_mapping(tmp_path, monkeypatch):
    import time as timemod

    import mono_ai_budget_bot.nlq.executor as exmod
    import mono_ai_budget_bot.nlq.memory_store as msmod

    monkeypatch.setattr(msmod, "BASE_DIR", tmp_path / "memory")
    monkeypatch.setattr(exmod, "UserStore", lambda: DummyUserStore())
    monkeypatch.setattr(exmod, "TxStore", lambda: DummyTxStore())
    monkeypatch.setattr(timemod, "time", lambda: 2000)

    s = exmod.execute_intent(
        1, {"intent": "transfer_out_sum", "days": 30, "recipient_alias": "дівчині"}
    )
    assert "Кого саме" in s

    exmod.execute_intent(1, {"intent": "spend_sum", "merchant_contains": "McDonalds"})
    mem = msmod.load_memory(1)
    assert "дівчині" in mem.get("recipient_aliases", {})


def test_default_merchant_aliases_contains_mcdonalds(tmp_path):
    user_id = 1
    save_memory(user_id, {"merchant_aliases": {"мак": "mcdonalds"}})
    assert resolve_merchant_alias(user_id, "мак") in ("mcdonald", "mcdonalds")


def test_resolve_merchant_alias_normalizes(tmp_path):
    user_id = 1
    save_memory(user_id, {"merchant_aliases": {"мак": "mcdonalds"}})
    assert resolve_merchant_alias(user_id, "  МАК!! ") == "mcdonalds"
