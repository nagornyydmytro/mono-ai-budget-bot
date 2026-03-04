from __future__ import annotations


def render_report(
    period: str,
    *,
    facts: dict,
    config,
    block_registry: dict[str, callable],
) -> str:
    enabled = config.get_enabled_blocks(period)
    out: list[str] = []
    for key in enabled:
        fn = block_registry.get(key)
        if fn is None:
            continue
        out.append(fn(facts))
    return "\n\n".join(out).strip()
