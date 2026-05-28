"""R35 — Underline-style top tab nav: Active item must have a 2px brand
bottom underline; Inactive items must have NO stroke.

Pattern (project canonical, e.g. imin_home Home Tabs at 17037:3648):

  Home Tabs (HORIZONTAL frame)
    ├─ Tab 내 스테이지 (Active)   ← strokeBottomWeight=2, stroke=brand
    └─ Tab 둘러보기                ← no stroke
    (each child is a HORIZONTAL frame containing a single TEXT label)

This is distinct from the bottom Tab Bar (R23/R25) — that one has an icon
+ label per item and uses fg-brand-primary on the active LABEL only, no
underline. This rule targets the LABEL-ONLY top tab nav (segment of a
page) where the visual cue is a bottom underline under the active label.

Why this rule exists:
  HTML/source has a "selected bottom line" under the active tab; earlier
  Figma builds repeatedly omitted the stroke. Encoding it as a rule means
  Claude doesn't need to remember to add it — the inject + post-fix
  phases enforce it automatically.

Detection (a frame is a "tab-nav" if):
  • layoutMode == "HORIZONTAL"
  • has ≥2 frame children
  • every frame child contains exactly ONE TEXT descendant (no icon)
  • at least one child name contains "(Active)" OR has brand-color text
    OR name suggests tab nav ("Home Tabs", "Top Tabs", "Tab Nav",
    "Tabs Wrap", "Section Tabs")
"""
from __future__ import annotations

from typing import Iterable, List, Optional, Tuple

from .base import Phase, Rule, Severity, Violation, register, walk_blueprint, walk_tree


# ── Pattern detection ─────────────────────────────────────────────

_TAB_NAV_NAME_HINTS = (
    "home tabs", "top tabs", "tab nav", "tabs wrap",
    "section tabs", "underline tabs", "page tabs",
)


def _count_text_children(node: dict) -> int:
    """Count TEXT descendants in a node tree (blueprint or built)."""
    if not isinstance(node, dict):
        return 0
    n = 0
    t = (node.get("type") or "").lower()
    if t == "text":
        n += 1
    for c in node.get("children") or node.get("_children_full") or []:
        n += _count_text_children(c)
    return n


def _has_active_marker(child: dict) -> bool:
    name = (child.get("name") or "").lower()
    if not name:
        return False
    return "(active)" in name or name.endswith(" active") or "[active]" in name


def _looks_like_segmented_control(node: dict) -> bool:
    """Segmented control = container has solid fill + large cornerRadius
    (pill). R29 owns that pattern; R35 must not fire on it."""
    fills = node.get("fills") or node.get("fill")
    if not fills:
        return False
    cr = node.get("cornerRadius") or 0
    try:
        cr = float(cr)
    except (TypeError, ValueError):
        cr = 0
    return cr >= 16


def _is_tab_nav(node: dict) -> bool:
    """Heuristic: HORIZONTAL frame whose every child is a frame with a
    single TEXT inside (label-only). Excludes segmented controls (R29)."""
    if not isinstance(node, dict):
        return False
    layout = (node.get("layoutMode") or node.get("autoLayout", {}).get("layoutMode") or "")
    if layout != "HORIZONTAL":
        return False
    if _looks_like_segmented_control(node):
        return False
    kids = node.get("children") or node.get("_children_full") or []
    if len(kids) < 2:
        return False
    # All children must be frames with exactly 1 TEXT descendant
    for k in kids:
        if not isinstance(k, dict):
            return False
        ktype = (k.get("type") or "").lower()
        if ktype != "frame":
            return False
        if _count_text_children(k) != 1:
            return False
        # If the active child has its own fill+pill radius, this is also a
        # segmented control — bail.
        if _has_active_marker(k) and _looks_like_segmented_control(k):
            return False
    # Confirm: at least one child marked Active OR parent name suggests tab nav
    name = (node.get("name") or "").lower()
    if any(h in name for h in _TAB_NAV_NAME_HINTS):
        return True
    if any(_has_active_marker(k) for k in kids):
        return True
    return False


def _find_active_child(parent: dict) -> Optional[Tuple[int, dict]]:
    kids = parent.get("children") or parent.get("_children_full") or []
    for i, k in enumerate(kids):
        if isinstance(k, dict) and _has_active_marker(k):
            return i, k
    # Fallback: first child if name unmarked
    if kids and isinstance(kids[0], dict):
        return 0, kids[0]
    return None


# ── L2 lint (blueprint) ───────────────────────────────────────────

def _check_blueprint(bp: dict, ctx: dict) -> Iterable[Violation]:
    for node, path in walk_blueprint(bp):
        if not _is_tab_nav(node):
            continue
        active = _find_active_child(node)
        if not active:
            continue
        _, ach = active
        sb = ach.get("strokeBottomWeight") or 0
        # Allow auto-fix to handle this — emit WARN (not ERROR) so build
        # continues; inject phase will repair it.
        if sb < 2:
            yield Violation(
                "R35-underline-tab-active",
                Severity.WARN,
                f"{path}/{ach.get('name')}",
                (f"underline tab nav active item missing 2px brand bottom "
                 f"stroke (strokeBottomWeight={sb}). Inject will add it."),
                Phase.LINT,
            )


# ── L3 inject (blueprint) ─────────────────────────────────────────

BRAND_STROKE_TOKEN = "$token(fg-brand-primary)"


