"""R36 — Horizontal carousel must show meaningful last-card peek.

When a HORIZONTAL frame with clipsContent (or scrolling overflow) holds
multiple FIXED-width cards, the last card MUST overflow into the right
edge by at least ~25% of its own width — otherwise the carousel looks
clipped/broken (cards 1-2 visible, card 3 entirely hidden behind clip).

Concrete failure observed (imin_home v25):
  Stage Card Scroll: 3 × 200px cards + 12 itemSpacing + 16 paddingLeft.
  Total content = 16 + 200+12 + 200+12 + 200 = 640. Viewport = 390.
  Card 1 fully shown, Card 2 mostly shown (162px peek), Card 3 entirely
  outside the clip — invisible. User reads it as "잘렸다".

Computation (post-fix tree, with absoluteBoundingBox available):
  let viewportR = carousel.x + carousel.width
  let lastCardR = lastCard.x + lastCard.width
  let lastCardL = lastCard.x
  let visibleW  = max(0, viewportR - lastCardL)  # how much of last card is in clip
  fail if visibleW < 0.25 * lastCard.width AND visibleW < 60

Auto-fix on the BUILT tree:
  reduce each card's width by Δ so that total fits viewport with last card
  ≥35% peeked. Carousel itemSpacing and paddingLeft preserved.

  Δ per card = ceil((totalContent - viewportR + 0.35*cardW) / nCards)

Lint phase (blueprint): if all cards have explicit `width` and the same
math fails, emit WARN with concrete card-width recommendation.
"""
from __future__ import annotations

import math
from typing import Iterable, List, Optional

from .base import Phase, Rule, Severity, Violation, register, walk_blueprint, walk_tree


def _is_horizontal_carousel_blueprint(node: dict) -> bool:
    if not isinstance(node, dict): return False
    al = node.get("autoLayout") or {}
    layout = al.get("layoutMode") or node.get("layoutMode")
    if layout != "HORIZONTAL":
        return False
    if not (node.get("clipsContent") or al.get("clipsContent")):
        return False
    return True


def _carousel_card_widths(node: dict) -> Optional[List[int]]:
    """Return list of card widths if every direct child has an explicit
    integer width. Otherwise None (cannot compute statically)."""
    kids = node.get("children") or []
    if len(kids) < 2:
        return None
    widths = []
    for k in kids:
        if not isinstance(k, dict): return None
        w = k.get("width")
        if not isinstance(w, (int, float)) or w <= 0:
            return None
        widths.append(int(w))
    return widths


def _viewport_width_blueprint(node: dict, ctx: dict) -> Optional[int]:
    """Approximate viewport width = root width - sum of nav padding etc.
    Use the carousel's own assumed parent width if unknown.
    Fallback: 390 (standard mobile width)."""
    # We don't have layout info in blueprint — use heuristic
    bp = ctx.get("blueprint") or {}
    rw = bp.get("width") or 390
    return int(rw)


def _check_blueprint(bp: dict, ctx: dict) -> Iterable[Violation]:
    for node, path in walk_blueprint(bp):
        if not _is_horizontal_carousel_blueprint(node):
            continue
        widths = _carousel_card_widths(node)
        if not widths:
            continue
        al = node.get("autoLayout") or {}
        pad_l = al.get("paddingLeft") or 0
        pad_r = al.get("paddingRight") or 0
        spacing = al.get("itemSpacing") or 0
        viewport = _viewport_width_blueprint(node, ctx)
        # Total content width when all cards laid out
        total = pad_l + sum(widths) + spacing * (len(widths) - 1)
        # If total <= viewport: everything visible — fine
        if total <= viewport - 1:
            continue
        # Otherwise check last card peek
        # Last card left edge = pad_l + sum(widths[:-1]) + spacing*(n-1)
        last_left = pad_l + sum(widths[:-1]) + spacing * (len(widths) - 1)
        viewport_right = viewport - pad_r
        peek = max(0, viewport_right - last_left)
        last_w = widths[-1]
        if peek < 0.25 * last_w and peek < 60:
            # Suggest a smaller card width
            n = len(widths)
            target_peek = int(0.4 * last_w)
            new_total = viewport_right - target_peek
            new_card_w = max(120, int((new_total - pad_l - spacing * (n - 1)) / n))
            yield Violation(
                "R36-carousel-peek",
                Severity.WARN,
                path,
                (f"horizontal carousel '{node.get('name')}' has {n} cards "
                 f"of width {widths[0]}; last card peeks only {peek}px "
                 f"(<25% of {last_w}). Reduce card width to ~{new_card_w} "
                 f"so the last card peeks at least ~{target_peek}px."),
                Phase.LINT,
            )


