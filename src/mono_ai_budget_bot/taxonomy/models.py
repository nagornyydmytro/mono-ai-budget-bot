from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Literal, Optional

TaxKind = Literal["income", "expense"]


@dataclass(frozen=True)
class TaxNode:
    id: str
    name: str
    parent_id: Optional[str]
    kind: TaxKind
    children: tuple[str, ...]


def _norm_name(name: str) -> str:
    s = (name or "").strip()
    s = " ".join(s.split())
    return s


def _make_id(parent_id: str, name: str) -> str:
    base = f"{parent_id}:{name.lower()}"
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()
    return h[:12]


def new_taxonomy() -> dict[str, Any]:
    nodes: dict[str, Any] = {}

    def _add_root(kind: TaxKind) -> str:
        rid = kind
        nodes[rid] = {
            "id": rid,
            "name": "Доходи" if kind == "income" else "Витрати",
            "parent_id": None,
            "kind": kind,
            "children": [],
            "is_root": True,
        }
        return rid

    income_root = _add_root("income")
    expense_root = _add_root("expense")

    tax = {
        "version": 1,
        "roots": {"income": income_root, "expense": expense_root},
        "nodes": nodes,
    }
    validate_taxonomy(tax)
    return tax


def _node(tax: dict[str, Any], node_id: str) -> dict[str, Any]:
    nodes = tax.get("nodes")
    if not isinstance(nodes, dict):
        raise ValueError("taxonomy.nodes is missing")
    n = nodes.get(node_id)
    if not isinstance(n, dict):
        raise KeyError(node_id)
    return n


def depth_of(tax: dict[str, Any], node_id: str) -> int:
    n = _node(tax, node_id)
    d = 0
    while n.get("parent_id") is not None:
        pid = n.get("parent_id")
        if not isinstance(pid, str) or not pid:
            raise ValueError("invalid parent_id")
        n = _node(tax, pid)
        d += 1
        if d > 10:
            raise ValueError("cycle detected")
    return d


def is_leaf(tax: dict[str, Any], node_id: str) -> bool:
    n = _node(tax, node_id)
    if bool(n.get("is_root")):
        return False
    ch = n.get("children")
    if not isinstance(ch, list):
        return True
    return len(ch) == 0


def add_category(tax: dict[str, Any], *, root_kind: TaxKind, name: str) -> str:
    roots = tax.get("roots")
    if not isinstance(roots, dict):
        raise ValueError("taxonomy.roots is missing")
    root_id = roots.get(root_kind)
    if not isinstance(root_id, str) or not root_id:
        raise ValueError("invalid root_kind")

    nm = _norm_name(name)
    if not nm or len(nm) > 60:
        raise ValueError("invalid category name")

    rid = str(root_id)
    cid = _make_id(rid, nm)

    nodes = tax.get("nodes")
    if not isinstance(nodes, dict):
        raise ValueError("taxonomy.nodes is missing")

    if cid in nodes:
        return cid

    nodes[cid] = {
        "id": cid,
        "name": nm,
        "parent_id": rid,
        "kind": root_kind,
        "children": [],
        "is_root": False,
    }

    rnode = _node(tax, rid)
    rch = rnode.get("children")
    if not isinstance(rch, list):
        rch = []
    if cid not in rch:
        rch.append(cid)
    rnode["children"] = rch

    validate_taxonomy(tax)
    return cid


def add_subcategory(tax: dict[str, Any], *, parent_id: str, name: str) -> str:
    pid = (parent_id or "").strip()
    if not pid:
        raise ValueError("missing parent_id")

    p = _node(tax, pid)
    if bool(p.get("is_root")):
        parent_depth = 0
    else:
        parent_depth = depth_of(tax, pid)

    if parent_depth != 1:
        raise ValueError("subcategories allowed only under level-1 categories")

    nm = _norm_name(name)
    if not nm or len(nm) > 60:
        raise ValueError("invalid subcategory name")

    kind = p.get("kind")
    if kind not in ("income", "expense"):
        raise ValueError("invalid parent kind")

    sid = _make_id(pid, nm)

    nodes = tax.get("nodes")
    if not isinstance(nodes, dict):
        raise ValueError("taxonomy.nodes is missing")

    if sid in nodes:
        return sid

    nodes[sid] = {
        "id": sid,
        "name": nm,
        "parent_id": pid,
        "kind": kind,
        "children": [],
        "is_root": False,
    }

    ch = p.get("children")
    if not isinstance(ch, list):
        ch = []
    if sid not in ch:
        ch.append(sid)
    p["children"] = ch

    validate_taxonomy(tax)
    return sid


