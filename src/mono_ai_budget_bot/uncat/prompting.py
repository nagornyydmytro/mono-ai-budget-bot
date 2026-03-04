from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mono_ai_budget_bot.bot.formatting import format_money_grn
from mono_ai_budget_bot.uncat.queue import UncatItem


@dataclass(frozen=True)
class UncatPromptMeta:
    last_sent_ts: int
    last_queue_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_sent_ts": int(self.last_sent_ts),
            "last_queue_hash": str(self.last_queue_hash),
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "UncatPromptMeta":
        return UncatPromptMeta(
            last_sent_ts=int(d.get("last_sent_ts") or 0),
            last_queue_hash=str(d.get("last_queue_hash") or ""),
        )


def _queue_hash(items: list[UncatItem]) -> str:
    ids = [x.tx_id for x in items[:50] if x.tx_id]
    payload = "|".join(ids).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:12]


class UncatPromptMetaStore:
    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or (Path(".cache") / "uncat_prompt_meta")
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, user_id: int) -> Path:
        return self.base_dir / f"{int(user_id)}.json"

    def load(self, user_id: int) -> UncatPromptMeta:
        p = self._path(user_id)
        if not p.exists():
            return UncatPromptMeta(last_sent_ts=0, last_queue_hash="")
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return UncatPromptMeta(last_sent_ts=0, last_queue_hash="")
        if not isinstance(raw, dict):
            return UncatPromptMeta(last_sent_ts=0, last_queue_hash="")
        return UncatPromptMeta.from_dict(raw)

    def save(self, user_id: int, meta: UncatPromptMeta) -> None:
        self._path(user_id).write_text(
            json.dumps(meta.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def should_send(
        self,
        user_id: int,
        *,
        frequency: str,
        items: list[UncatItem],
        now_ts: int | None = None,
        mode: str,
    ) -> bool:
        if not items:
            return False

        now = int(now_ts if now_ts is not None else time.time())
        meta = self.load(user_id)
        qh = _queue_hash(items)

        if frequency == "before_report":
            if mode != "before_report":
                return False
            if meta.last_queue_hash == qh and (now - meta.last_sent_ts) < 6 * 3600:
                return False
            return True

        if frequency == "immediate":
            if mode != "refresh":
                return False
            if meta.last_queue_hash != qh:
                return True
            return (now - meta.last_sent_ts) >= 6 * 3600

        if frequency == "daily":
            if mode != "refresh":
                return False
            return (now - meta.last_sent_ts) >= 24 * 3600

        if frequency == "weekly":
            if mode != "refresh":
                return False
            return (now - meta.last_sent_ts) >= 7 * 24 * 3600

        return False

    def mark_sent(self, user_id: int, *, items: list[UncatItem], now_ts: int | None = None) -> None:
        now = int(now_ts if now_ts is not None else time.time())
        qh = _queue_hash(items)
        self.save(user_id, UncatPromptMeta(last_sent_ts=now, last_queue_hash=qh))


def build_uncat_prompt_message(items: list[UncatItem], *, frequency: str) -> str:
    n = len(items)
    if frequency in ("daily", "weekly"):
        top = items[:8]
        lines = ["🧩 Є некатегоризовані покупки:", f"• Кількість: {n}", "", "Останні:"]
        for it in top:
            amt = abs(int(it.amount)) / 100.0
            lines.append(f"• {it.description} — {format_money_grn(amt)}")
        if n > len(top):
            lines.append(f"• …ще {n - len(top)}")
        lines.append("")
        lines.append("Натисни кнопку нижче, щоб розкласти по категоріях.")
        return "\n".join(lines)

    return "\n".join(
        [
            "🧩 Є некатегоризовані покупки.",
            f"• Кількість: {n}",
            "",
            "Натисни кнопку нижче, щоб розкласти по категоріях.",
        ]
    )
