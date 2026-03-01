import mono_ai_budget_bot.nlq.executor as ex


def test_llm_alias_ranking_safe(monkeypatch):
    candidates = [("Getmancar", 500000), ("Aston express", 40000), ("Фора", 200000)]

    class DummyClient:
        def suggest_alias_candidates(self, *, alias: str, candidates: list[str]):
            return ["Aston express", "Getmancar"]

    monkeypatch.setattr(
        ex, "load_settings", lambda: type("S", (), {"openai_api_key": "x", "openai_model": "m"})()
    )
    monkeypatch.setattr(ex, "OpenAIClient", lambda api_key, model: DummyClient())

    ranked = ex._maybe_llm_rank_alias("каршерінг", candidates)
    assert ranked[0][0] == "Aston express"
    assert ranked[1][0] == "Getmancar"