def _is_horizontal_carousel_tree(node: dict) -> bool:
    if not isinstance(node, dict): return False
    layout = (node.get("layoutMode") or "")
    if layout != "HORIZONTAL":
        return False
    return bool(node.get("clipsContent"))


def _abs_x(n: dict) -> Optional[float]:
    bb = n.get("absoluteBoundingBox") if isinstance(n, dict) else None
    if isinstance(bb, dict) and "x" in bb: return float(bb["x"])
    if isinstance(n, dict) and "x" in n: return float(n["x"])
    return None


def _autofix(tree: dict, ctx: dict) -> int:
    """Post-fix: walk built tree, find horizontal carousels with the
    last-card-hidden problem, and resize children to restore peek."""
    import importlib, sys
    fmc = sys.modules.get("figma_mcp_client")
    if fmc is None:
        try:
            fmc = importlib.import_module("figma_mcp_client")
        except ImportError:
            return 0

    fixes = 0
    seen = set()

    def _walk(n):
        nonlocal fixes
        if not isinstance(n, dict): return
        if id(n) in seen: return
        seen.add(id(n))
        if _is_horizontal_carousel_tree(n):
            kids = n.get("_children_full") or n.get("children") or []
            if len(kids) >= 2 and all(isinstance(k, dict) for k in kids):
                widths = [k.get("width") or 0 for k in kids]
                if all(w > 0 for w in widths):
                    pad_l = n.get("paddingLeft") or 0
                    pad_r = n.get("paddingRight") or 0
                    spacing = n.get("itemSpacing") or 0
                    nav_x = _abs_x(n)
                    nav_w = n.get("width") or 0
                    if nav_x is not None and nav_w:
                        viewport_right = nav_x + nav_w - pad_r
                        last_card = kids[-1]
                        last_x = _abs_x(last_card)
                        last_w = widths[-1]
                        if last_x is not None:
                            peek = max(0, viewport_right - last_x)
                            if peek < 0.25 * last_w and peek < 60:
                                # compute target card width
                                target_peek = int(0.4 * last_w)
                                count = len(kids)
                                new_total = nav_w - pad_l - pad_r - target_peek
                                new_w = max(120, int((new_total - spacing * (count - 1)) / count))
                                if new_w < last_w - 5:
                                    for k in kids:
                                        kid_id = k.get("id")
                                        if not kid_id: continue
                                        try:
                                            fmc.call_tool("resize_node", {
                                                "nodeId": kid_id,
                                                "width": new_w,
                                                "height": k.get("height") or 0,
                                            })
                                            fixes += 1
                                        except Exception as e:
                                            print(f"  ⚠️ R36 resize 실패 ({k.get('name')}): {e}")
                                    print(f"  R36 carousel-peek: '{n.get('name')}' "
                                          f"{count}× cards {last_w}→{new_w} "
                                          f"(target peek ≈{target_peek}px)")
        for c in n.get("_children_full") or n.get("children") or []:
            _walk(c)

    _walk(tree)
    return fixes


def _verify(tree: dict, ctx: dict) -> Iterable[Violation]:
    for node, path in walk_tree(tree):
        if not _is_horizontal_carousel_tree(node):
            continue
        kids = node.get("_children_full") or node.get("children") or []
        if len(kids) < 2:
            continue
        widths = [k.get("width") or 0 for k in kids if isinstance(k, dict)]
        if not all(w > 0 for w in widths) or len(widths) != len(kids):
            continue
        nav_x = _abs_x(node)
        nav_w = node.get("width") or 0
        if nav_x is None or not nav_w:
            continue
        pad_r = node.get("paddingRight") or 0
        viewport_right = nav_x + nav_w - pad_r
        last = kids[-1]
        last_x = _abs_x(last)
        last_w = widths[-1]
        if last_x is None: continue
        peek = max(0, viewport_right - last_x)
        if peek < 0.2 * last_w and peek < 50:
            yield Violation(
                "R36-carousel-peek",
                Severity.WARN,
                f"{path}/{last.get('name')}",
                (f"last carousel card '{last.get('name')}' peeks only "
                 f"{peek:.0f}px out of its {last_w} width — appears clipped"),
                Phase.VERIFY,
            )


register(Rule(
    rule_id="R36-carousel-peek",
    title="Horizontal carousel last card must peek (≥25% of width or 60px)",
    description=(
        "Horizontal scroll carousels must reveal at least a fraction of "
        "the last card past the viewport — otherwise users perceive the "
        "card as cut off rather than scrollable."
    ),
    check_blueprint_fn=_check_blueprint,
    auto_fix_built_fn=_autofix,
    check_built_fn=_verify,
))
