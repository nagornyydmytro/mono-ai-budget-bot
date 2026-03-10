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


def test_get_pending_contract_has_canonical_shape(monkeypatch, tmp_path):
    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")
    monkeypatch.setattr(time, "time", lambda: 1000)

    ms.set_pending_intent(
        1,
        {"intent": "transfer_out_sum", "days": 30, "recipient_alias": "мамі"},
        kind="recipient",
        options=["Anna K.", "Kate S."],
    )

    contract = ms.get_pending_contract(1, now_ts=1001)
    assert isinstance(contract, dict)
    assert isinstance(contract.get("id"), str) and contract.get("id")
    assert contract.get("ttl_sec") == 600
    assert contract.get("one_time_use") is True
    assert contract.get("entity_type") == "recipient"
    assert contract.get("kind") == "recipient"
    assert contract.get("options") == ["Anna K.", "Kate S."]
    assert contract.get("original_query_spec", {}).get("intent") == "transfer_out_sum"


def test_update_pending_options_updates_contract(monkeypatch, tmp_path):
    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")
    monkeypatch.setattr(time, "time", lambda: 1000)

    ms.set_pending_intent(
        1,
        {"intent": "spend_sum", "days": 30, "merchant_contains": "каршерінг"},
        kind="category_alias",
        options=["Getmancar"],
    )
    ms.update_pending_options(1, ["Getmancar", "Aston express"])

    contract = ms.get_pending_contract(1, now_ts=1001)
    assert isinstance(contract, dict)
    assert contract.get("options") == ["Getmancar", "Aston express"]
    assert contract.get("entity_type") == "alias"
