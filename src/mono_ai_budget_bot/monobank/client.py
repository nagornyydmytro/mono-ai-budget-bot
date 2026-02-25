from pathlib import Path

import httpx, random, time, hashlib

from ..core.cache import JsonDiskCache
from ..core.rate_limit import FileRateLimiter
from .models import MonoClientInfo, MonoStatementItem


class MonobankClient:
    CLIENT_INFO_MIN_INTERVAL = 60
    STATEMENT_MIN_INTERVAL = 60

    CLIENT_INFO_TTL = 600  # 10 min
    STATEMENT_TTL = 600  # 10 min

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
        # robust retries for 429 + transient network errors
        max_attempts = 6
        base_sleep = 2.0  # seconds

        last_err: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                resp = self._client.get(path)

                # 429 Too Many Requests
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        sleep_s = float(retry_after)
                    else:
                        # exponential backoff with jitter
                        sleep_s = min(60.0, base_sleep * (2 ** (attempt - 1)))
                        sleep_s += random.uniform(0.0, 1.5)

                    time.sleep(sleep_s)
                    continue

                # other errors
                try:
                    resp.raise_for_status()
                except httpx.HTTPStatusError as e:
                    raise RuntimeError(
                        f"Monobank API error: {resp.status_code} {resp.reason_phrase}. Response: {resp.text}"
                    ) from e

                return resp.json()

            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_err = e
                # retry with backoff
                sleep_s = min(30.0, base_sleep * (2 ** (attempt - 1)))
                sleep_s += random.uniform(0.0, 1.0)
                time.sleep(sleep_s)
                continue

            except Exception as e:
                last_err = e
                break

        raise RuntimeError(f"Monobank request failed after retries: {path}. Last error: {last_err}")

    def client_info(self) -> MonoClientInfo:
        cache_key = "mono:client-info"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return MonoClientInfo.model_validate(cached)

        # rate limit protection
        self._limiter.throttle(f"mono:client-info:{self._token_hash}", self.CLIENT_INFO_MIN_INTERVAL, wait=True)

        data = self._request_json("/personal/client-info")
        self._cache.set(cache_key, data, ttl_seconds=self.CLIENT_INFO_TTL)
        return MonoClientInfo.model_validate(data)

    def statement(self, account: str, date_from: int, date_to: int) -> list[MonoStatementItem]:
        cache_key = f"mono:statement:{account}:{date_from}:{date_to}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return [MonoStatementItem.model_validate(x) for x in cached]

        # rate limit protection (Monobank: statement is limited too)
        self._limiter.throttle(f"mono:client-info:{self._token_hash}", self.CLIENT_INFO_MIN_INTERVAL, wait=True)
        
        data = self._request_json(f"/personal/statement/{account}/{date_from}/{date_to}")
        # Monobank returns list
        self._cache.set(cache_key, data, ttl_seconds=self.STATEMENT_TTL)
        return [MonoStatementItem.model_validate(x) for x in data]