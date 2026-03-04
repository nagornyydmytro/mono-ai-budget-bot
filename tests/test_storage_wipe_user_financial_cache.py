from __future__ import annotations

from pathlib import Path

from mono_ai_budget_bot.storage.report_store import ReportStore
from mono_ai_budget_bot.storage.rules_store import RulesStore
from mono_ai_budget_bot.storage.tx_store import TxStore
from mono_ai_budget_bot.storage.uncat_store import UncatStore
from mono_ai_budget_bot.storage.wipe import wipe_user_financial_cache
from mono_ai_budget_bot.uncat.pending import UncatPendingStore


def test_wipe_user_financial_cache_removes_user_files(tmp_path: Path) -> None:
    user_id = 123

    tx_store = TxStore(root_dir=tmp_path / "tx")
    report_store = ReportStore(root_dir=tmp_path / "reports")
    rules_store = RulesStore(base_dir=tmp_path / "rules")
    uncat_store = UncatStore(base_dir=tmp_path / "uncat")
    uncat_pending_store = UncatPendingStore(base_dir=tmp_path / "uncat_pending")

    (tx_store.root_dir / str(user_id)).mkdir(parents=True, exist_ok=True)
    (tx_store.root_dir / str(user_id) / "a.jsonl").write_text("{}", encoding="utf-8")
    (tx_store.root_dir / str(user_id) / "_meta.json").write_text("{}", encoding="utf-8")

    (report_store.root_dir / str(user_id)).mkdir(parents=True, exist_ok=True)
    (report_store.root_dir / str(user_id) / "facts_week.json").write_text("{}", encoding="utf-8")

    (rules_store.base_dir / f"{user_id}.json").write_text("{}", encoding="utf-8")
    (uncat_store.base_dir / f"{user_id}.json").write_text("{}", encoding="utf-8")
    (uncat_pending_store.base_dir / f"{user_id}.json").write_text("{}", encoding="utf-8")

    wipe_user_financial_cache(
        user_id,
        tx_store=tx_store,
        report_store=report_store,
        rules_store=rules_store,
        uncat_store=uncat_store,
        uncat_pending_store=uncat_pending_store,
    )

    assert not (tx_store.root_dir / str(user_id)).exists()
    assert not (report_store.root_dir / str(user_id)).exists()
    assert not (rules_store.base_dir / f"{user_id}.json").exists()
    assert not (uncat_store.base_dir / f"{user_id}.json").exists()
    assert not (uncat_pending_store.base_dir / f"{user_id}.json").exists()
