from pathlib import Path

import mono_ai_budget_bot.core.cache as cache_mod
import mono_ai_budget_bot.currency.client as client_mod
from mono_ai_budget_bot.bot.renderers import render_currency_screen_text
from mono_ai_budget_bot.currency.client import CurrencySnapshot, MonobankPublicClient
from mono_ai_budget_bot.currency.models import MonoCurrencyRate


def _sample_rates() -> list[dict]:
    return [
        {
            "currencyCodeA": 840,
            "currencyCodeB": 980,
            "date": 1_700_000_000,
            "rateBuy": 40.0,
            "rateSell": 41.0,
            "rateCross": None,
        },
        {
            "currencyCodeA": 978,
            "currencyCodeB": 980,
            "date": 1_700_000_000,
            "rateBuy": 43.0,
            "rateSell": 44.0,
            "rateCross": None,
        },
        {
            "currencyCodeA": 985,
            "currencyCodeB": 980,
            "date": 1_700_000_000,
            "rateBuy": None,
            "rateSell": None,
            "rateCross": 10.0,
        },
    ]


def test_currency_snapshot_uses_fresh_cache_without_network(monkeypatch, tmp_path: Path):
    client = MonobankPublicClient(cache_root=tmp_path / "mono_public")
    client._cache.set("mono_public:bank-currency:v1", _sample_rates(), ttl_seconds=300)

    monkeypatch.setattr(
        client,
        "_request_json",
        lambda path: (_ for _ in ()).throw(AssertionError("network must not be called")),
    )

    try:
        snapshot = client.currency_snapshot(force_refresh=False)
    finally:
        client.close()

    assert snapshot.source == "cache"
    assert snapshot.requested_refresh is False
    assert snapshot.fetch_failed_error is None
    assert len(snapshot.rates) == 3


def test_currency_snapshot_force_refresh_falls_back_to_stale_cache_on_fetch_failure(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setattr(cache_mod.time, "time", lambda: 1000)
    monkeypatch.setattr(client_mod.time, "time", lambda: 1000)

    client = MonobankPublicClient(cache_root=tmp_path / "mono_public")
    client._cache.set("mono_public:bank-currency:v1", _sample_rates(), ttl_seconds=10)

    monkeypatch.setattr(cache_mod.time, "time", lambda: 2000)
    monkeypatch.setattr(client_mod.time, "time", lambda: 2000)
    monkeypatch.setattr(
        client, "_request_json", lambda path: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    try:
        snapshot = client.currency_snapshot(force_refresh=True)
    finally:
        client.close()

    assert snapshot.source == "stale_cache"
    assert snapshot.requested_refresh is True
    assert snapshot.fetch_failed_error == "boom"
    assert len(snapshot.rates) == 3


def test_currency_snapshot_without_cache_raises_on_fetch_failure(monkeypatch, tmp_path: Path):
    client = MonobankPublicClient(cache_root=tmp_path / "mono_public")
    monkeypatch.setattr(
        client, "_request_json", lambda path: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    try:
        try:
            client.currency_snapshot(force_refresh=True)
            raise AssertionError("RuntimeError was expected")
        except RuntimeError as e:
            assert "boom" in str(e)
    finally:
        client.close()


def test_render_currency_screen_text_shows_cache_freshness_and_refresh_failure():
    snapshot = CurrencySnapshot(
        rates=[
            MonoCurrencyRate(
                currencyCodeA=840,
                currencyCodeB=980,
                date=1_700_000_000,
                rateBuy=40.0,
                rateSell=41.0,
                rateCross=None,
            ),
            MonoCurrencyRate(
                currencyCodeA=978,
                currencyCodeB=980,
                date=1_700_000_000,
                rateBuy=43.0,
                rateSell=44.0,
                rateCross=None,
            ),
            MonoCurrencyRate(
                currencyCodeA=985,
                currencyCodeB=980,
                date=1_700_000_000,
                rateBuy=None,
                rateSell=None,
                rateCross=10.0,
            ),
        ],
        source="stale_cache",
        requested_refresh=True,
        fetch_failed_error="boom",
    )

    text = render_currency_screen_text(snapshot)

    assert "Джерело: останній кеш" in text
    assert "⚠️ Оновлення не вдалося, показую останній доступний кеш." in text
    assert "USD/UAH" in text
    assert "EUR/UAH" in text
    assert "PLN/UAH" in text


def test_render_currency_screen_text_shows_cache_source_label():
    snapshot = CurrencySnapshot(
        rates=[
            MonoCurrencyRate(
                currencyCodeA=840,
                currencyCodeB=980,
                date=1_700_000_000,
                rateBuy=40.0,
                rateSell=41.0,
                rateCross=None,
            )
        ],
        source="cache",
        requested_refresh=False,
        fetch_failed_error=None,
    )

    text = render_currency_screen_text(snapshot)

    assert "Джерело: кеш" in text
    assert "Monobank API" not in text
    assert "Оновлення не вдалося" not in text


def test_render_currency_screen_text_shows_network_refresh_label():
    snapshot = CurrencySnapshot(
        rates=[
            MonoCurrencyRate(
                currencyCodeA=840,
                currencyCodeB=980,
                date=1_700_000_000,
                rateBuy=40.0,
                rateSell=41.0,
                rateCross=None,
            )
        ],
        source="network",
        requested_refresh=True,
        fetch_failed_error=None,
    )

    text = render_currency_screen_text(snapshot)

    assert "Джерело: Monobank API (refresh)" in text
    assert "Оновлення не вдалося" not in text


def test_currency_snapshot_force_refresh_uses_network_when_fetch_succeeds(
    monkeypatch, tmp_path: Path
):
    client = MonobankPublicClient(cache_root=tmp_path / "mono_public")
    client._cache.set("mono_public:bank-currency:v1", _sample_rates(), ttl_seconds=300)
    monkeypatch.setattr(client, "_request_json", lambda path: _sample_rates())

    try:
        snapshot = client.currency_snapshot(force_refresh=True)
    finally:
        client.close()

    assert snapshot.source == "network"
    assert snapshot.requested_refresh is True
    assert snapshot.fetch_failed_error is None
    assert len(snapshot.rates) == 3
