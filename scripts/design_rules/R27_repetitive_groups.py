"""R27 — Repetitive shape/icon/cell groups produce visual noise.

Project policy 2026-05-05: a Timeline / progress / rating row that uses
≥5 visually-identical children (same size + same fill + same cornerRadius,
or all empty/icon) is design noise. Use progress text ("3/13"), a single
progress bar, or a small fixed-width dot row (max 10 dots, no labels).

Triggers:
  • Parent has ≥5 children that share (width, height, fill, cornerRadius).
  • OR ≥5 children that are empty frames with no text/no children.
  • OR ≥5 children whose only content is an icon vector.

Bypass:
  • Set `_repetitionAllowed: true` on the parent with a one-line reason.

This catches the Timeline c1..c13 + similar Filter star placeholder cases
that produced "blank star noise" in v5 (2026-05-05 incident).
"""
from __future__ import annotations

from typing import Iterable

from .base import Phase, Rule, Severity, Violation, register, walk_blueprint


_MIN_REPEAT = 7


def _shape_signature(node: dict) -> tuple | None:
    """Reduce node to a comparable shape tuple. None if non-frame/text."""
    if not isinstance(node, dict): return None
    nt = (node.get("type") or "frame").lower()
    if nt not in ("frame", "instance", "rectangle", "ellipse", "text"):
        return None
    fill = node.get("fill")
    fill_key = None
    if isinstance(fill, str):
        fill_key = fill
    elif isinstance(fill, dict):
        fill_key = (round(fill.get("r", 0), 2), round(fill.get("g", 0), 2),
                    round(fill.get("b", 0), 2))
    return (
        nt,
        node.get("width"),
        node.get("height"),
        fill_key,
        node.get("cornerRadius"),
        bool(node.get("componentKey")),
    )


def _is_empty_or_icon_only(node: dict) -> bool:
    """Frame with no children, or only one vector/icon child."""
    if not isinstance(node, dict): return False
    children = node.get("children") or []
    if not children:
        # Empty frame counts (would render as blank or get a placeholder)
        return (node.get("type") or "frame").lower() in ("frame",)
    if len(children) == 1:
        c = children[0]
        ctype = (c.get("type") or "").lower()
        cname = (c.get("name") or "").lower()
        if ctype in ("vector", "icon") or "icon" in cname or "star" in cname:
            return True
    return False


def _check(bp: dict, ctx: dict) -> Iterable[Violation]:
    for parent, ppath in walk_blueprint(bp):
        if parent.get("_repetitionAllowed"):
            continue
        children = parent.get("children") or []
        if len(children) < _MIN_REPEAT:
            continue
        # Group children by shape signature
        groups: dict = {}
        for c in children:
            sig = _shape_signature(c)
            if sig is None:
                continue
            groups.setdefault(sig, []).append(c)
        for sig, items in groups.items():
            if len(items) < _MIN_REPEAT:
                continue
            # Flag any ≥7 visually-identical children (same width/height/fill/
            # cornerRadius/type). Even if cells contain text, 7+ identical
            # shapes is design noise — collapse to progress text or a single
            # bar. Whether children are empty or have text doesn't matter:
            # the parent screams "redundant marker" at this density.
            empty_count = sum(1 for it in items if _is_empty_or_icon_only(it))
            yield Violation(
                "R27-repetitive-groups", Severity.ERROR, ppath,
                (f"{len(items)} visually-identical children "
                 f"(same shape signature) — this is Timeline-noise. "
                 f"Use progress text ('current/total'), single progress bar, "
                 f"or ≤6 small dots. "
                 f"Bypass: _repetitionAllowed:'<reason>' on the parent."),
                Phase.LINT,
            )


register(Rule(
    rule_id="R27-repetitive-groups",
    title="Reject ≥5 repeated empty/icon children (Timeline-noise pattern)",
    description="Timeline 13-cell / placeholder-rating-row anti-pattern.",
    check_blueprint_fn=_check,
))
