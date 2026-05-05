"""R28 — Horizontal-scroll carousel must left-align with section title.

Project policy 2026-05-05: when a VERTICAL section contains
  - a TEXT/title sibling, AND
  - a HORIZONTAL carousel sibling (auto-layout HORIZONTAL with clipsContent),

the carousel's first card MUST start at the same absolute x as the title.

Mechanism:
  • Section itself has paddingLeft=0 (so carousel can clip-from-edge).
  • Title sibling carries its own paddingLeft (e.g. 20).
  • Carousel carries the same paddingLeft.

When a build/blueprint sets paddingLeft on the SECTION instead of on the
title sibling, the title gets indented by section padding AND the carousel
adds another paddingLeft → carousel's first card ends up indented twice.

This rule auto-corrects in post-fix: detect carousels (HORIZONTAL +
clipsContent), measure the title sibling's effective left edge, and align
the carousel's first child x to match by setting paddingLeft on the
carousel to (title_x - carousel_x).

Verify phase: assert |carousel_first_card.x - title.x| ≤ 1px.
"""
from __future__ import annotations

from typing import Iterable

from .base import Phase, Rule, Severity, Violation, register, walk_tree


def _is_horizontal_carousel(node: dict) -> bool:
    if not isinstance(node, dict): return False
    if (node.get("layoutMode") or "") != "HORIZONTAL":
        return False
    # Either explicitly clipsContent OR has overflow children (width sum > parent width)
    if node.get("clipsContent") is True:
        return True
    # Heuristic: total children width > own width → scrolling
    kids = node.get("_children_full") or node.get("children") or []
    if not kids:
        return False
    own_w = node.get("width") or 0
    total = 0
    fixed_count = 0
    for c in kids:
        if isinstance(c, dict) and c.get("width"):
            total += c.get("width") or 0
            if c.get("layoutSizingHorizontal") in ("FIXED", None, ""):
                fixed_count += 1
    return total > own_w + 8 and fixed_count >= 2


def _find_title_sibling(parent: dict, carousel_idx: int) -> dict | None:
    """Find the nearest TEXT sibling (preceding) acting as section title."""
    kids = parent.get("_children_full") or parent.get("children") or []
    for i in range(carousel_idx - 1, -1, -1):
        sib = kids[i]
        if not isinstance(sib, dict):
            continue
        ntype = (sib.get("type") or "").upper()
        if ntype == "TEXT":
            return sib
        # Wrapper frame containing text — peek inside
        inner_kids = sib.get("_children_full") or sib.get("children") or []
        if any(isinstance(c, dict) and (c.get("type") or "").upper() == "TEXT"
               for c in inner_kids):
            return sib
    return None


def _title_content_x(title: dict) -> float | None:
    """Return the absolute x where the title's CONTENT begins — i.e. the
    inner edge after the wrapper's paddingLeft. Carousel's first card should
    align with this x.

    Why: R28's earlier logic used the title wrapper's outer x and computed
    `new_pad = title_x - car_x = 0 - 0 = 0`, zeroing the carousel's
    paddingLeft. Using `wrapper_x + paddingLeft` gives the correct target.
    """
    bb = title.get("absoluteBoundingBox") if isinstance(title.get("absoluteBoundingBox"), dict) else None
    wrapper_x = float(bb["x"]) if isinstance(bb, dict) and "x" in bb else float(title.get("x") or 0)
    pad_l = float(title.get("paddingLeft") or 0)
    return wrapper_x + pad_l


