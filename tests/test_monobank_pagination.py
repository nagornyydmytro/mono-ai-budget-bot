from mono_ai_budget_bot.monobank.client import MonobankClient


class DummyCache:
    def __init__(self):
        self._data = {}

    def get(self, key):
        return self._data.get(key)

    def set(self, key, value, ttl_seconds=None):
        self._data[key] = value


class DummyLimiter:
    def throttle(self, *args, **kwargs):
        return None


def _mk_batch(start_time: int, count: int) -> list[dict]:
    return [
        {"id": f"tx_{start_time - i}", "time": start_time - i, "amount": 100} for i in range(count)
    ]


def test_statement_paginates_when_500_and_dedups_and_caches(monkeypatch):
    mb = MonobankClient(token="t")
    mb._cache = DummyCache()
    mb._limiter = DummyLimiter()

    batch1 = [{"id": f"tx_{2000 - i}", "time": 2000 - i, "amount": 100} for i in range(500)]
    batch2 = [{"id": f"tx_{1500 - i}", "time": 1500 - i, "amount": 100} for i in range(500)]
    batch3 = [{"id": f"tx_{1000 - i}", "time": 1000 - i, "amount": 100} for i in range(120)]

    batch2[10]["id"] = batch1[20]["id"]

    calls: list[str] = []
    batches = [batch1, batch2, batch3]

    def fake_request_json(path: str):
        calls.append(path)
        return batches.pop(0)

    monkeypatch.setattr(mb, "_request_json", fake_request_json)

    res1 = mb.statement(account="acc", date_from=0, date_to=2000)

    ids = [x.id for x in res1]
    assert len(ids) == len(set(ids))
    assert len(res1) == 1119
    assert len(calls) == 3

    res2 = mb.statement(account="acc", date_from=0, date_to=2000)
    assert len(res2) == len(res1)
    assert len(calls) == 3

    mb.close()


def test_statement_does_not_loop_on_same_timestamp(monkeypatch):
    mb = MonobankClient(token="t")
    mb._cache = DummyCache()
    mb._limiter = DummyLimiter()

    batch1 = [{"id": f"tx_{i}", "time": 1000, "amount": 1} for i in range(500)]

    calls: list[str] = []
    batches = [batch1, []]

    def fake_request_json(path: str):
        calls.append(path)
        return batches.pop(0)

    monkeypatch.setattr(mb, "_request_json", fake_request_json)

    res = mb.statement(account="acc", date_from=0, date_to=2000)

    assert len(res) == 500
    assert len(calls) == 2

    mb.close()