def add_subcategory_with_migration(
    tax: dict[str, Any], *, parent_id: str, name: str
) -> tuple[str, bool]:
    pid = (parent_id or "").strip()
    if not pid:
        raise ValueError("missing parent_id")

    was_leaf = is_leaf(tax, pid)
    sid = add_subcategory(tax, parent_id=pid, name=name)
    return sid, bool(was_leaf)


def validate_taxonomy(tax: dict[str, Any]) -> None:
    if not isinstance(tax, dict):
        raise ValueError("taxonomy must be dict")

    if tax.get("version") != 1:
        raise ValueError("unsupported taxonomy version")

    roots = tax.get("roots")
    nodes = tax.get("nodes")
    if not isinstance(roots, dict) or not isinstance(nodes, dict):
        raise ValueError("taxonomy.roots/nodes missing")

    for rk in ("income", "expense"):
        rid = roots.get(rk)
        if not isinstance(rid, str) or not rid:
            raise ValueError("missing root id")
        r = nodes.get(rid)
        if not isinstance(r, dict):
            raise ValueError("root node missing")
        if r.get("parent_id") is not None:
            raise ValueError("root must have parent_id=None")
        if r.get("kind") != rk:
            raise ValueError("root kind mismatch")
        if not bool(r.get("is_root")):
            raise ValueError("root must have is_root=True")

    for nid, n in nodes.items():
        if not isinstance(nid, str) or not isinstance(n, dict):
            raise ValueError("invalid node map")
        if n.get("id") != nid:
            raise ValueError("node.id mismatch")
        name = n.get("name")
        if not isinstance(name, str) or not _norm_name(name):
            raise ValueError("invalid node name")
        kind = n.get("kind")
        if kind not in ("income", "expense"):
            raise ValueError("invalid node kind")
        pid = n.get("parent_id")
        is_root = bool(n.get("is_root"))
        if is_root:
            if pid is not None:
                raise ValueError("root parent_id must be None")
        else:
            if not isinstance(pid, str) or not pid:
                raise ValueError("non-root must have parent_id")
            if pid not in nodes:
                raise ValueError("parent does not exist")
            if depth_of(tax, nid) > 2:
                raise ValueError("max depth is 2")

        ch = n.get("children")
        if ch is None:
            n["children"] = []
            ch = n["children"]
        if not isinstance(ch, list):
            raise ValueError("children must be list")
        for cid in ch:
            if not isinstance(cid, str) or cid not in nodes:
                raise ValueError("invalid child id")
            c = nodes[cid]
            if c.get("parent_id") != nid:
                raise ValueError("child parent mismatch")
            if c.get("kind") != kind:
                raise ValueError("child kind mismatch")


def leaf_ids(tax: dict[str, Any], *, root_kind: TaxKind) -> list[str]:
    roots = tax.get("roots")
    if not isinstance(roots, dict):
        raise ValueError("taxonomy.roots is missing")
    rid = roots.get(root_kind)
    if not isinstance(rid, str) or not rid:
        raise ValueError("invalid root_kind")

    nodes = tax.get("nodes")
    if not isinstance(nodes, dict):
        raise ValueError("taxonomy.nodes is missing")

    out: list[str] = []

    rnode = _node(tax, rid)
    ch = rnode.get("children")
    if not isinstance(ch, list):
        ch = []

    for cid in ch:
        if not isinstance(cid, str):
            continue
        if is_leaf(tax, cid):
            out.append(cid)
            continue
        cnode = _node(tax, cid)
        gch = cnode.get("children")
        if not isinstance(gch, list):
            gch = []
        for sid in gch:
            if not isinstance(sid, str):
                continue
            if is_leaf(tax, sid):
                out.append(sid)

    return out


def ensure_leaf_target(tax: dict[str, Any], *, node_id: str) -> None:
    nid = (node_id or "").strip()
    if not nid:
        raise ValueError("missing node_id")
    if nid in ("income", "expense"):
        raise ValueError("root cannot hold transactions")
    if not is_leaf(tax, nid):
        raise ValueError("transactions must be assigned to leaf categories only")
