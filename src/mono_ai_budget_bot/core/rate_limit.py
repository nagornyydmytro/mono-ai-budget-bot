import json
import time
from pathlib import Path


class FileRateLimiter:
    """
    Simple file-based rate limiter that persists between runs.
    Keeps last call time per key in a JSON file.
    """

    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, float]:
        if not self.state_file.exists():
            return {}
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                # ensure floats
                return {k: float(v) for k, v in data.items()}
        except Exception:
            pass
        return {}

    def _save(self, state: dict[str, float]) -> None:
        self.state_file.write_text(json.dumps(state), encoding="utf-8")

    def throttle(self, key: str, min_interval_seconds: int, wait: bool = True) -> None:
        state = self._load()
        now = time.time()
        last = state.get(key, None)

        if last is not None:
            elapsed = now - last
            remaining = min_interval_seconds - elapsed
            if remaining > 0:
                if wait:
                    time.sleep(remaining)
                else:
                    raise RuntimeError(
                        f"Rate limit: wait {remaining:.1f}s before calling '{key}' again"
                    )

        # record call time as "now" (after potential sleep)
        state[key] = time.time()
        self._save(state)
