from pathlib import Path

from mono_ai_budget_bot.uncat.prompting import UncatPromptMetaStore, build_uncat_prompt_message
from mono_ai_budget_bot.uncat.queue import UncatItem


def _items(*ids: str) -> list[UncatItem]:
    out: list[UncatItem] = []
    t = 100
    for i in ids:
        t += 1
        out.append(
            UncatItem(
                tx_id=i,
                time=t,
                account_id="a",
                amount=-12345,
                description=f"Shop {i}",
                mcc=5812,
                reason="purchase_without_rule",
            )
        )
    return out


def test_uncat_prompt_immediate_sends_on_new_queue_and_cooldown(tmp_path: Path):
    st = UncatPromptMetaStore(tmp_path / "meta")
    user_id = 1
    now = 1_000_000

    items1 = _items("t1", "t2")
    assert (
        st.should_send(user_id, frequency="immediate", items=items1, now_ts=now, mode="refresh")
        is True
    )
    st.mark_sent(user_id, items=items1, now_ts=now)

    assert (
        st.should_send(
            user_id, frequency="immediate", items=items1, now_ts=now + 10, mode="refresh"
        )
        is False
    )
    assert (
        st.should_send(
            user_id, frequency="immediate", items=items1, now_ts=now + 6 * 3600 - 1, mode="refresh"
        )
        is False
    )
    assert (
        st.should_send(
            user_id, frequency="immediate", items=items1, now_ts=now + 6 * 3600 + 1, mode="refresh"
        )
        is True
    )

    items2 = _items("t1", "t2", "t3")
    assert (
        st.should_send(
            user_id, frequency="immediate", items=items2, now_ts=now + 100, mode="refresh"
        )
        is True
    )


def test_uncat_prompt_daily_weekly_thresholds(tmp_path: Path):
    st = UncatPromptMetaStore(tmp_path / "meta")
    user_id = 2
    now = 2_000_000
    items = _items("a1")

    assert (
        st.should_send(user_id, frequency="daily", items=items, now_ts=now, mode="refresh") is True
    )
    st.mark_sent(user_id, items=items, now_ts=now)
    assert (
        st.should_send(
            user_id, frequency="daily", items=items, now_ts=now + 23 * 3600, mode="refresh"
        )
        is False
    )
    assert (
        st.should_send(
            user_id, frequency="daily", items=items, now_ts=now + 24 * 3600 + 1, mode="refresh"
        )
        is True
    )

    st.mark_sent(user_id, items=items, now_ts=now)
    assert (
        st.should_send(
            user_id, frequency="weekly", items=items, now_ts=now + 6 * 24 * 3600, mode="refresh"
        )
        is False
    )
    assert (
        st.should_send(
            user_id, frequency="weekly", items=items, now_ts=now + 7 * 24 * 3600 + 1, mode="refresh"
        )
        is True
    )


def test_uncat_prompt_before_report_only_in_report_mode(tmp_path: Path):
    st = UncatPromptMetaStore(tmp_path / "meta")
    user_id = 3
    now = 3_000_000
    items = _items("x1", "x2")

    assert (
        st.should_send(user_id, frequency="before_report", items=items, now_ts=now, mode="refresh")
        is False
    )
    assert (
        st.should_send(
            user_id, frequency="before_report", items=items, now_ts=now, mode="before_report"
        )
        is True
    )
    st.mark_sent(user_id, items=items, now_ts=now)

    assert (
        st.should_send(
            user_id, frequency="before_report", items=items, now_ts=now + 60, mode="before_report"
        )
        is False
    )

    items2 = _items("x1", "x2", "x3")
    assert (
        st.should_send(
            user_id, frequency="before_report", items=items2, now_ts=now + 60, mode="before_report"
        )
        is True
    )


def test_build_uncat_prompt_message_daily_lists_items():
    items = _items("t1", "t2", "t3")
    msg = build_uncat_prompt_message(items, frequency="daily")
    assert "Є некатегоризовані покупки" in msg
    assert "Кількість: 3" in msg
    assert "Shop t1" in msg
    assert "Shop t2" in msg
