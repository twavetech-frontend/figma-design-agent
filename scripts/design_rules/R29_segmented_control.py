"""⛔ R29 — 2026-05-27 폐기. white pill on grey track 패턴 사용자 폐기.

새 룰: Underline Tab 패턴 ([[feedback_underline_tab_v2]]).
사용자 reference 노드(Mode Tabs, file 17382:48541) 분석:
- 컨테이너: HORIZONTAL, paddingLeft/Right=24, paddingBottom=8, itemSpacing=22,
  counterAxisAlignItems=MAX, fill=bg-primary
- 각 탭: VERTICAL HUG x HUG, paddingTop=16, itemSpacing=12, counterAxisAlignItems=CENTER
  - label (TEXT): 16px Bold (active) / Medium (inactive),
    text-primary / text-tertiary 바인딩
  - underline (RECTANGLE): 2.5px, FILL horizontal, fill=bg-brand-solid (active) /
    transparent (inactive)

이 룰은 no-op 으로 남김 (이전 v17 white pill 패턴 강제 폐기).
새 패턴 강제는 별도 R48 또는 메모리/CLAUDE.md 룰로 처리.

Required pattern:
  Wrapper (VERTICAL, fill=bg-primary, padding 16/12)
    └─ Track (HORIZONTAL, fill=bg-secondary, padding 4/4)
       ├─ Active Segment (fill=bg-primary [white pill])
       │  └─ Label (fontColor=fg-primary, Bold)
       └─ Inactive Segment (fill=transparent OR no fill)
          └─ Label (fontColor=fg-tertiary, Medium)

Forbidden on Active:
  - stroke / strokeWeight (no border, no aqua outline)
  - non-fg-primary label color (no aqua/brand text)
  - non-bg-primary fill (must be pure white pill)

This catches the v8 regression where an aqua stroke and aqua-700 label
were applied to "추천" Active. User explicitly rejected that variant
2026-05-05: "segmented control은 저렇게 써야하는거야".
"""
from __future__ import annotations

import re
from typing import Iterable

from .base import Phase, Rule, Severity, Violation, register, walk_blueprint


_ACTIVE_NAME_RE = re.compile(r"(?:^|[^a-zA-Z])(active|선택)\b", re.I)


def _walk_with_parent(node: dict, path: str = "root", parent: dict = None):
    yield node, path, parent
    for i, child in enumerate(node.get("children") or []):
        cname = child.get("name", f"child[{i}]")
        yield from _walk_with_parent(child, f"{path}/{cname}", node)


def _is_segmented_track_parent(parent: dict) -> bool:
    """Track = HORIZONTAL frame with bg fill OR pill cornerRadius. An
    underline tab nav (R35) has neither — bare HORIZONTAL — so we skip
    R29 entirely on those, since R35 owns the active-stroke pattern.
    """
    if not isinstance(parent, dict):
        return False
    al = parent.get("autoLayout") or {}
    if al.get("layoutMode") != "HORIZONTAL" and parent.get("layoutMode") != "HORIZONTAL":
        return False
    fills = parent.get("fill") or parent.get("fills")
    cr = parent.get("cornerRadius") or 0
    try:
        cr = float(cr)
    except (TypeError, ValueError):
        cr = 0
    return bool(fills) or cr >= 16


def _is_segment_track(node: dict) -> bool:
    if not isinstance(node, dict): return False
    al = node.get("autoLayout") or {}
    if al.get("layoutMode") != "HORIZONTAL":
        return False
    name = (node.get("name") or "").lower()
    if "segment" in name or "tab" in name:
        kids = node.get("children") or []
        # Track has 2-4 sibling segments
        if 2 <= len(kids) <= 4:
            return True
    return False


def _is_active_segment(node: dict) -> bool:
    if not isinstance(node, dict): return False
    name = node.get("name") or ""
    if not _ACTIVE_NAME_RE.search(name):
        return False
    return (node.get("type") or "frame").lower() == "frame"


def _check(bp: dict, ctx: dict) -> Iterable[Violation]:
    for node, path, parent in _walk_with_parent(bp):
        if not _is_active_segment(node):
            continue
        # Skip when the parent is a bare HORIZONTAL frame (underline tab
        # nav, R35 territory) — R35 mandates a brand bottom stroke there.
        if not _is_segmented_track_parent(parent):
            continue
        # Forbid stroke
        if node.get("stroke") or node.get("strokeWeight"):
            yield Violation(
                "R29-segmented-control", Severity.ERROR, path,
                "Active Segment must not have a stroke/border. "
                "v17 pattern is a pure white pill (bg-primary) on grey track. "
                "Remove stroke/strokeWeight.",
                Phase.LINT,
            )
        # Active fill must be bg-primary (white) — not aqua/brand
        fill = node.get("fill")
        if isinstance(fill, str):
            fl = fill.lower()
            if "$token(bg-primary)" not in fl and "bg-primary" not in fl:
                yield Violation(
                    "R29-segmented-control", Severity.ERROR, path,
                    f"Active Segment fill must be bg-primary (white pill). "
                    f"Got: {fill}",
                    Phase.LINT,
                )
        # Active label must be fg-primary
        for c in (node.get("children") or []):
            if (c.get("type") or "").lower() == "text":
                fc = c.get("fontColor")
                if isinstance(fc, str):
                    fcl = fc.lower()
                    # Allow fg-primary; reject anything else
                    if "fg-primary" not in fcl:
                        yield Violation(
                            "R29-segmented-control", Severity.ERROR, path,
                            f"Active Segment label fontColor must be "
                            f"fg-primary. Got: {fc}",
                            Phase.LINT,
                        )
                break


# ⛔ 2026-05-27 폐기 — R29 white pill on grey track 룰 등록 해제.
# 새 패턴(Underline Tab) 은 별도 룰/문서로 강제.
# register(Rule(
#     rule_id="R29-segmented-control",
#     title="Segmented control follows imin_home_v17 pattern (white pill, no stroke)",
#     description="Active = bg-primary fill, fg-primary label, no border.",
#     check_blueprint_fn=_check,
# ))
