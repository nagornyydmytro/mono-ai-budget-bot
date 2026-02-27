import hashlib
import random
import time
from pathlib import Path

import httpx

from ..core.cache import JsonDiskCache
from ..core.rate_limit import FileRateLimiter
from .models import MonoClientInfo, MonoStatementItem


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
        max_attempts = 6
        base_sleep = 2.0

        last_err: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                resp = self._client.get(path)

                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        sleep_s = float(retry_after)
                    else:
                        sleep_s = min(60.0, base_sleep * (2 ** (attempt - 1)))
                        sleep_s += random.uniform(0.0, 1.5)

                    time.sleep(sleep_s)
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
                sleep_s = min(30.0, base_sleep * (2 ** (attempt - 1)))
                sleep_s += random.uniform(0.0, 1.0)
                time.sleep(sleep_s)
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
            f"mono:client-info:{self._token_hash}", self.CLIENT_INFO_MIN_INTERVAL, wait=True
        )

        data = self._request_json("/personal/client-info")
        self._cache.set(cache_key, data, ttl_seconds=self.CLIENT_INFO_TTL)
        return MonoClientInfo.model_validate(data)

    def statement(self, account: str, date_from: int, date_to: int) -> list[MonoStatementItem]:
        cache_key = f"mono:statement:{self._token_hash}:{account}:{date_from}:{date_to}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return [MonoStatementItem.model_validate(x) for x in cached]

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

        self._cache.set(cache_key, out, ttl_seconds=self.STATEMENT_TTL)
        return [MonoStatementItem.model_validate(x) for x in out]
