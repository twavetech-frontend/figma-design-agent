"""R10 — Layout/sizing checks (legacy R1, R2, R3, R4, R5)."""
from __future__ import annotations

import re
from typing import Iterable

from .base import Phase, Rule, Severity, Violation, register, walk_blueprint


_SKIP_KEYWORDS = ("Tag", "Chip", "Badge", "Dot", "Icon", "Indicator",
                  "Nav Right", "DI1 Left", "DI2 Left", "DI3 Left")
_SKIP_RE = re.compile(r'\b(?:' + '|'.join(re.escape(k.lower()) for k in _SKIP_KEYWORDS) + r')\b')


def _frame_fill_check(bp: dict, ctx: dict) -> Iterable[Violation]:
    """R10.1 — FRAME children of root/sections must be FILL (not HUG)."""
    for node, path in walk_blueprint(bp):
        if path == "root":
            continue
        ntype = node.get("type", "frame")
        if ntype not in ("frame", "FRAME"):
            continue
        sizing_h = node.get("layoutSizingHorizontal", "")
        if sizing_h not in ("HUG", ""):
            continue
        # Filter out small intrinsic-width elements
        w = node.get("width", 999)
        name = node.get("name", "?")
        if w <= 60: continue
        if _SKIP_RE.search(name.lower()): continue
        if path.count("/") > 3: continue
        yield Violation(
            "R10.1-frame-fill", Severity.WARN, path,
            f"FRAME '{name}' layoutSizingHorizontal='{sizing_h or 'unset'}' — should be FILL",
            Phase.LINT,
        )


def _absolute_positioning_check(bp: dict, ctx: dict) -> Iterable[Violation]:
    """R10.2 — Tab Bar / FAB note about ABSOLUTE positioning (informational)."""
    for node, path in walk_blueprint(bp):
        name = node.get("name", "")
        if "Tab Bar" not in name and "FAB" not in name:
            continue
        if node.get("layoutPositioning", "") != "ABSOLUTE":
            yield Violation(
                "R10.2-absolute", Severity.INFO, path,
                f"'{name}' will be set to ABSOLUTE in post-fix (auto-handled)",
                Phase.LINT, auto_fixable=True,
            )


def _carousel_horizontal_check(bp: dict, ctx: dict) -> Iterable[Violation]:
    """R10.3 — Hero/Banner section with multiple banners must be HORIZONTAL + clipsContent."""
    for node, path in walk_blueprint(bp):
        name = node.get("name", "")
        if not any(kw in name for kw in ("Banner", "Hero", "Carousel")):
            continue
        children = node.get("children", []) or []
        banners = [c for c in children
                   if "Banner" in c.get("name", "")
                   and c.get("type", "frame") in ("frame", "FRAME")]
        if len(banners) < 2:
            continue
        al = node.get("autoLayout", {}) or {}
        mode = al.get("layoutMode", "") or al.get("direction", "")
        if mode != "HORIZONTAL":
            yield Violation(
                "R10.3-carousel-horizontal", Severity.WARN, path,
                f"Carousel '{name}' has {len(banners)} banners but layoutMode='{mode}' — should be HORIZONTAL",
                Phase.LINT,
            )
        if not node.get("clipsContent", False):
            yield Violation(
                "R10.3-carousel-clip", Severity.WARN, path,
                f"Carousel '{name}' needs clipsContent=true",
                Phase.LINT,
            )


def _fab_pill_check(bp: dict, ctx: dict) -> Iterable[Violation]:
    """R10.4 — FAB with text should be pill-shaped (width >= 100)."""
    for node, path in walk_blueprint(bp):
        if "FAB" not in node.get("name", ""):
            continue
        children = node.get("children", []) or []
        has_text = any(c.get("type") in ("text", "TEXT") for c in children)
        if has_text and node.get("width", 0) < 100:
            yield Violation(
                "R10.4-fab-pill", Severity.WARN, path,
                f"FAB has text but width={node.get('width', 0)} — pill (width>=100)",
                Phase.LINT,
            )


def _cta_padding_check(bp: dict, ctx: dict) -> Iterable[Violation]:
    """R10.5 — CTA/Button frames with text need vertical padding (HUG height bug)."""
    for node, path in walk_blueprint(bp):
        ntype = node.get("type", "frame")
        if ntype not in ("frame", "FRAME"): continue
        al = node.get("autoLayout") or {}
        if not al: continue
        name = node.get("name", "")
        if not any(kw.lower() in name.lower() for kw in ("CTA Button", "CTA", "Button")):
            continue
        children = node.get("children", []) or []
        has_text = any(c.get("type") in ("text", "TEXT") for c in children)
        if has_text and al.get("paddingTop", 0) == 0 and al.get("paddingBottom", 0) == 0:
            yield Violation(
                "R10.5-cta-padding", Severity.WARN, path,
                f"CTA/Button '{name}' has no vertical padding — add paddingTop/Bottom (e.g. 16)",
                Phase.LINT,
            )


def _all_layout_checks(bp: dict, ctx: dict) -> Iterable[Violation]:
    yield from _frame_fill_check(bp, ctx)
    yield from _absolute_positioning_check(bp, ctx)
    yield from _carousel_horizontal_check(bp, ctx)
    yield from _fab_pill_check(bp, ctx)
    yield from _cta_padding_check(bp, ctx)


register(Rule(
    rule_id="R10-layout",
    title="Layout/sizing rules",
    description="FRAME FILL, Tab Bar/FAB ABSOLUTE, Carousel HORIZONTAL, FAB pill, CTA padding.",
    check_blueprint_fn=_all_layout_checks,
))