def _inject(bp: dict) -> dict:
    """Pre-build: for every detected tab-nav,
      • set Active child's 2px brand bottom underline (and clear inactive strokes)
      • force every tab cell to layoutSizingHorizontal=HUG so the underline
        width matches the text (FILL-distributed tabs produce a too-wide
        line under the cell, not under the label as the HTML reference does)
      • set the tab-nav itemSpacing default of 16 (paired tabs) when missing
      • enforce paddingBottom ≥ 8 so the underline has room
    """
    fixed = 0

    def _walk(n):
        nonlocal fixed
        if not isinstance(n, dict):
            return
        if _is_tab_nav(n):
            # Parent: ensure spacing between tabs (so HUG tabs don't touch)
            if (n.get("itemSpacing") in (None, 0)):
                n["itemSpacing"] = 16
            al = n.get("autoLayout")
            if isinstance(al, dict) and al.get("itemSpacing") in (None, 0):
                al["itemSpacing"] = 16

            kids = n.get("children") or []
            for k in kids:
                if not isinstance(k, dict):
                    continue
                # All tabs HUG horizontally so underline ~= text width
                k["layoutSizingHorizontal"] = "HUG"
                # Make sure all tabs have padding so underline fits below text
                if (k.get("paddingBottom") or 0) < 8:
                    k["paddingBottom"] = 8
                if _has_active_marker(k):
                    # active: 2px brand bottom underline
                    k["strokeWeight"] = 0
                    k["strokeBottomWeight"] = 2
                    k["strokeTopWeight"] = 0
                    k["strokeLeftWeight"] = 0
                    k["strokeRightWeight"] = 0
                    k["strokeAlign"] = "INSIDE"
                    k["stroke"] = BRAND_STROKE_TOKEN
                    fixed += 1
                else:
                    # inactive: no stroke
                    if k.get("stroke") or k.get("strokes"):
                        k["stroke"] = None
                    k["strokeWeight"] = 0
                    k["strokeBottomWeight"] = 0
        for c in n.get("children") or []:
            _walk(c)

    _walk(bp)
    if fixed:
        print(f"  ✓ R35 inject: {fixed} active tab(s) underline-armed")
    return bp


# ── L4 post-fix (built tree) ──────────────────────────────────────

def _autofix(tree: dict, ctx: dict) -> int:
    """Built-tree post-fix: locate tab-nav frames in the actual Figma
    tree and apply 2px brand bottom stroke to active child via
    figma_mcp_client.set_stroke_color.
    """
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
        if _is_tab_nav(n):
            # Set itemSpacing on the nav itself (so HUG tabs are spaced)
            nav_id = n.get("id")
            if nav_id and (n.get("itemSpacing") in (None, 0)):
                try:
                    fmc.call_tool("set_auto_layout", {
                        "nodeId": nav_id,
                        "layoutMode": "HORIZONTAL",
                        "itemSpacing": 16,
                    })
                except Exception:
                    pass
            kids = n.get("_children_full") or n.get("children") or []
            for k in kids:
                if not isinstance(k, dict):
                    continue
                node_id = k.get("id")
                if not node_id:
                    continue
                # Force tab cell to HUG horizontal so underline ≈ text width
                try:
                    fmc.call_tool("set_layout_sizing", {
                        "nodeId": node_id,
                        "layoutSizingHorizontal": "HUG",
                    })
                except Exception:
                    pass
                if _has_active_marker(k):
                    try:
                        # Brand purple ~ #693DEB → r=0.42 g=0.24 b=0.92
                        fmc.call_tool("set_stroke_color", {
                            "nodeId": node_id,
                            "r": 0.42, "g": 0.24, "b": 0.92, "a": 1,
                            "strokeWeight": 0,
                            "strokeBottomWeight": 2,
                            "strokeTopWeight": 0,
                            "strokeLeftWeight": 0,
                            "strokeRightWeight": 0,
                        })
                        print(f"  R35 active-underline: {k.get('name')} → 2px brand (HUG)")
                        fixes += 1
                    except Exception as e:
                        print(f"  ⚠️ R35 active stroke 실패 ({k.get('name')}): {e}")
                else:
                    # Defensive: clear any stray stroke on inactive item
                    try:
                        fmc.call_tool("set_stroke_color", {
                            "nodeId": node_id,
                            "r": 0, "g": 0, "b": 0, "a": 0,
                            "strokeWeight": 0,
                        })
                    except Exception:
                        pass
        for c in n.get("_children_full") or n.get("children") or []:
            _walk(c)

    _walk(tree)
    return fixes


# ── L5 verify (built tree) ────────────────────────────────────────

def _verify(tree: dict, ctx: dict) -> Iterable[Violation]:
    for node, path in walk_tree(tree):
        if not _is_tab_nav(node):
            continue
        active = _find_active_child(node)
        if not active:
            continue
        _, ach = active
        sb = ach.get("strokeBottomWeight") or 0
        strokes = ach.get("strokes") or []
        has_stroke = bool(strokes) or bool(ach.get("stroke"))
        if sb < 2 or not has_stroke:
            yield Violation(
                "R35-underline-tab-active",
                Severity.ERROR,
                f"{path}/{ach.get('name')}",
                (f"underline tab nav active item still missing brand bottom "
                 f"stroke (sb={sb}, has_stroke={has_stroke})"),
                Phase.VERIFY,
            )


register(Rule(
    rule_id="R35-underline-tab-active",
    title="Underline tab nav: active item has 2px brand bottom stroke",
    description=(
        "Top label-only tab nav (HORIZONTAL frame, single TEXT per child) "
        "must show its active item with a 2px brand-purple bottom underline. "
        "Enforced via inject + post-fix; verify blocks if missing."
    ),
    check_blueprint_fn=_check_blueprint,
    inject_blueprint_fn=_inject,
    auto_fix_built_fn=_autofix,
    check_built_fn=_verify,
))
