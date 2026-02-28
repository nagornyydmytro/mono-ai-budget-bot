from __future__ import annotations

import hashlib
import random
import time
from pathlib import Path

import httpx

from ..core.cache import JsonDiskCache
from ..core.rate_limit import FileRateLimiter
from .models import MonoClientInfo, MonoStatementItem


def _sleep_seconds(attempt: int) -> float:
    base = min(20.0, 1.2 * (2**attempt))
    return base + random.random() * 0.8


def _retry_after_seconds(headers: httpx.Headers) -> float | None:
    ra = headers.get("Retry-After")
    if ra and ra.isdigit():
        return float(ra)
    return None


class MonobankClient:
    CLIENT_INFO_MIN_INTERVAL = 60
    STATEMENT_MIN_INTERVAL = 60

    CLIENT_INFO_TTL = 600
    STATEMENT_TTL = 600

    def __init__(self, token: str, base_url: str = "https://api.monobank.ua"):
        self._token = token
        self._base_url = base_url.rstrip("/")

        cache_root = Path(".cache") / "mono"
        self._cache = JsonDiskCache(cache_root)
        self._limiter = FileRateLimiter(cache_root / "ratelimit.json")

        self._token_hash = hashlib.sha256(self._token.encode("utf-8")).hexdigest()[:12]

        self._client = httpx.Client(
            base_url=self._base_url,
            headers={
                "X-Token": self._token,
                "User-Agent": "mono-ai-budget-bot/0.1.0",
            },
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
                        sleep_s = min(90.0, _sleep_seconds(attempt))
                    time.sleep(sleep_s)
                    last_err = RuntimeError(
                        f"Monobank API error: 429 Too Many Requests. Response: {resp.text}"
                    )
                    continue

                if 500 <= resp.status_code <= 599:
                    time.sleep(min(30.0, _sleep_seconds(attempt)))
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
                time.sleep(min(30.0, _sleep_seconds(attempt)))
                continue

            except Exception as e:
                last_err = e
                break

        raise RuntimeError(f"Monobank request failed after retries: {path}. Last error: {last_err}")

    def client_info(self) -> MonoClientInfo:
        cache_key = f"mono:client-info:{self._token_hash}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return MonoClientInfo.model_validate(cached)

        self._limiter.throttle(
            f"mono:client-info:{self._token_hash}",
            self.CLIENT_INFO_MIN_INTERVAL,
            wait=True,
        )

        data = self._request_json("/personal/client-info")
        self._cache.set(cache_key, data, ttl_seconds=self.CLIENT_INFO_TTL)
        return MonoClientInfo.model_validate(data)

    def statement(self, account: str, date_from: int, date_to: int) -> list[MonoStatementItem]:
        cache_key = f"mono:statement:{self._token_hash}:{account}:{date_from}:{date_to}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return [MonoStatementItem.model_validate(x) for x in cached]

        out = self._statement_paginated(account=account, date_from=date_from, date_to=date_to)

        self._cache.set(cache_key, out, ttl_seconds=self.STATEMENT_TTL)
        return [MonoStatementItem.model_validate(x) for x in out]

    def _statement_paginated(self, account: str, date_from: int, date_to: int) -> list[dict]:
        limiter_key = f"mono:statement:{self._token_hash}:{account}"

        out: list[dict] = []
        seen: set[str] = set()

        cur_to = int(date_to)
        date_from = int(date_from)

        while True:
            if cur_to <= date_from:
                break

            self._limiter.throttle(
                limiter_key,
                self.STATEMENT_MIN_INTERVAL,
                wait=True,
            )

            batch = self._request_json(f"/personal/statement/{account}/{date_from}/{cur_to}")
            if not isinstance(batch, list):
                raise RuntimeError("Monobank statement response is not a list")

            for x in batch:
                if not isinstance(x, dict):
                    continue
                tx_id = x.get("id")
                if not isinstance(tx_id, str):
                    continue
                if tx_id in seen:
                    continue
                seen.add(tx_id)
                out.append(x)

            if len(batch) < 500:
                break

            oldest_time: int | None = None
            for x in batch:
                if isinstance(x, dict):
                    t = x.get("time")
                    if isinstance(t, int):
                        if oldest_time is None or t < oldest_time:
                            oldest_time = t

            if oldest_time is None:
                break

            new_to = oldest_time - 1
            if new_to >= cur_to:
                new_to = cur_to - 1
            cur_to = new_to

        return out
