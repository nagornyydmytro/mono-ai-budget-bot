from __future__ import annotations

from typing import Callable, Dict, List

from mono_ai_budget_bot.reports.config import ReportsConfig

BlockFn = Callable[[dict], str | None]


def render_report(
    period: str,
    facts: dict,
    config: ReportsConfig,
    block_registry: Dict[str, BlockFn],
) -> str:
    blocks: List[str] = []

    enabled_blocks = config.get_enabled_blocks(period)

    for block_name in enabled_blocks:
        fn = block_registry.get(block_name)
        if not fn:
            continue

        text = fn(facts)

        if text:
            blocks.append(text)

    return "\n\n".join(blocks)
