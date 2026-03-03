import mono_ai_budget_bot.nlq.memory_store as ms


def test_pending_manual_mode_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")

    pid = ms.set_pending_manual_mode(
        1,
        expected="merchant_or_recipient",
        hint="type name from statement",
        source="nlq_other",
        ttl_sec=600,
    )
    assert isinstance(pid, str) and pid

    mode = ms.get_pending_manual_mode(1, now_ts=ms.load_memory(1)["pending_created_ts"])
    assert mode is not None
    assert mode["expected"] == "merchant_or_recipient"
    assert mode["hint"] == "type name from statement"
    assert mode["source"] == "nlq_other"

    popped = ms.pop_pending_manual_mode(1)
    assert popped is not None
    assert ms.get_pending_manual_mode(1, now_ts=9999999999) is None


def test_pending_manual_mode_expires(tmp_path, monkeypatch):
    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")

    ms.set_pending_manual_mode(2, expected="x", ttl_sec=1)
    mem = ms.load_memory(2)
    created = int(mem["pending_created_ts"])

    assert ms.get_pending_manual_mode(2, now_ts=created) is not None
    assert ms.get_pending_manual_mode(2, now_ts=created + 11) is None
