import time

from mono_ai_budget_bot.nlq.executor import execute_intent
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
    def __init__(self, amount: int, mcc: int | None, description: str):
        self.amount = amount
        self.mcc = mcc
        self.description = description


class DummyTxStore:
    def load_range(self, telegram_user_id: int, account_ids: list[str], ts_from: int, ts_to: int):
        return [
            Tx(amount=10000, mcc=None, description="Поповнення картки"),
            Tx(amount=-5000, mcc=5411, description="ATB"),
            Tx(amount=-2000, mcc=4829, description="Переказ на картку"),
            Tx(amount=3000, mcc=4829, description="P2P transfer incoming"),
            Tx(amount=7000, mcc=None, description="top up"),
        ]


def test_executor_income_and_transfers(monkeypatch):
    import mono_ai_budget_bot.nlq.executor as ex

    monkeypatch.setattr(ex, "UserStore", lambda: DummyUserStore())
    monkeypatch.setattr(ex, "TxStore", lambda: DummyTxStore())
    monkeypatch.setattr(time, "time", lambda: 2000)

    uid = 1

    s = execute_intent(uid, {"intent": "income_sum", "days": 30})
    assert "170.00" in s

    s = execute_intent(uid, {"intent": "income_count", "days": 30})
    assert "2" in s

    s = execute_intent(uid, {"intent": "transfer_out_sum", "days": 30})
    assert "20.00" in s

    s = execute_intent(uid, {"intent": "transfer_in_sum", "days": 30})
    assert "30.00" in s
