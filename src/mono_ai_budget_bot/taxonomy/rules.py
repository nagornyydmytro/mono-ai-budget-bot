from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal, Optional, Sequence

from mono_ai_budget_bot.storage.tx_store import TxRecord
from mono_ai_budget_bot.taxonomy.models import TaxKind, _node, is_leaf

Bucket = Literal["real_income", "real_expense", "turnover", "needs_clarify"]


@dataclass(frozen=True)
class Rule:
    id: str
    leaf_id: str
    merchant_contains: Optional[str] = None
    recipient_contains: Optional[str] = None
    mcc_in: Optional[Sequence[int]] = None
    tx_kinds: Optional[Sequence[str]] = None


@dataclass(frozen=True)
class Categorization:
    bucket: Bucket
    leaf_id: Optional[str]
    reason: str


def _norm(s: str | None) -> str:
    return " ".join((s or "").strip().lower().split())


def _match_contains(hay: str, needle: str) -> bool:
    h = _norm(hay).replace(" ", "")
    n = _norm(needle).replace(" ", "")
    if not n:
        return False
    return n in h


def _iter_leaf_ids(tax: dict[str, Any], *, root_kind: TaxKind) -> Iterable[str]:
    roots = tax.get("roots")
    nodes = tax.get("nodes")
    if not isinstance(roots, dict) or not isinstance(nodes, dict):
        return []

    rid = roots.get(root_kind)
    if not isinstance(rid, str) or rid not in nodes:
        return []

    rnode = _node(tax, rid)
    ch = rnode.get("children")
    if not isinstance(ch, list):
        ch = []

    for cid in ch:
        if not isinstance(cid, str) or cid not in nodes:
            continue
        if is_leaf(tax, cid):
            yield cid
            continue
        cnode = _node(tax, cid)
        gch = cnode.get("children")
        if not isinstance(gch, list):
            gch = []
        for sid in gch:
            if not isinstance(sid, str) or sid not in nodes:
                continue
            if is_leaf(tax, sid):
                yield sid


def find_leaf_by_name(tax: dict[str, Any], *, root_kind: TaxKind, name: str) -> str | None:
    target = _norm(name)
    if not target:
        return None

    nodes = tax.get("nodes")
    if not isinstance(nodes, dict):
        return None

    for lid in _iter_leaf_ids(tax, root_kind=root_kind):
        n = nodes.get(lid)
        if not isinstance(n, dict):
            continue
        nm = _norm(str(n.get("name") or ""))
        if nm == target:
            return lid
    return None


def _rule_matches(rule: Rule, tx: TxRecord, tx_kind: str) -> bool:
    if rule.tx_kinds is not None:
        allowed = {str(x) for x in rule.tx_kinds if str(x)}
        if tx_kind not in allowed:
            return False

    if rule.mcc_in is not None:
        allowed_mcc = {int(x) for x in rule.mcc_in}
        if tx.mcc is None or int(tx.mcc) not in allowed_mcc:
            return False

    if rule.merchant_contains is not None:
        if not _match_contains(tx.description, rule.merchant_contains):
            return False

    if rule.recipient_contains is not None:
        if not _match_contains(tx.description, rule.recipient_contains):
            return False

    return True


def categorize_tx(
    *,
    tax: dict[str, Any],
    tx: TxRecord,
    rules: Sequence[Rule],
    override_leaf_id: str | None = None,
    alias_categories: dict[str, list[str]] | None = None,
) -> Categorization:
    from mono_ai_budget_bot.taxonomy.pipeline import categorize_tx as canonical_categorize_tx

    return canonical_categorize_tx(
        tax=tax,
        tx=tx,
        rules=rules,
        override_leaf_id=override_leaf_id,
        alias_categories=alias_categories,
    )
