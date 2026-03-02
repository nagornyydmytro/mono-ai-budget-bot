import time

import mono_ai_budget_bot.nlq.memory_store as ms


def test_pending_ttl_expires(tmp_path, monkeypatch):
    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")
    monkeypatch.setattr(time, "time", lambda: 1000)

    ms.set_pending_intent(1, {"intent": "spend_sum"}, kind="paging", options=["x"])
    mem = ms.load_memory(1)
    assert ms.pending_is_alive(mem, now_ts=1001)

    assert not ms.pending_is_alive(mem, now_ts=2000)
