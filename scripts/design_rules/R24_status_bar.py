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

# DS 'Status Bar' 마스터 스펙 (393×62) — 사용자 명시 2026-06-12
STATUS_BAR_HEIGHT = 62


def _inject(bp: dict) -> dict:
    if not _is_mobile_root(bp):
        return bp
    if _has_status_bar(bp):
        return bp
    # 🔴 2026-06-12 사용자 회귀: vertical "HUG" + height 50 이 DS 마스터(393×62 FIXED)를
    # 내부 콘텐츠 자연 높이(63.5)로 재측정시켜 모든 생성 화면의 Status Bar 가 62→63.5 로
    # 변형됐다. 인스턴스는 마스터 높이를 유지해야 하므로 FIXED 62 로 강제한다.
    sb_node: dict = {
        "name": "Status Bar",
        "type": "instance" if _STATUS_BAR_KEY else "frame",
        "width": bp.get("width", 393),
        "height": STATUS_BAR_HEIGHT,
        "layoutSizingHorizontal": "FILL",
        "layoutSizingVertical": "FIXED",
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
        return
    # 🔴 높이 = 마스터 62 검증 (2026-06-12 회귀: HUG 강제로 63.5 변형)
    sb = children[0]
    bb = sb.get("absoluteBoundingBox") or {}
    h = bb.get("height") or sb.get("height")
    if h is not None and abs(float(h) - STATUS_BAR_HEIGHT) > 1:
        yield Violation(
            "R24-status-bar", Severity.WARN, "root",
            f"Status Bar height {h}px ≠ {STATUS_BAR_HEIGHT}px — vertical HUG 변형 의심 "
            f"(post-fix _enforce_status_bar_size_live 가 복구해야 함)",
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
