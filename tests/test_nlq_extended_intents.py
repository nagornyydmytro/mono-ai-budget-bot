import time

from mono_ai_budget_bot.nlq.executor import execute_intent
from mono_ai_budget_bot.nlq.router import parse_nlq_intent
from mono_ai_budget_bot.storage.user_store import UserConfig

NOW_TS = 40 * 86400 + 12 * 3600


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


class Tx:
    def __init__(
        self,
        *,
        tx_id: str,
        ts: int,
        amount: int,
        description: str,
        mcc: int | None,
    ):
        self.id = tx_id
        self.time = ts
        self.account_id = "acc"
        self.amount = amount
        self.description = description
        self.mcc = mcc
        self.currencyCode = 980


class DummyTxStore:
    def load_range(self, telegram_user_id: int, account_ids: list[str], ts_from: int, ts_to: int):
        return [
            Tx(tx_id="1", ts=NOW_TS - 2 * 86400, amount=-15000, description="SILPO", mcc=5411),
            Tx(tx_id="2", ts=NOW_TS - 3 * 86400, amount=-25000, description="WOLT", mcc=5812),
            Tx(
                tx_id="3", ts=NOW_TS - 5 * 86400, amount=-5000, description="COFFEE POINT", mcc=5814
            ),
            Tx(
                tx_id="4", ts=NOW_TS - 6 * 86400, amount=-3000, description="COFFEE POINT", mcc=5814
            ),
            Tx(
                tx_id="5", ts=NOW_TS - 9 * 86400, amount=-4000, description="COFFEE POINT", mcc=5814
            ),
            Tx(tx_id="6", ts=NOW_TS - 1 * 86400, amount=-10000, description="P2P мама", mcc=4829),
            Tx(tx_id="7", ts=NOW_TS - 8 * 86400, amount=-4000, description="P2P мама", mcc=4829),
            Tx(tx_id="8", ts=NOW_TS - 15 * 86400, amount=-5000, description="P2P мама", mcc=4829),
        ]

    def aggregated_coverage_window(
        self,
        telegram_user_id: int,
        account_ids: list[str],
    ) -> tuple[int, int] | None:
        return 0, NOW_TS + 86400


def test_router_threshold_count_over():
    parsed = parse_nlq_intent("Скільки витрат було більше 200 грн за 30 днів?")
    assert parsed["intent"] == "count_over"
    assert parsed["entity_kind"] == "spend"
    assert parsed["threshold_uah"] == 200.0


def test_router_threshold_count_under():
    parsed = parse_nlq_intent("Скільки витрат було менше 60 грн за 30 днів?")
    assert parsed["intent"] == "count_under"
    assert parsed["entity_kind"] == "spend"
    assert parsed["threshold_uah"] == 60.0


def test_router_threshold_query_without_count_phrasing():
    parsed = parse_nlq_intent("Які витрати були більше 100 грн за 30 днів?")
    assert parsed["intent"] == "threshold_query"
    assert parsed["entity_kind"] == "spend"
    assert parsed["threshold_uah"] == 100.0


def test_router_last_time_merchant():
    parsed = parse_nlq_intent("Коли востаннє я витрачав на силпо?")
    assert parsed["intent"] == "last_time"
    assert parsed["entity_kind"] == "spend"
    assert parsed["merchant_contains"] == "силпо"


def test_router_recurrence_category():
    parsed = parse_nlq_intent("Як часто я витрачаю на каву за 30 днів?")
    assert parsed["intent"] == "recurrence_summary"
    assert parsed["entity_kind"] == "spend"
    assert parsed["category"] == "Кафе/Ресторани"


def test_router_compare_to_baseline_recipient():
    parsed = parse_nlq_intent("На скільки більше я переказав мамі ніж зазвичай за 30 днів?")
    assert parsed["intent"] == "compare_to_baseline"
    assert parsed["entity_kind"] == "transfer_out"
    assert parsed["recipient_alias"] == "мамі"


def test_executor_extended_intents(monkeypatch):
    import mono_ai_budget_bot.nlq.executor as ex

    monkeypatch.setattr(ex, "UserStore", lambda: DummyUserStore())
    monkeypatch.setattr(ex, "TxStore", lambda: DummyTxStore())
    monkeypatch.setattr(time, "time", lambda: NOW_TS)
    monkeypatch.setattr(
        ex,
        "load_memory",
        lambda telegram_user_id: {
            "recipient_aliases": {"мамі": "мама"},
            "merchant_aliases": {},
            "category_aliases": {},
            "pending_intent": None,
            "pending_kind": None,
            "pending_options": None,
        },
    )
    monkeypatch.setattr(ex, "save_memory", lambda telegram_user_id, data: None)

    msg = execute_intent(
        1, {"intent": "count_over", "days": 30, "threshold_uah": 200.0, "entity_kind": "spend"}
    )
    assert "було 1 операцій більше 200.00 грн" in msg

    msg = execute_intent(
        1, {"intent": "count_under", "days": 30, "threshold_uah": 60.0, "entity_kind": "spend"}
    )
    assert "було 3 операцій менше 60.00 грн" in msg

    msg = execute_intent(
        1, {"intent": "threshold_query", "days": 30, "threshold_uah": 100.0, "entity_kind": "spend"}
    )
    assert "було 2 операцій більше 100.00 грн" in msg
    assert "Найбільша сума" in msg

    msg = execute_intent(
        1, {"intent": "last_time", "days": 30, "entity_kind": "spend", "merchant_contains": "силпо"}
    )
    assert "Остання операція була" in msg
    assert "SILPO" in msg
    assert "150.00 грн" in msg

    msg = execute_intent(
        1,
        {
            "intent": "recurrence_summary",
            "days": 30,
            "entity_kind": "spend",
            "category": "Кафе/Ресторани",
        },
    )
    assert "3 операцій у 3 активних днях" in msg
    assert "Медіанний інтервал" in msg

    msg = execute_intent(
        1,
        {
            "intent": "compare_to_baseline",
            "days": 30,
            "entity_kind": "transfer_out",
            "recipient_alias": "мамі",
        },
    )
    assert "Зазвичай" in msg
    assert "Різниця:" in msg


def test_executor_top_categories_biggest_category_format(monkeypatch):
    import mono_ai_budget_bot.nlq.executor as ex

    monkeypatch.setattr(ex, "UserStore", lambda: DummyUserStore())
    monkeypatch.setattr(ex, "TxStore", lambda: DummyTxStore())
    monkeypatch.setattr(time, "time", lambda: NOW_TS)
    monkeypatch.setattr(
        ex,
        "load_memory",
        lambda telegram_user_id: {
            "recipient_aliases": {},
            "merchant_aliases": {},
            "category_aliases": {},
            "pending_intent": None,
            "pending_kind": None,
            "pending_options": None,
        },
    )
    monkeypatch.setattr(ex, "save_memory", lambda telegram_user_id, data: None)

    msg = execute_intent(
        1,
        {
            "intent": "top_categories",
            "top_n": 1,
            "period_label": "цей місяць",
            "start_ts": NOW_TS - 7 * 86400,
            "end_ts": NOW_TS,
        },
    )
    assert "Цього місяця: найбільша категорія —" in msg
    assert "\n1. " not in msg