def _verify(tree: dict, ctx: dict) -> Iterable[Violation]:
    """Post-build assert that carousels align with their title sibling."""
    for node, path in walk_tree(tree):
        kids = node.get("_children_full") or node.get("children") or []
        if (node.get("layoutMode") or "") != "VERTICAL":
            continue
        for i, child in enumerate(kids):
            if not isinstance(child, dict): continue
            if not _is_horizontal_carousel(child):
                continue
            title = _find_title_sibling(node, i)
            if not title:
                continue
            # Use title's CONTENT x (first TEXT inside) — accounts for the
            # title wrapper's own paddingLeft.
            title_x = _title_content_x(title)
            carousel_kids = child.get("_children_full") or child.get("children") or []
            first = carousel_kids[0] if carousel_kids else None
            if not first or not isinstance(first, dict):
                continue
            first_x = first.get("absoluteBoundingBox", {}).get("x") if isinstance(first.get("absoluteBoundingBox"), dict) else first.get("x")
            if title_x is None or first_x is None:
                continue
            if abs(float(title_x) - float(first_x)) > 1.5:
                yield Violation(
                    "R28-carousel-align", Severity.WARN, f"{path}/{child.get('name')}",
                    (f"carousel first card x={first_x:.0f} doesn't match "
                     f"title '{title.get('name')}' content x={title_x:.0f}. "
                     f"Set paddingLeft on the carousel to match the title's "
                     f"content left edge."),
                    Phase.VERIFY,
                )


def _autofix(tree: dict, ctx: dict) -> int:
    """Post-fix: align carousel first child to title sibling x by adjusting
    carousel paddingLeft. Calls set_auto_layout via figma_mcp_client."""
    import importlib, sys
    fmc = sys.modules.get("figma_mcp_client")
    if fmc is None:
        try:
            fmc = importlib.import_module("figma_mcp_client")
        except ImportError:
            print("  ⚠️ R28: figma_mcp_client not loaded — skip")
            return 0

    fixes = 0
    seen = set()

    def _walk(node, path=""):
        nonlocal fixes
        if not isinstance(node, dict): return
        if id(node) in seen: return
        seen.add(id(node))
        kids = node.get("_children_full") or node.get("children") or []
        if (node.get("layoutMode") or "") == "VERTICAL":
            for i, child in enumerate(kids):
                if not isinstance(child, dict): continue
                if not _is_horizontal_carousel(child):
                    continue
                title = _find_title_sibling(node, i)
                if not title:
                    continue

                def _abs_x(n):
                    bb = n.get("absoluteBoundingBox") if isinstance(n, dict) else None
                    if isinstance(bb, dict) and "x" in bb:
                        return float(bb["x"])
                    return float(n.get("x") or 0) if isinstance(n, dict) else 0.0

                # Use title's CONTENT x (first TEXT inside) — not wrapper x —
                # so carousel paddingLeft accounts for title's own paddingLeft.
                title_content_x = _title_content_x(title)
                if title_content_x is None:
                    title_content_x = _abs_x(title)
                car_x = _abs_x(child)
                car_kids = child.get("_children_full") or child.get("children") or []
                first = car_kids[0] if car_kids else None
                if not first:
                    continue
                first_x = _abs_x(first)
                if abs(title_content_x - first_x) <= 1.5:
                    continue
                # New paddingLeft = title_content_x - carousel_x
                new_pad = max(0, int(round(title_content_x - car_x)))
                try:
                    fmc.call_tool("set_auto_layout", {
                        "nodeId": child.get("id"),
                        "layoutMode": "HORIZONTAL",
                        "paddingLeft": new_pad,
                    })
                    print(f"  R28 carousel-align: {child.get('name')} "
                          f"paddingLeft → {new_pad}px (match title content x={title_content_x:.0f})")
                    fixes += 1
                except Exception as e:
                    print(f"  ⚠️ R28 align 실패 ({child.get('name')}): {e}")
        for c in kids:
            _walk(c, f"{path}/{c.get('name','?')}" if isinstance(c, dict) else path)
    _walk(tree)
    return fixes


register(Rule(
    rule_id="R28-carousel-align",
    title="Horizontal carousel first card aligns with section title",
    description=(
        "Carousel's first card MUST share x with its title sibling. "
        "Set paddingLeft on the carousel; section padding stays 0."
    ),
    auto_fix_built_fn=_autofix,
    check_built_fn=_verify,
))
