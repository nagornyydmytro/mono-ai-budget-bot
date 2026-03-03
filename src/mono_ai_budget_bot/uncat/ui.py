from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mono_ai_budget_bot.taxonomy.models import is_leaf


@dataclass(frozen=True)
class LeafOption:
    leaf_id: str
    name: str


def list_leaf_options(tax: dict[str, Any], *, root_kind: str) -> list[LeafOption]:
    roots = tax.get("roots")
    nodes = tax.get("nodes")
    if not isinstance(roots, dict) or not isinstance(nodes, dict):
        return []

    rid = roots.get(root_kind)
    if not isinstance(rid, str) or rid not in nodes:
        return []

    rnode = nodes.get(rid)
    if not isinstance(rnode, dict):
        return []

    ch = rnode.get("children")
    if not isinstance(ch, list):
        ch = []

    out: list[LeafOption] = []
    for cid in ch:
        if not isinstance(cid, str) or cid not in nodes:
            continue

        if is_leaf(tax, cid):
            n = nodes.get(cid)
            name = str(n.get("name") or "") if isinstance(n, dict) else ""
            out.append(LeafOption(leaf_id=cid, name=name))
            continue

        cnode = nodes.get(cid)
        gch = cnode.get("children") if isinstance(cnode, dict) else []
        if not isinstance(gch, list):
            gch = []
        for sid in gch:
            if not isinstance(sid, str) or sid not in nodes:
                continue
            if not is_leaf(tax, sid):
                continue
            sn = nodes.get(sid)
            name = str(sn.get("name") or "") if isinstance(sn, dict) else ""
            out.append(LeafOption(leaf_id=sid, name=name))

    out = [x for x in out if x.leaf_id and x.name]
    out.sort(key=lambda x: x.name.lower())
    return out
