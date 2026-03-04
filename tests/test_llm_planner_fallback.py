import mono_ai_budget_bot.nlq.pipeline as pl
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
            Tx(time_=1000, amount=-41800, mcc=5814, description="McDonald's"),
            Tx(time_=1100, amount=-10000, mcc=5814, description="McDonald's"),
        ]

    def aggregated_coverage_window(
        self,
        telegram_user_id: int,
        account_ids: list[str],
    ) -> tuple[int, int] | None:
        return None


def test_llm_planner_fallback_executes(monkeypatch, tmp_path):
    import mono_ai_budget_bot.nlq.executor as ex
    import mono_ai_budget_bot.nlq.memory_store as ms

    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")
    monkeypatch.setattr(ex, "UserStore", lambda: DummyUserStore())
    monkeypatch.setattr(ex, "TxStore", lambda: DummyTxStore())

    monkeypatch.setattr(pl, "route", lambda req: None)

    class DummyClient:
        def plan_nlq(self, *, user_text: str, now_ts: int):
            return {"intent": "spend_sum", "days": 30, "merchant_contains": "мак", "end_ts": now_ts}

    monkeypatch.setattr(pl, "_get_llm_client", lambda: DummyClient())

    resp = pl.handle_nlq(
        NLQRequest(telegram_user_id=1, text="скільки я витратив на мак за місяць?", now_ts=2000)
    )
    assert resp.result is not None
    assert "518.00" in resp.result.text
