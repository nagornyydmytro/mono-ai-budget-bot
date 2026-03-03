from __future__ import annotations

import time
from pathlib import Path

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


class MonobankPublicClient:
    CURRENCY_MIN_INTERVAL = 30
    CURRENCY_TTL = 300

    def __init__(self, base_url: str = "https://api.monobank.ua"):
        self._base_url = base_url.rstrip("/")

        cache_root = Path(".cache") / "mono_public"
        self._cache = JsonDiskCache(cache_root)
        self._limiter = FileRateLimiter(cache_root / "ratelimit.json")

        self._client = httpx.Client(
            base_url=self._base_url,
            headers={"User-Agent": "mono-ai-budget-bot/0.1.0"},
            timeout=httpx.Timeout(20.0),
        )

    def close(self) -> None:
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

    def currency(self, *, force_refresh: bool = False) -> list[MonoCurrencyRate]:
        cache_key = "mono_public:bank-currency:v1"

        if force_refresh:
            self._cache.delete(cache_key)

        cached = self._cache.get(cache_key)
        if cached is not None:
            if isinstance(cached, list):
                return [MonoCurrencyRate.model_validate(x) for x in cached]
            return []

        self._limiter.throttle("mono_public:bank-currency", self.CURRENCY_MIN_INTERVAL, wait=True)

        data = self._request_json("/bank/currency")
        if not isinstance(data, list):
            raise RuntimeError("Monobank /bank/currency response is not a list")

        self._cache.set(cache_key, data, ttl_seconds=self.CURRENCY_TTL)
        return [MonoCurrencyRate.model_validate(x) for x in data]
