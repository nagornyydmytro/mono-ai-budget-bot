from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from mono_ai_budget_bot.taxonomy.rules import Rule


class RulesStore:
    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or (Path(".cache") / "rules")
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, user_id: int) -> Path:
        return self.base_dir / f"{int(user_id)}.json"

    def load(self, user_id: int) -> list[Rule]:
        p = self._path(user_id)
        if not p.exists():
            return []
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return []
        if not isinstance(raw, list):
            return []

        out: list[Rule] = []
        for x in raw:
            if not isinstance(x, dict):
                continue
            rid = str(x.get("id") or "").strip()
            leaf_id = str(x.get("leaf_id") or "").strip()
            if not rid or not leaf_id:
                continue
            out.append(
                Rule(
                    id=rid,
                    leaf_id=leaf_id,
                    merchant_contains=(
                        str(x.get("merchant_contains")) if x.get("merchant_contains") else None
                    ),
                    recipient_contains=(
                        str(x.get("recipient_contains")) if x.get("recipient_contains") else None
                    ),
                    mcc_in=list(x.get("mcc_in")) if isinstance(x.get("mcc_in"), list) else None,
                    tx_kinds=list(x.get("tx_kinds"))
                    if isinstance(x.get("tx_kinds"), list)
                    else None,
                )
            )
        return out

    def save(self, user_id: int, rules: list[Rule]) -> None:
        self._path(user_id).write_text(
            json.dumps([asdict(r) for r in rules], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add(self, user_id: int, rule: Rule) -> None:
        rules = self.load(user_id)
        rules = [r for r in rules if r.id != rule.id]
        rules.append(rule)
        self.save(user_id, rules)
