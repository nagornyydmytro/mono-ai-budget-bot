import time

import mono_ai_budget_bot.nlq.memory_store as ms


def test_validate_and_consume_pending_one_time(monkeypatch, tmp_path):
    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")
    user_id = 123

    ms.set_pending_intent(user_id, {"intent": "x"}, kind="k", options=["a", "b"])
    pid = ms.get_pending_id(user_id)
    assert pid

    now_ts = int(time.time())
    assert ms.validate_and_consume_pending(user_id, pending_id=pid, now_ts=now_ts)
    assert not ms.validate_and_consume_pending(user_id, pending_id=pid, now_ts=now_ts)


def test_validate_and_consume_pending_rejects_wrong_pending_id(monkeypatch, tmp_path):
    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")
    user_id = 456

    ms.set_pending_intent(user_id, {"intent": "x"}, kind="k", options=["a", "b"])
    pid = ms.get_pending_id(user_id)
    assert pid

    now_ts = int(time.time())
    assert not ms.validate_and_consume_pending(user_id, pending_id="deadbeef", now_ts=now_ts)


def test_validate_and_consume_pending_rejects_stale(monkeypatch, tmp_path):
    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")
    user_id = 789

    ms.set_pending_intent(user_id, {"intent": "x"}, kind="k", options=["a", "b"])
    pid = ms.get_pending_id(user_id)
    assert pid

    now_ts = int(time.time())
    mem = ms.load_memory(user_id)
    mem["pending_created_ts"] = now_ts - 601
    mem["pending_ttl_sec"] = 600
    ms.save_memory(user_id, mem)

    assert not ms.validate_and_consume_pending(user_id, pending_id=pid, now_ts=now_ts)
