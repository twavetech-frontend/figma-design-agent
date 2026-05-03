"""R12 — imageGen field constraints (small icons need style='2d')."""
from __future__ import annotations

from typing import Iterable

from .base import Phase, Rule, Severity, Violation, register, walk_blueprint


def _check(bp: dict, ctx: dict) -> Iterable[Violation]:
    for node, path in walk_blueprint(bp):
        ig = node.get("imageGen")
        if not isinstance(ig, dict):
            continue
        if ig.get("isHero", False):
            continue
        w = ig.get("width", 120)
        h = ig.get("height", 120)
        if max(w, h) > 32:
            continue
        style = (ig.get("style") or "").lower()
        if style not in ("2d", "tossface"):
            yield Violation(
                "R12.1-icon-2d", Severity.WARN, path,
                f"icon imageGen {w}x{h} missing style='2d' (auto-corrected, explicit preferred)",
                Phase.LINT, auto_fixable=True,
            )


register(Rule(
    rule_id="R12-image-gen",
    title="Image generation hints",
    description="Small icons (<=32px) require style='2d' or 'tossface'.",
    check_blueprint_fn=_check,
))
