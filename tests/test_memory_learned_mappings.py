import mono_ai_budget_bot.nlq.memory_store as ms


def test_learned_mappings_multi_select(tmp_path, monkeypatch):
    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")

    ms.add_learned_mapping(1, bucket="recipient", alias="мама", value="olena ivanovna")
    ms.add_learned_mapping(1, bucket="recipient", alias="мама", value="olena ivanovna")
    ms.add_learned_mapping(1, bucket="recipient", alias="мама", value="olena petrova")

    vals = ms.get_learned_mapping(1, bucket="recipient", alias="мама")
    assert vals is not None
    assert set(vals) == {"olena ivanovna", "olena petrova"}


def test_learned_mappings_respects_ttl_for_touch(tmp_path, monkeypatch):
    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")

    ms.add_learned_mapping(2, bucket="merchant", alias="мак", value="mcdonalds")
    vals = ms.get_learned_mapping(2, bucket="merchant", alias="мак")
    assert vals == ["mcdonalds"]

    mem = ms.load_memory(2)
    assert isinstance(mem.get("alias_stats"), dict)
