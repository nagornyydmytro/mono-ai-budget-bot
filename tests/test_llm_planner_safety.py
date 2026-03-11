import mono_ai_budget_bot.nlq.pipeline as pl
from mono_ai_budget_bot.nlq.types import NLQRequest


def test_llm_scope_guard_blocks_investing(monkeypatch):
    monkeypatch.setattr(pl, "route", lambda req: None)

    called = {"n": 0}

    class DummyClient:
        def plan_nlq(self, *, user_text: str, now_ts: int):
            called["n"] += 1
            return {"intent": "spend_sum", "days": 30, "end_ts": now_ts}

    monkeypatch.setattr(pl, "_get_llm_client", lambda: DummyClient())

    resp = pl.handle_nlq(
        NLQRequest(
            telegram_user_id=1,
            text="Куди інвестувати 1000$? купити btc чи акції?",
            now_ts=2000,
        )
    )
    assert resp.result is not None
    assert "лише з персональною фінансовою аналітикою" in resp.result.text
    assert called["n"] == 0


def test_llm_cooldown_blocks_spam(monkeypatch):
    monkeypatch.setattr(pl, "route", lambda req: None)

    class DummyClient:
        def plan_nlq(self, *, user_text: str, now_ts: int):
            return {"intent": "spend_sum", "days": 30, "end_ts": now_ts}

    monkeypatch.setattr(pl, "_get_llm_client", lambda: DummyClient())

    r1 = pl.handle_nlq(NLQRequest(telegram_user_id=1, text="скільки витратив?", now_ts=2000))
    r2 = pl.handle_nlq(NLQRequest(telegram_user_id=1, text="скільки витратив?", now_ts=2001))
    assert r1.result is None or r1.result.text is not None
    assert r2.result is None


def test_llm_planner_rejects_tool_mode_like_output(monkeypatch):
    monkeypatch.setattr(pl, "route", lambda req: None)

    class DummyClient:
        def plan_nlq(self, *, user_text: str, now_ts: int):
            return {"tool": "write_storage", "args": {"foo": "bar"}}

    monkeypatch.setattr(pl, "_get_llm_client", lambda: DummyClient())

    resp = pl.handle_nlq(
        NLQRequest(
            telegram_user_id=1,
            text="скільки я витратив на мак за місяць?",
            now_ts=3000,
        )
    )
    assert resp.result is None


def test_llm_planner_rejects_extra_storage_like_fields(monkeypatch):
    monkeypatch.setattr(pl, "route", lambda req: None)

    class DummyClient:
        def plan_nlq(self, *, user_text: str, now_ts: int):
            return {
                "intent": "spend_sum",
                "days": 30,
                "merchant_contains": "мак",
                "write_storage": {"bucket": "users"},
            }

    monkeypatch.setattr(pl, "_get_llm_client", lambda: DummyClient())

    resp = pl.handle_nlq(
        NLQRequest(
            telegram_user_id=1,
            text="скільки я витратив на мак за місяць?",
            now_ts=4000,
        )
    )
    assert resp.result is None


def test_llm_planner_accepts_model_dump_style_contract(monkeypatch, tmp_path):
    import mono_ai_budget_bot.nlq.executor as ex
    import mono_ai_budget_bot.nlq.memory_store as ms
    from mono_ai_budget_bot.storage.user_store import UserConfig

    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")

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
        def load_range(
            self, telegram_user_id: int, account_ids: list[str], ts_from: int, ts_to: int
        ):
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

    class DummyPlanModel:
        def model_dump(self, exclude_none: bool = True):
            return {
                "intent": "spend_sum",
                "days": 30,
                "merchant_contains": "мак",
                "end_ts": 5000,
            }

    class DummyClient:
        def plan_nlq(self, *, user_text: str, now_ts: int):
            return DummyPlanModel()

    monkeypatch.setattr(ex, "UserStore", lambda: DummyUserStore())
    monkeypatch.setattr(ex, "TxStore", lambda: DummyTxStore())
    monkeypatch.setattr(pl, "route", lambda req: None)
    monkeypatch.setattr(pl, "_get_llm_client", lambda: DummyClient())

    resp = pl.handle_nlq(
        NLQRequest(
            telegram_user_id=1,
            text="скільки я витратив на мак за місяць?",
            now_ts=5000,
        )
    )
    assert resp.result is not None
    assert "518.00" in resp.result.text
