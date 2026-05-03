"""R30 — Wrappers around existing post-fix functions in figma_mcp_client.

These rules don't reimplement the fix logic — they reference functions
already battle-tested in figma_mcp_client.py. The registry just records
which fix is responsible for which rule_id, so post-fix logs become
attributable to specific rules.

The actual cmd_post_fix in figma_mcp_client.py still drives the order;
this module just registers metadata + thin call-throughs.
"""
from __future__ import annotations

from typing import Iterable, Optional

from .base import Phase, Rule, Severity, Violation, register


def _lazy_client():
    """Lazy-import figma_mcp_client to avoid circular import at package load."""
    import importlib, sys
    # figma_mcp_client lives next to design_rules/
    if "figma_mcp_client" not in sys.modules:
        import scripts  # noqa: F401  ensures path is set
    return importlib.import_module("figma_mcp_client")


# ── Wrapper builders ─────────────────────────────────────────────

def _wrap_fix_fill_sizing(tree: dict, ctx: dict) -> int:
    return _lazy_client()._fix_fill_sizing(tree)


def _wrap_fix_tab_bar_items(tree: dict, ctx: dict) -> int:
    return _lazy_client()._fix_tab_bar_items(tree)


def _wrap_fix_zero_width_text(tree: dict, ctx: dict) -> int:
    return _lazy_client()._fix_zero_width_text(tree)


def _wrap_fix_stroke_alignment(tree: dict, ctx: dict) -> int:
    return _lazy_client()._fix_stroke_alignment(tree)


def _wrap_match_status_bar_bg(tree: dict, ctx: dict) -> int:
    return 1 if _lazy_client()._match_status_bar_bg_to_nav(tree) else 0


# ── Register ────────────────────────────────────────────────────

register(Rule(
    rule_id="R30-fill-sizing",
    title="Recursive FILL sizing for FRAME children",
    description="Walks built tree, sets layoutSizingHorizontal=FILL on all eligible frames.",
    auto_fix_built_fn=_wrap_fix_fill_sizing,
))

register(Rule(
    rule_id="R31-tab-bar-items",
    title="Tab Bar item FILL + bottom-only stroke",
    auto_fix_built_fn=_wrap_fix_tab_bar_items,
))

register(Rule(
    rule_id="R32-zero-width-text",
    title="Width=0 TEXT auto-resize",
    auto_fix_built_fn=_wrap_fix_zero_width_text,
))

register(Rule(
    rule_id="R33-stroke-alignment",
    title="Stroke alignment INSIDE",
    auto_fix_built_fn=_wrap_fix_stroke_alignment,
))

register(Rule(
    rule_id="R34-status-bar-bg",
    title="Status Bar bg matches NavBar",
    auto_fix_built_fn=_wrap_match_status_bar_bg,
))
