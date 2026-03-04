from __future__ import annotations

from pathlib import Path

from mono_ai_budget_bot.storage.report_store import ReportStore
from mono_ai_budget_bot.storage.rules_store import RulesStore
from mono_ai_budget_bot.storage.tx_store import TxStore
from mono_ai_budget_bot.storage.uncat_store import UncatStore
from mono_ai_budget_bot.uncat.pending import UncatPendingStore


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def _safe_rmtree(path: Path) -> None:
    if not path.exists():
        return
    if path.is_file():
        _safe_unlink(path)
        return
    for p in sorted(path.rglob("*"), reverse=True):
        if p.is_file():
            _safe_unlink(p)
        else:
            try:
                p.rmdir()
            except FileNotFoundError:
                pass
            except OSError:
                pass
    try:
        path.rmdir()
    except FileNotFoundError:
        return
    except OSError:
        return


def wipe_user_financial_cache(
    telegram_user_id: int,
    *,
    tx_store: TxStore,
    report_store: ReportStore,
    rules_store: RulesStore,
    uncat_store: UncatStore,
    uncat_pending_store: UncatPendingStore,
) -> None:
    _safe_rmtree(tx_store.root_dir / str(int(telegram_user_id)))
    _safe_rmtree(report_store.root_dir / str(int(telegram_user_id)))

    _safe_unlink(rules_store.base_dir / f"{int(telegram_user_id)}.json")
    _safe_unlink(uncat_store.base_dir / f"{int(telegram_user_id)}.json")
    _safe_unlink(uncat_pending_store.base_dir / f"{int(telegram_user_id)}.json")
