from __future__ import annotations

from typing import Any, Sequence

from mono_ai_budget_bot.analytics.categories import category_from_mcc
from mono_ai_budget_bot.analytics.classify import classify_kind
from mono_ai_budget_bot.storage.tx_store import TxRecord
from mono_ai_budget_bot.taxonomy.models import _node, ensure_leaf_target
from mono_ai_budget_bot.taxonomy.rules import (
    Categorization,
    Rule,
    _match_contains,
    _rule_matches,
    find_leaf_by_name,
)

CATEGORIZATION_PRIORITY: tuple[str, ...] = (
    "override",
    "rules",
    "aliases",
    "transfer_turnover",
    "mcc_fallback",
    "needs_clarify",
)


def _normalize_alias_categories(
    tax: dict[str, Any],
    alias_categories: dict[str, list[str]] | None,
) -> dict[str, list[str]]:
    nodes = tax.get("nodes")
    if not isinstance(nodes, dict):
        return {}

    raw = alias_categories
    if raw is None:
        raw = tax.get("alias_terms")

    if not isinstance(raw, dict):
        return {}

    out: dict[str, list[str]] = {}
    for raw_key, raw_terms in raw.items():
        if not isinstance(raw_key, str):
            continue
        if not isinstance(raw_terms, list):
            continue

        terms = [str(x).strip() for x in raw_terms if isinstance(x, str) and str(x).strip()]
        if not terms:
            continue

        leaf_id: str | None = None
        if raw_key in nodes:
            try:
                ensure_leaf_target(tax, node_id=raw_key)
                leaf_id = raw_key
            except Exception:
                leaf_id = None
        else:
            leaf_id = find_leaf_by_name(tax, root_kind="expense", name=raw_key)

        if not leaf_id:
            continue

        bucket = out.setdefault(leaf_id, [])
        for term in terms:
            if term not in bucket:
                bucket.append(term)

    return out


def _categorize_override(
    *,
    tax: dict[str, Any],
    override_leaf_id: str | None,
) -> Categorization | None:
    if not override_leaf_id:
        return None

    ensure_leaf_target(tax, node_id=override_leaf_id)
    n = _node(tax, override_leaf_id)
    kind = str(n.get("kind"))
    if kind == "income":
        return Categorization(bucket="real_income", leaf_id=override_leaf_id, reason="override")
    return Categorization(bucket="real_expense", leaf_id=override_leaf_id, reason="override")


def _categorize_rules(
    *,
    tax: dict[str, Any],
    tx: TxRecord,
    rules: Sequence[Rule],
    tx_kind: str,
) -> Categorization | None:
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
    return None


def _categorize_aliases(
    *,
    tax: dict[str, Any],
    tx: TxRecord,
    alias_categories: dict[str, list[str]] | None,
) -> Categorization | None:
    aliases = _normalize_alias_categories(tax, alias_categories)
    if not aliases:
        return None

    for leaf_id, terms in aliases.items():
        for term in terms:
            if _match_contains(tx.description, term):
                ensure_leaf_target(tax, node_id=leaf_id)
                return Categorization(bucket="real_expense", leaf_id=leaf_id, reason="alias")
    return None


def _categorize_transfer_or_fallback(
    *,
    tax: dict[str, Any],
    tx: TxRecord,
    tx_kind: str,
) -> Categorization:
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


def categorize_tx(
    *,
    tax: dict[str, Any],
    tx: TxRecord,
    rules: Sequence[Rule],
    override_leaf_id: str | None = None,
    alias_categories: dict[str, list[str]] | None = None,
) -> Categorization:
    tx_kind = classify_kind(tx.amount, tx.mcc, tx.description)

    out = _categorize_override(tax=tax, override_leaf_id=override_leaf_id)
    if out is not None:
        return out

    out = _categorize_rules(tax=tax, tx=tx, rules=rules, tx_kind=tx_kind)
    if out is not None:
        return out

    out = _categorize_aliases(tax=tax, tx=tx, alias_categories=alias_categories)
    if out is not None:
        return out

    return _categorize_transfer_or_fallback(tax=tax, tx=tx, tx_kind=tx_kind)
