"""R50 — Generative archetype injection.

Walks blueprint, for any node whose name matches an ARCHETYPE pattern AND
has empty/minimal children, replaces the node with the archetype template
expanded from archetypeData.

This runs in the inject phase BEFORE R23 ds-first so child icon names
inside the expanded template (e.g. "Chevron Right Icon") are caught by
R23 and swapped to DS instances.
"""
from __future__ import annotations

from typing import Optional

from .base import Phase, Rule, register
from .archetype_catalog import resolve_archetype


def _is_minimal(node: dict) -> bool:
    """A node is 'minimal' (placeholder) if it has no children OR only
    a single rectangle/frame placeholder. Such nodes are candidates for
    archetype expansion."""
    children = node.get("children") or []
    if not children:
        return True
    if len(children) == 1:
        c = children[0]
        if c.get("type") in ("rectangle", "RECTANGLE") and not c.get("children"):
            return True
    return False


def _walk_inject(node: dict, parent: Optional[dict] = None,
                 idx: Optional[int] = None) -> int:
    """Recursively expand archetype nodes. Returns count of expansions."""
    n = 0
    if not isinstance(node, dict):
        return 0
    template_fn = resolve_archetype(node)
    if template_fn and _is_minimal(node):
        expanded = template_fn(node)
        # Preserve any explicit overrides from the blueprint
        for k in ("archetype", "archetypeData", "discoverySource"):
            if k in node:
                expanded[k] = node[k]
        # In-place replace: copy expanded back into node
        for k in list(node.keys()):
            if k not in ("name",):  # keep name
                del node[k]
        for k, v in expanded.items():
            node[k] = v
        n += 1
    # Recurse into (possibly newly-expanded) children
    for i, c in enumerate(node.get("children") or []):
        n += _walk_inject(c, node, i)
    return n


def _inject(bp: dict) -> dict:
    n = _walk_inject(bp)
    if n:
        print(f"[inject R05] expanded {n} archetype node(s) → polished content")
    return bp


register(Rule(
    rule_id="R05-archetype-inject",
    title="Generative archetype expansion",
    description=(
        "Empty 'Stage Card', 'Product', 'Stat Card', 'List Item', 'Hero Banner' "
        "frames get auto-expanded into polished content templates "
        "(tag/amount/period/progress, image/name/price, etc.) from "
        "archetype_catalog. archetypeData lets author override defaults."
    ),
    inject_blueprint_fn=_inject,
))
