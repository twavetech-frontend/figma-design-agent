"""R20 — Semantic tokens only (no primitive scales, no state variants).

Mirror of L1 schema check but at the semantic level: also flags hex strings
embedded in nested objects like fills:[{color:'#xxxxxx'}].
"""
from __future__ import annotations

import re
from typing import Iterable

from .base import Phase, Rule, Severity, Violation, register, walk_blueprint


_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{3,8}$")


def _scan(obj, path: str, depth: int = 0):
    """Recursively yield (path, hex_str) for any hex string anywhere in obj."""
    if depth > 10: return
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _scan(v, f"{path}.{k}", depth + 1)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _scan(v, f"{path}[{i}]", depth + 1)
    elif isinstance(obj, str):
        if _HEX_RE.match(obj):
            yield path, obj


def _check(bp: dict, ctx: dict) -> Iterable[Violation]:
    for node, path in walk_blueprint(bp):
        # Skip the children list (children are scanned recursively by walk_blueprint)
        scan_target = {k: v for k, v in node.items() if k != "children"}
        for p, hexv in _scan(scan_target, path):
            yield Violation(
                "R20-semantic-only", Severity.ERROR, p,
                f"raw hex '{hexv}' — only semantic $token() allowed",
                Phase.LINT,
            )


register(Rule(
    rule_id="R20-semantic-only",
    title="Semantic tokens only",
    description="No primitive scales, no state variants, no raw hex anywhere.",
    check_blueprint_fn=_check,
))
