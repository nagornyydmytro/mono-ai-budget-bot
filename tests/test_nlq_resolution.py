import mono_ai_budget_bot.nlq.memory_store as ms
from mono_ai_budget_bot.nlq.executor import execute_intent
from mono_ai_budget_bot.nlq.resolver import (
    resolve_merchant_by_evidence,
    resolve_recipient_by_evidence,
)
from mono_ai_budget_bot.storage.user_store import UserConfig


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
    def __init__(self, amount: int, mcc: int | None, description: str):
        self.id = description
        self.time = 1000
        self.account_id = "acc"
        self.amount = amount
        self.mcc = mcc
        self.description = description
        self.currencyCode = 980


class DummyTxStore:
    def load_range(self, telegram_user_id: int, account_ids: list[str], ts_from: int, ts_to: int):
        return [
            Tx(amount=-120000, mcc=4829, description="P2P Anna K."),
            Tx(amount=-50000, mcc=4829, description="P2P Kate S."),
            Tx(amount=-25000, mcc=5411, description="ATB"),
            Tx(amount=-18000, mcc=5732, description="COMFY"),
        ]

    def aggregated_coverage_window(
        self,
        telegram_user_id: int,
        account_ids: list[str],
    ) -> tuple[int, int] | None:
        return None


def test_resolver_explicit_recipient_direct_match():
    rows = [
        Tx(amount=-120000, mcc=4829, description="P2P Anna K."),
        Tx(amount=-40000, mcc=4829, description="P2P Kate S."),
        Tx(amount=-25000, mcc=5411, description="ATB"),
    ]

    result = resolve_recipient_by_evidence(
        1,
        rows,
        alias="Anna",
        target="Anna",
        mode="explicit",
        intent_name="transfer_out_sum",
    )

    assert result.decision == "matched"
    assert result.display_values == ["P2P Anna K."]
    assert result.normalized_values == ["p2p anna k."]


def test_resolver_explicit_recipient_not_found():
    rows = [
        Tx(amount=-25000, mcc=5411, description="ATB"),
        Tx(amount=-18000, mcc=5732, description="COMFY"),
    ]

    result = resolve_recipient_by_evidence(
        1,
        rows,
        alias="Юлії",
        target="Юлії",
        mode="explicit",
        intent_name="transfer_out_sum",
    )

    assert result.decision == "not_found"
    assert result.display_values == []


def test_resolver_generic_recipient_clarify_uses_only_transfer_candidates():
    rows = [
        Tx(amount=-120000, mcc=4829, description="P2P Anna K."),
        Tx(amount=-50000, mcc=4829, description="P2P Kate S."),
        Tx(amount=-25000, mcc=5411, description="ATB"),
        Tx(amount=-18000, mcc=5732, description="COMFY"),
    ]

    result = resolve_recipient_by_evidence(
        1,
        rows,
        alias="другу",
        target="другу",
        mode="generic",
        intent_name="transfer_out_sum",
    )

    assert result.decision == "clarify"
    assert "P2P Anna K." in result.display_values
    assert "P2P Kate S." in result.display_values
    assert "ATB" not in result.display_values
    assert "COMFY" not in result.display_values


def test_resolver_merchant_alias_mapping(tmp_path, monkeypatch):
    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")
    ms.add_learned_mapping(1, bucket="category", alias="каршерінг", value="getmancar")
    ms.add_learned_mapping(1, bucket="category", alias="каршерінг", value="aston express")

    result = resolve_merchant_by_evidence(
        1,
        merchant_contains="каршерінг",
        merchant_targets=["каршерінг"],
    )

    assert result.decision == "matched"
    assert result.normalized_values == ["getmancar", "astonexpress"]


def test_executor_explicit_recipient_not_found_is_honest(tmp_path, monkeypatch):
    import mono_ai_budget_bot.nlq.executor as ex

    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")
    monkeypatch.setattr(ex, "UserStore", lambda: DummyUserStore())
    monkeypatch.setattr(ex, "TxStore", lambda: DummyTxStore())

    msg = execute_intent(
        1,
        {
            "intent": "transfer_out_sum",
            "days": 30,
            "recipient_alias": "Юлії",
            "recipient_target": "Юлії",
            "recipient_mode": "explicit",
            "recipient_explicit_name": True,
        },
    )

    assert "Не знайшов отримувача 'Юлії'" in msg


def test_executor_generic_recipient_clarify_does_not_mix_merchants(tmp_path, monkeypatch):
    import mono_ai_budget_bot.nlq.executor as ex

    monkeypatch.setattr(ms, "BASE_DIR", tmp_path / "memory")
    monkeypatch.setattr(ex, "UserStore", lambda: DummyUserStore())
    monkeypatch.setattr(ex, "TxStore", lambda: DummyTxStore())

    msg = execute_intent(
        1,
        {
            "intent": "transfer_out_sum",
            "days": 30,
            "recipient_alias": "другу",
            "recipient_target": "другу",
            "recipient_mode": "generic",
            "recipient_explicit_name": False,
        },
    )

    assert "Кого саме маєш на увазі" in msg
    assert "P2P Anna K." in msg
    assert "P2P Kate S." in msg
    assert "ATB" not in msg
    assert "COMFY" not in msg
