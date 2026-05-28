"""R46 — NavBar back icon must be chevron-left, not arrow-left.

Detail-screen back navigation is canonically `<` (chevron-left) on iOS/Material.
`←` (arrow-left) reads like a media/forward control and feels wrong as a back
action. Sourced from 2026-05-26 user feedback.

Strategy: walk the blueprint and rewrite any icon node whose name matches a
nav-back pattern (e.g. "nav-back", "back btn", "header-back") **or** any icon
whose iconName is "arrow-left" and sits inside a NavBar ancestor → set
`iconName: "chevron-left"`. Idempotent.
"""
from __future__ import annotations

from typing import Optional

from .base import Rule, register

_BACK_NAME_PATTERNS = (
    "nav-back", "nav back", "navback",
    "back btn", "back-btn", "back-button", "back button",
    "header-back", "header back",
    "topbar-back", "topbar back",
)

_NAVBAR_NAME_PATTERNS = ("navbar", "nav bar", "top bar", "topbar", "header")


def _is_navbar_like(node: dict) -> bool:
    if not isinstance(node, dict):
        return False
    name = (node.get("name") or "").lower()
    return any(p in name for p in _NAVBAR_NAME_PATTERNS)


def _is_back_named(node: dict) -> bool:
    name = (node.get("name") or "").lower().strip()
    return any(p in name for p in _BACK_NAME_PATTERNS)


def _rewrite_icon(node: dict, reason: str, counts: dict) -> None:
    if not isinstance(node, dict):
        return
    if (node.get("type") or "").lower() != "icon":
        return
    current = (node.get("iconName") or "").lower()
    if current == "chevron-left":
        return  # already correct
    # Rewrite anything that's the wrong glyph for a back chevron:
    # arrow-left, arrow-narrow-left, chevron-left-double, none, or empty.
    if current in ("arrow-left", "arrow-narrow-left", "arrow-circle-left",
                   "chevron-left-double", "", None):
        node["iconName"] = "chevron-left"
        counts["fixed"] += 1
        counts["reasons"].setdefault(reason, 0)
        counts["reasons"][reason] += 1


def _walk(node: dict, navbar_depth: int, counts: dict) -> None:
    if not isinstance(node, dict):
        return
    in_navbar = navbar_depth > 0 or _is_navbar_like(node)
    next_depth = navbar_depth + (1 if _is_navbar_like(node) else 0)

    # Rule 1 — name match wins regardless of ancestor (e.g., "nav-back" anywhere).
    if _is_back_named(node):
        _rewrite_icon(node, "name-match", counts)

    # Rule 2 — inside a NavBar-like ancestor, any arrow-left icon → chevron-left.
    if in_navbar:
        _rewrite_icon(node, "navbar-ancestor", counts)

    for c in node.get("children") or []:
        _walk(c, next_depth, counts)


def _inject(bp: dict) -> dict:
    counts = {"fixed": 0, "reasons": {}}
    _walk(bp, 0, counts)
    if counts["fixed"]:
        parts = ", ".join(f"{k}×{v}" for k, v in counts["reasons"].items())
        print(f"[inject R46] nav-back arrow → chevron — {counts['fixed']}건 ({parts})")
    return bp


register(Rule(
    rule_id="R46-nav-back-chevron",
    title="NavBar back icon must be chevron-left",
    description=(
        "Detail screen back buttons use chevron-left (`<`), not arrow-left (`←`). "
        "Auto-rewrites iconName on (a) any icon node whose name matches a back pattern, "
        "or (b) any arrow-left icon nested inside a NavBar-like ancestor. "
        "2026-05-26 user directive — codified to prevent regression across sessions."
    ),
    inject_blueprint_fn=_inject,
))
