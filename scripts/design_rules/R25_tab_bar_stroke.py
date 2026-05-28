"""R25 — Tab Bar / card stroke must be individual sides, never 4-sided.

`weight: 1` on a stroked frame paints all four sides. Tab Bar wants only
top divider; cards typically only top or bottom. Accept either:
  weight: 0 + at least one of strokeTopWeight/Bottom/Left/RightWeight set
  no stroke at all (use a separate Rectangle as divider)
"""
from __future__ import annotations

from typing import Iterable

from .base import Phase, Rule, Severity, Violation, register, walk_blueprint


def _check(bp: dict, ctx: dict) -> Iterable[Violation]:
    for node, path in walk_blueprint(bp):
        name = node.get("name", "") or ""
        if "Tab Bar" not in name and "Tab Row" not in name:
            continue
        sw = node.get("strokeWeight", 0)
        per_side = any(node.get(k) for k in
                       ("strokeTopWeight", "strokeBottomWeight",
                        "strokeLeftWeight", "strokeRightWeight"))
        has_stroke_color = bool(node.get("stroke") or node.get("strokeColor")
                                or node.get("strokes"))
        if has_stroke_color and sw and not per_side:
            yield Violation(
                "R25-tab-bar-stroke", Severity.ERROR, path,
                f"'{name}' has 4-sided stroke (weight={sw}) — set per-side weights "
                f"or weight=0 + strokeTopWeight",
                Phase.LINT,
            )


register(Rule(
    rule_id="R25-tab-bar-stroke",
    title="Tab Bar stroke individual sides",
    description="Tab Bar / Tab Row must use per-side stroke, never 4-sided weight.",
    check_blueprint_fn=_check,
))
