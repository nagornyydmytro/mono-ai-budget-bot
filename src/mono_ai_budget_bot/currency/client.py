from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx

from mono_ai_budget_bot.core.cache import JsonDiskCache
from mono_ai_budget_bot.core.rate_limit import FileRateLimiter
from mono_ai_budget_bot.currency.models import MonoCurrencyRate


def _sleep_seconds(attempt: int) -> float:
    base = min(10.0, 0.8 * (2**attempt))
    return base


def _retry_after_seconds(headers: httpx.Headers) -> float | None:
    ra = headers.get("Retry-After")
    if ra and ra.isdigit():
        return float(ra)
    return None


@dataclass(frozen=True)
class CurrencySnapshot:
    rates: list[MonoCurrencyRate]
    source: Literal["cache", "network", "stale_cache"]
    requested_refresh: bool
    fetch_failed_error: str | None = None


class MonobankPublicClient:
    CURRENCY_MIN_INTERVAL = 30
    CURRENCY_TTL = 300

    def __init__(
        self,
        base_url: str = "https://api.monobank.ua",
        *,
        cache_root: Path | None = None,
        http_client: httpx.Client | None = None,
    ):
        self._base_url = base_url.rstrip("/")

        cache_dir = cache_root or (Path(".cache") / "mono_public")
        self._cache = JsonDiskCache(cache_dir)
        self._limiter = FileRateLimiter(cache_dir / "ratelimit.json")

        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(
            base_url=self._base_url,
            headers={"User-Agent": "mono-ai-budget-bot/0.1.0"},
            timeout=httpx.Timeout(20.0),
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _request_json(self, path: str) -> object:
        max_attempts = 5
        last_err: Exception | None = None

        for attempt in range(max_attempts):
            try:
                resp = self._client.get(path)

                if resp.status_code == 429:
                    sleep_s = _retry_after_seconds(resp.headers)
                    if sleep_s is None:
                        sleep_s = min(60.0, _sleep_seconds(attempt))
                    time.sleep(sleep_s)
                    last_err = RuntimeError(
                        f"Monobank API error: 429 Too Many Requests. Response: {resp.text}"
                    )
                    continue

                if 500 <= resp.status_code <= 599:
                    time.sleep(min(20.0, _sleep_seconds(attempt)))
                    last_err = RuntimeError(
                        f"Monobank API error: {resp.status_code} {resp.reason_phrase}. Response: {resp.text}"
                    )
                    continue

                try:
                    resp.raise_for_status()
                except httpx.HTTPStatusError as e:
                    raise RuntimeError(
                        f"Monobank API error: {resp.status_code} {resp.reason_phrase}. Response: {resp.text}"
                    ) from e

                return resp.json()

            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_err = e
                time.sleep(min(20.0, _sleep_seconds(attempt)))
                continue

            except Exception as e:
                last_err = e
                break

        raise RuntimeError(f"Monobank request failed after retries: {path}. Last error: {last_err}")

    def currency_snapshot(self, *, force_refresh: bool = False) -> CurrencySnapshot:
        cache_key = "mono_public:bank-currency:v1"

        cached_entry = self._cache.get_entry(cache_key, allow_expired=True)
        cached_value = cached_entry.get("value") if cached_entry is not None else None
        cached_rates: list[MonoCurrencyRate] | None = None
        if isinstance(cached_value, list):
            cached_rates = [MonoCurrencyRate.model_validate(x) for x in cached_value]

        has_fresh_cache = (
            cached_rates is not None
            and cached_entry is not None
            and not bool(cached_entry.get("is_expired"))
        )

        if has_fresh_cache and not force_refresh:
            return CurrencySnapshot(
                rates=cached_rates,
                source="cache",
                requested_refresh=False,
                fetch_failed_error=None,
            )

        try:
            self._limiter.throttle(
                "mono_public:bank-currency", self.CURRENCY_MIN_INTERVAL, wait=True
            )
            data = self._request_json("/bank/currency")
            if not isinstance(data, list):
                raise RuntimeError("Monobank /bank/currency response is not a list")

            self._cache.set(cache_key, data, ttl_seconds=self.CURRENCY_TTL)
            return CurrencySnapshot(
                rates=[MonoCurrencyRate.model_validate(x) for x in data],
                source="network",
                requested_refresh=bool(force_refresh),
                fetch_failed_error=None,
            )
        except Exception as e:
            if cached_rates is not None:
                return CurrencySnapshot(
                    rates=cached_rates,
                    source="stale_cache",
                    requested_refresh=bool(force_refresh),
                    fetch_failed_error=str(e),
                )
            raise

    def currency(self, *, force_refresh: bool = False) -> list[MonoCurrencyRate]:
        return self.currency_snapshot(force_refresh=force_refresh).rates
