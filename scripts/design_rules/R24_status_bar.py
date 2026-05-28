"""R24 — Mobile root must contain a Status Bar instance.

L2 (lint):    warn if mobile-sized root has no Status Bar child.
L3 (inject):  auto-prepend a Status Bar component instance node so the
              build pipeline materializes it (works around plugin
              findOne miss when the component isn't already in the file).
L5 (verify):  error if built tree's first child is not a Status Bar.
"""
from __future__ import annotations

import re
from typing import Iterable, List

from .base import Phase, Rule, Severity, Violation, register
from .ds_catalog import COMPONENT_KEYS


_SB_RE = re.compile(r"\bstatus\s*[_-]?\s*bar\b", re.I)


def _is_mobile_root(bp: dict) -> bool:
    """Mobile root if width is phone-sized OR statusBar:true is explicit.

    height is often unset (HUG) at blueprint time, so we cannot rely on
    height >= 700. Combine width range with explicit statusBar flag.
    """
    w = bp.get("width", 0) or 0
    if 360 <= w <= 430:
        return True
    return bool(bp.get("statusBar"))


def _has_status_bar(bp: dict) -> bool:
    for c in bp.get("children") or []:
        if _SB_RE.search(c.get("name", "") or ""):
            return True
    return False


# ── L2 lint ───────────────────────────────────────────────────────

def _lint(bp: dict, ctx: dict) -> Iterable[Violation]:
    if not _is_mobile_root(bp):
        return
    if _has_status_bar(bp):
        return
    yield Violation(
        "R24-status-bar", Severity.WARN, "root",
        "mobile root has no Status Bar child — auto-injected at build time",
        Phase.LINT, auto_fixable=True,
    )


# ── L3 inject ─────────────────────────────────────────────────────

# Try a known componentKey if available; otherwise fall back to a
# named frame so the plugin's findOne can adopt an existing instance.
_STATUS_BAR_KEY = COMPONENT_KEYS.get("Status Bar")


def _inject(bp: dict) -> dict:
    if not _is_mobile_root(bp):
        return bp
    if _has_status_bar(bp):
        return bp
    sb_node: dict = {
        "name": "Status Bar",
        "type": "instance" if _STATUS_BAR_KEY else "frame",
        "width": bp.get("width", 393),
        "height": 50,
        "layoutSizingHorizontal": "FILL",
        "layoutSizingVertical": "HUG",
    }
    if _STATUS_BAR_KEY:
        sb_node["componentKey"] = _STATUS_BAR_KEY
    bp.setdefault("children", []).insert(0, sb_node)
    print("[inject R24] Status Bar prepended to mobile root")
    return bp


# ── L5 verify ─────────────────────────────────────────────────────

def _verify(tree: dict, ctx: dict) -> Iterable[Violation]:
    bp = ctx.get("blueprint") or {}
    if not _is_mobile_root(bp):
        return
    children = tree.get("children") or []
    if not children:
        yield Violation("R24-status-bar", Severity.ERROR, "root",
                        "built root has no children — Status Bar missing",
                        Phase.VERIFY)
        return
    first_name = (children[0].get("name") or "").lower()
    if not _SB_RE.search(first_name):
        yield Violation(
            "R24-status-bar", Severity.ERROR, "root",
            f"first child is '{children[0].get('name')}' — Status Bar must be first",
            Phase.VERIFY,
        )


register(Rule(
    rule_id="R24-status-bar",
    title="Mobile root requires Status Bar",
    description="Auto-injects Status Bar instance when missing on mobile-sized root.",
    check_blueprint_fn=_lint,
    inject_blueprint_fn=_inject,
    check_built_fn=_verify,
))
