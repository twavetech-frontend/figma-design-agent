"""R54 — Underline tab active/inactive underline width 통일 (2026-05-28).

문제: Mode Tabs 같은 underline tab 에서 active 탭의 underline (RECTANGLE, FILL) 과
inactive 탭의 underline (transparent RECTANGLE, FILL) 이 부모 라벨 width 에 따라
다른 길이로 박힘. 시각적으로 정렬 깨짐.

이전 룰 [feedback_underline_tab_v2]: "underline RECTANGLE 은 FILL 로 자리만 유지해
높이 일치" — width 도 일치해야 하는데 강제 안 됨.

Fix (inject): 같은 부모 안 sibling tab cell (VERTICAL HUG×HUG, label + underline
RECTANGLE 자식) 들의 underline RECTANGLE width 를 가장 긴 라벨 width 와 같게
강제. 또는 모든 underline 의 layoutSizingHorizontal=FILL + 부모 cell 의
layoutSizingHorizontal=FILL 통일.
"""
from __future__ import annotations

from .base import Rule, register, walk_blueprint


def _has_underline_child(node: dict) -> bool:
    """tab cell 인지 (VERTICAL + 자식에 RECTANGLE 'underline' 포함)."""
    al = node.get("autoLayout") or {}
    if al.get("layoutMode") != "VERTICAL":
        return False
    for ch in (node.get("children") or []):
        if ((ch.get("type") or "").lower() == "rectangle"
                and "underline" in (ch.get("name") or "").lower()):
            return True
    return False


def _inject(bp: dict) -> dict:
    fixed = 0
    for node, _ in walk_blueprint(bp):
        al = node.get("autoLayout") or {}
        if al.get("layoutMode") != "HORIZONTAL":
            continue
        kids = node.get("children") or []
        tab_cells = [k for k in kids if _has_underline_child(k)]
        if len(tab_cells) < 2:
            continue
        # 모든 tab cell + underline 의 layoutSizingHorizontal 통일
        for cell in tab_cells:
            # tab cell 자체는 HUG (라벨 width 따라감) 보존
            for ch in (cell.get("children") or []):
                if ((ch.get("type") or "").lower() == "rectangle"
                        and "underline" in (ch.get("name") or "").lower()):
                    if ch.get("layoutSizingHorizontal") != "FILL":
                        ch["layoutSizingHorizontal"] = "FILL"
                        fixed += 1
                    # height 도 통일 (2.5px standard)
                    if ch.get("height") != 2.5:
                        ch["height"] = 2.5
                        fixed += 1
                    if ch.get("layoutSizingVertical") != "FIXED":
                        ch["layoutSizingVertical"] = "FIXED"
                        fixed += 1
    if fixed:
        print(f"[inject R54] Underline tab underline width/height 통일 {fixed}건")
    return bp


register(Rule(
    rule_id="R54-underline-width",
    title="Underline tab active/inactive underline width unify",
    description=(
        "Underline tab cell sibling 들의 underline RECTANGLE 의 "
        "layoutSizingHorizontal=FILL + height=2.5 통일. active/inactive width 일치. "
        "2026-05-28 사용자 명시."
    ),
    inject_blueprint_fn=_inject,
))
