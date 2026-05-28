"""R55 — Stepper minus/plus 아이콘 시인성 강화 (2026-05-28).

문제: Stepper (- value +) 의 minus/plus 아이콘이 fg-tertiary (#b1b6be) 로 박혀
카드 bg-secondary (#f3f4f6) 위 대비 1.5 — WCAG AA 미달. 시각적으로 거의 안 보임.

Fix (inject): name 에 'stepper' 포함된 frame 또는 sibling 에 minus/plus 가 동시
존재하는 frame 의 icon 자식의 iconColor 가 fg-tertiary 면 → fg-secondary 자동 승격.
"""
from __future__ import annotations

from .base import Rule, register, walk_blueprint


_STEPPER_ICON_NAMES = ("minus", "plus")


def _is_stepper_frame(node: dict) -> bool:
    if (node.get("type") or "").lower() != "frame":
        return False
    name = (node.get("name") or "").lower()
    if "stepper" in name:
        return True
    # 휴리스틱: 자식에 minus + plus icon 둘 다 있으면 stepper
    icon_names = set()
    for ch in (node.get("children") or []):
        if (ch.get("type") or "").lower() == "icon":
            icon_names.add(ch.get("iconName"))
    if "minus" in icon_names and "plus" in icon_names:
        return True
    return False


def _inject(bp: dict) -> dict:
    fixed = 0
    for node, _ in walk_blueprint(bp):
        if not _is_stepper_frame(node):
            continue
        for ch in (node.get("children") or []):
            if (ch.get("type") or "").lower() != "icon":
                continue
            if ch.get("iconName") not in _STEPPER_ICON_NAMES:
                continue
            color = ch.get("iconColor") or ""
            if "fg-tertiary" in color or "text-tertiary" in color:
                ch["iconColor"] = "$token(fg-secondary)"
                fixed += 1
    if fixed:
        print(f"[inject R55] Stepper minus/plus 아이콘 fg-tertiary → fg-secondary 승격 {fixed}건")
    return bp


register(Rule(
    rule_id="R55-stepper-icon-visibility",
    title="Stepper minus/plus icon contrast",
    description=(
        "Stepper (-value+) 의 minus/plus 아이콘이 fg-tertiary 면 시인성 약함 "
        "(WCAG AA 미달). fg-secondary 자동 승격. 2026-05-28 사용자 명시."
    ),
    inject_blueprint_fn=_inject,
))
