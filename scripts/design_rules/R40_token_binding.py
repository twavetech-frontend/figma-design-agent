"""R40 — Verify all SOLID fills are bound to a variable (semantic token).

After build + token-bind sweep, every SOLID fill on a non-image frame
should have boundVariables.color set. Unbound fills are usually one of:
  - Hard-coded RGBA from blueprint (resolver missed it)
  - Non-semantic primitive that was filtered out

Reports unbound fills so the binder can be debugged.
"""
from __future__ import annotations

from typing import Iterable

from .base import Phase, Rule, Severity, Violation, register, walk_tree


def _verify(tree: dict, ctx: dict) -> Iterable[Violation]:
    unbound = 0
    examples = []
    for node, path in walk_tree(tree):
        ntype = node.get("type")
        # Only frames + text — skip vector/image
        if ntype not in ("FRAME", "INSTANCE", "TEXT", "RECTANGLE"):
            continue
        for i, fill in enumerate(node.get("fills") or []):
            if not isinstance(fill, dict): continue
            if fill.get("type") != "SOLID": continue
            bv = fill.get("boundVariables") or {}
            if isinstance(bv, dict) and bv.get("color"):
                continue
            unbound += 1
            if len(examples) < 5:
                examples.append(f"{path}.fills[{i}]")
    if unbound:
        yield Violation(
            "R40-token-binding", Severity.WARN, "(tree)",
            f"{unbound} SOLID fills unbound to variables — examples: {examples}",
            Phase.VERIFY,
        )


register(Rule(
    rule_id="R40-token-binding",
    title="All SOLID fills bound to variables",
    description="Verify token binding completeness after build + bind sweep.",
    check_built_fn=_verify,
))
