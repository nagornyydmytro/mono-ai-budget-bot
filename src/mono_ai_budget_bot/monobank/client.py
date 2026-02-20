import httpx
from .models import MonoClientInfo


class MonobankClient:
    def __init__(self, token: str, base_url: str = "https://api.monobank.ua"):
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={"X-Token": self._token, "User-Agent": "mono-ai-budget-bot/0.1.0"},
            timeout=httpx.Timeout(20.0),
        )

    def close(self) -> None:
        self._client.close()

    def client_info(self) -> MonoClientInfo:
        resp = self._client.get("/personal/client-info")
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            # Monobank часто повертає короткий текст — його корисно бачити
            raise RuntimeError(
                f"Monobank API error: {resp.status_code} {resp.reason_phrase}. "
                f"Response: {resp.text}"
            ) from e
        return MonoClientInfo.model_validate(resp.json())