from __future__ import annotations

from mono_ai_budget_bot.bot import templates


def _render(**kwargs) -> str:
    return templates.report_layout(
        header=kwargs.get("header", "HEADER"),
        facts_block=kwargs.get("facts_block", "FACTS"),
        trends_block=kwargs.get("trends_block"),
        anomalies_block=kwargs.get("anomalies_block"),
        insight_block=kwargs.get("insight_block"),
    )


def _assert_order(text: str, *parts: str) -> None:
    idx = -1
    for p in parts:
        j = text.find(p)
        assert j != -1, f"Missing part: {p!r}\n{text}"
        assert j > idx, f"Wrong order for part: {p!r}\n{text}"
        idx = j


def _extract_divider_line(text: str) -> str | None:
    lines = [ln.rstrip("\n") for ln in text.splitlines()]
    candidates: dict[str, int] = {}
    for ln in lines:
        s = ln.strip()
        if len(s) < 6:
            continue
        uniq = set(s)
        if len(uniq) == 1 and s[0] in {"-", "—", "─", "_", "="}:
            candidates[s] = candidates.get(s, 0) + 1
    if not candidates:
        return None
    return max(candidates.items(), key=lambda x: x[1])[0]


def test_layout_facts_only():
    text = _render(trends_block=None, anomalies_block=None, insight_block=None)
    _assert_order(text, "HEADER", "FACTS")
    assert "TRENDS" not in text
    assert "ANOM" not in text
    assert "AI" not in text

    divider = _extract_divider_line(text)
    if divider is not None:
        assert text.count(divider) <= 1


def test_layout_with_trends_and_ai():
    text = _render(trends_block="TRENDS", anomalies_block=None, insight_block="AI")
    _assert_order(text, "HEADER", "FACTS", "TRENDS", "AI")
    assert "ANOM" not in text

    divider = _extract_divider_line(text)
    assert divider is not None
    assert text.count(divider) >= 2


def test_layout_full_blocks():
    text = _render(trends_block="TRENDS", anomalies_block="ANOM", insight_block="AI")
    _assert_order(text, "HEADER", "FACTS", "TRENDS", "ANOM", "AI")

    divider = _extract_divider_line(text)
    assert divider is not None
    assert text.count(divider) >= 3
