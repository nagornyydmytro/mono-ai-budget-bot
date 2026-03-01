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
    assert resp.result is None
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
