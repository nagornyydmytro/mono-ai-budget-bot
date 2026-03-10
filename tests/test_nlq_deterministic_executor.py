import time

from mono_ai_budget_bot.nlq.executor import execute_intent
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
            Tx(tx_id="1", ts=NOW_TS - 2 * 86400, amount=-15000, description="NOVUS", mcc=5411),
            Tx(tx_id="2", ts=NOW_TS - 4 * 86400, amount=-10000, description="NOVUS", mcc=5411),
            Tx(tx_id="3", ts=NOW_TS - 3 * 86400, amount=-9000, description="ATB", mcc=5411),
            Tx(tx_id="4", ts=NOW_TS - 7 * 86400, amount=-6000, description="ATB", mcc=5411),
            Tx(tx_id="5", ts=NOW_TS - 5 * 86400, amount=-2500, description="MCDONALDS", mcc=5814),
            Tx(tx_id="6", ts=NOW_TS - 8 * 86400, amount=-3500, description="KFC", mcc=5812),
            Tx(tx_id="7", ts=NOW_TS - 1 * 86400, amount=-5000, description="P2P брат", mcc=4829),
            Tx(tx_id="8", ts=NOW_TS - 9 * 86400, amount=-4000, description="P2P брат", mcc=4829),
            Tx(tx_id="9", ts=NOW_TS - 6 * 86400, amount=12000, description="Salary", mcc=None),
        ]

    def aggregated_coverage_window(
        self,
        telegram_user_id: int,
        account_ids: list[str],
    ) -> tuple[int, int] | None:
        return 0, NOW_TS + 86400


def _patch(monkeypatch):
    import mono_ai_budget_bot.nlq.executor as ex

    monkeypatch.setattr(ex, "UserStore", lambda: DummyUserStore())
    monkeypatch.setattr(ex, "TxStore", lambda: DummyTxStore())
    monkeypatch.setattr(time, "time", lambda: NOW_TS)
    monkeypatch.setattr(
        ex,
        "load_memory",
        lambda telegram_user_id: {
            "recipient_aliases": {"брату": "брат"},
            "merchant_aliases": {"новус": "novus", "атб": "atb"},
            "category_aliases": {},
            "pending_intent": None,
            "pending_kind": None,
            "pending_options": None,
        },
    )
    monkeypatch.setattr(ex, "save_memory", lambda telegram_user_id, data: None)


def test_executor_between_entities_sum(monkeypatch):
    _patch(monkeypatch)

    msg = execute_intent(
        1,
        {
            "intent": "between_entities",
            "entity_kind": "spend",
            "comparison_mode": "between_entities",
            "comparison_metric": "sum",
            "target_type": "merchant",
            "merchant_targets": ["novus", "atb"],
            "days": 30,
        },
    )

    assert "novus" in msg.lower()
    assert "atb" in msg.lower()
    assert "Різниця:" in msg
    assert "Більше припало на novus." in msg


def test_executor_between_entities_avg_ticket(monkeypatch):
    _patch(monkeypatch)

    msg = execute_intent(
        1,
        {
            "intent": "between_entities",
            "entity_kind": "spend",
            "comparison_mode": "between_entities",
            "comparison_metric": "avg_ticket",
            "target_type": "merchant",
            "merchant_targets": ["mcdonalds", "kfc"],
            "days": 30,
        },
    )

    assert "середній чек" in msg.lower()
    assert "mcdonalds" in msg.lower()
    assert "kfc" in msg.lower()


def test_executor_merchant_share_uses_proper_denominator(monkeypatch):
    _patch(monkeypatch)

    msg = execute_intent(
        1,
        {
            "intent": "merchant_share",
            "entity_kind": "spend",
            "merchant_contains": "novus",
            "merchant_targets": ["novus"],
            "days": 30,
        },
    )

    assert "novus" in msg.lower()
    assert "від усіх витрат" in msg
    assert "250.00 грн" in msg
    assert "54.35%" in msg
