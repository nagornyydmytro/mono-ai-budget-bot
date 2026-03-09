import time
from pathlib import Path

from mono_ai_budget_bot.reports.renderer import render_report_for_user
from mono_ai_budget_bot.storage.reports_store import ReportsStore
from mono_ai_budget_bot.storage.user_store import UserConfig


def test_reports_renderer_includes_coverage_warning(tmp_path: Path) -> None:
    rs = ReportsStore(base_dir=tmp_path / "reports_cfg")
    tg_id = 1

    facts = {
        "totals": {
            "real_spend_total_uah": 0.0,
            "spend_total_uah": 0.0,
            "income_total_uah": 0.0,
            "transfer_in_total_uah": 0.0,
            "transfer_out_total_uah": 0.0,
        },
        "coverage": {
            "coverage_from_ts": 200,
            "coverage_to_ts": 300,
            "requested_from_ts": 100,
            "requested_to_ts": 400,
        },
    }

    text = render_report_for_user(rs, tg_id, "week", facts)
    assert "⚠️ Дані неповні для запитаного періоду." in text
    assert "Coverage:" in text


def test_nlq_executor_prepends_coverage_warning(monkeypatch) -> None:
    import mono_ai_budget_bot.nlq.executor as ex
    from mono_ai_budget_bot.nlq.executor import execute_intent

    class DummyUserStore:
        def load(self, telegram_user_id: int):
            return UserConfig(
                telegram_user_id=telegram_user_id,
                mono_token="t",
                selected_account_ids=["acc"],
                chat_id=None,
                autojobs_enabled=False,
                updated_at=0.0,
            )

    class DummyTxStore:
        def load_range(
            self, telegram_user_id: int, account_ids: list[str], ts_from: int, ts_to: int
        ):
            return []

        def aggregated_coverage_window(
            self,
            telegram_user_id: int,
            account_ids: list[str],
        ) -> tuple[int, int] | None:
            return 200, 300

    monkeypatch.setattr(ex, "UserStore", lambda: DummyUserStore())
    monkeypatch.setattr(ex, "TxStore", lambda: DummyTxStore())
    monkeypatch.setattr(time, "time", lambda: 1000)

    s = execute_intent(1, {"intent": "spend_count", "days": 1})
    assert s.startswith("⚠️ Дані неповні для запитаного періоду.")
    assert "Coverage:" in s


def test_nlq_executor_prepends_missing_warning_when_no_coverage(monkeypatch) -> None:
    import mono_ai_budget_bot.nlq.executor as ex
    from mono_ai_budget_bot.nlq.executor import execute_intent

    class DummyUserStore:
        def load(self, telegram_user_id: int):
            return UserConfig(
                telegram_user_id=telegram_user_id,
                mono_token="t",
                selected_account_ids=["acc"],
                chat_id=None,
                autojobs_enabled=False,
                updated_at=0.0,
            )

    class DummyTxStore:
        def load_range(
            self, telegram_user_id: int, account_ids: list[str], ts_from: int, ts_to: int
        ):
            return []

        def aggregated_coverage_window(
            self,
            telegram_user_id: int,
            account_ids: list[str],
        ) -> tuple[int, int] | None:
            return None

    monkeypatch.setattr(ex, "UserStore", lambda: DummyUserStore())
    monkeypatch.setattr(ex, "TxStore", lambda: DummyTxStore())
    monkeypatch.setattr(time, "time", lambda: 1000)

    s = execute_intent(1, {"intent": "spend_count", "days": 1})
    assert s.startswith("⚠️ Немає даних для запитаного періоду.")


def test_nlq_executor_suppresses_partial_warning_for_small_right_edge_lag(monkeypatch) -> None:
    import mono_ai_budget_bot.nlq.executor as ex
    from mono_ai_budget_bot.nlq.executor import execute_intent

    class DummyUserStore:
        def load(self, telegram_user_id: int):
            return UserConfig(
                telegram_user_id=telegram_user_id,
                mono_token="t",
                selected_account_ids=["acc"],
                chat_id=None,
                autojobs_enabled=False,
                updated_at=0.0,
            )

    class DummyTx:
        def __init__(self):
            self.id = "1"
            self.time = 1000 - 300
            self.account_id = "acc"
            self.amount = -10000
            self.description = "NOVUS"
            self.mcc = 5411
            self.currencyCode = 980

    class DummyTxStore:
        def load_range(
            self, telegram_user_id: int, account_ids: list[str], ts_from: int, ts_to: int
        ):
            return [DummyTx()]

        def aggregated_coverage_window(
            self,
            telegram_user_id: int,
            account_ids: list[str],
        ) -> tuple[int, int] | None:
            return 200, 1000 - 120

    monkeypatch.setattr(ex, "UserStore", lambda: DummyUserStore())
    monkeypatch.setattr(ex, "TxStore", lambda: DummyTxStore())
    monkeypatch.setattr(time, "time", lambda: 1000)

    s = execute_intent(1, {"intent": "spend_sum", "days": 1})
    assert not s.startswith("⚠️ Дані неповні для запитаного періоду.")
