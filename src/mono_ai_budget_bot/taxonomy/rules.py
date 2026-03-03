from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal, Optional, Sequence

from mono_ai_budget_bot.analytics.categories import category_from_mcc
from mono_ai_budget_bot.analytics.classify import classify_kind
from mono_ai_budget_bot.storage.tx_store import TxRecord
from mono_ai_budget_bot.taxonomy.models import TaxKind, _node, ensure_leaf_target, is_leaf

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
) -> Categorization:
    tx_kind = classify_kind(tx.amount, tx.mcc, tx.description)

    for r in rules:
        if _rule_matches(r, tx, tx_kind):
            ensure_leaf_target(tax, node_id=r.leaf_id)
            n = _node(tax, r.leaf_id)
            kind = str(n.get("kind"))
            if kind == "income":
                return Categorization(
                    bucket="real_income", leaf_id=r.leaf_id, reason=f"rule:{r.id}"
                )
            return Categorization(bucket="real_expense", leaf_id=r.leaf_id, reason=f"rule:{r.id}")

    if tx_kind in {"transfer_out", "transfer_in"}:
        return Categorization(bucket="turnover", leaf_id=None, reason="transfer_without_rule")

    if tx_kind == "spend":
        if tx.mcc is not None:
            mcc_name = category_from_mcc(int(tx.mcc))
            if mcc_name:
                lid = find_leaf_by_name(tax, root_kind="expense", name=mcc_name)
                if lid:
                    ensure_leaf_target(tax, node_id=lid)
                    return Categorization(bucket="real_expense", leaf_id=lid, reason="mcc_fallback")

        return Categorization(bucket="needs_clarify", leaf_id=None, reason="purchase_without_rule")

    return Categorization(bucket="needs_clarify", leaf_id=None, reason="income_without_rule")
