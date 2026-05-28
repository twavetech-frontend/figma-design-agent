"""R57 — FAB 안 icon color = fg-light 강제 (2026-05-28 사용자 명시 절대 룰).

FAB 의 아이콘은 brand-solid bg(보라) 위 흰색이 정석.
blueprint 가 fg-white(alias), fg-primary_on-brand, 검정, 임의 hex 등으로 박았으면
inject 단계에서 fg-light 로 자동 교정.

라이브 트리도 cmd_post_fix 끝의 `_enforce_fab_icon_color_live` 가 마지막에
fg-light 로 덮어씀 — 이 룰은 blueprint 단계의 첫 번째 방어선.

Detection:
  - 이름이 'FAB'/'Fab'/'fab' 인 frame 자손 중
  - type 이 'icon' / 'vector' 인 노드
  - iconColor / fill / stroke / strokeColor 가 fg-light 가 아닌 색 토큰 또는 raw RGB

Fix (inject):
  - iconColor → $token(fg-light)
  - fill (SOLID white) → $token(fg-light)
  - stroke / strokeColor → $token(fg-light)
"""
from __future__ import annotations

from typing import Iterable

from .base import Phase, Rule, Severity, Violation, register, walk_blueprint


_FG_LIGHT = "$token(fg-light)"
_WRONG_TOKENS = (
    "$token(fg-white)",         # alias 가 silent skip 위험
    "$token(text-white)",
    "$token(fg-primary)",
    "$token(fg-primary_on-brand)",
    "$token(text-primary_on-brand)",
    "$token(fg-secondary)",
    "$token(text-secondary)",
)


def _under_fab(path: str) -> bool:
    if not path:
        return False
    p = path.lower()
    return "/fab" in p or p.endswith("/fab") or "/fab/" in p


def _is_icon_role(node: dict) -> bool:
    t = (node.get("type") or "").lower()
    if t in ("icon", "vector"):
        return True
    name = (node.get("name") or "").lower()
    if "icon" in name:
        return True
    return False


def _color_field_wrong(value) -> bool:
    """fg-light 가 아닌 색 토큰 또는 raw 색이면 True."""
    if value is None:
        return False
    if isinstance(value, str):
        v = value.strip()
        if not v:
            return False
        if v == _FG_LIGHT:
            return False
        # fg-light figmaPath 도 OK
        if "fg-light" in v.lower():
            return False
        return True  # 다른 토큰 또는 raw hex
    # dict (raw {r,g,b}) 등도 wrong
    return True


def _check(bp: dict, ctx: dict) -> Iterable[Violation]:
    for node, path in walk_blueprint(bp):
        if not _under_fab(path):
            continue
        if not _is_icon_role(node):
            continue
        for field in ("iconColor", "fill", "stroke", "strokeColor"):
            val = node.get(field)
            if val is None:
                continue
            if _color_field_wrong(val):
                yield Violation(
                    "R57-fab-icon-fg-light",
                    Severity.ERROR,
                    path,
                    (f"FAB 안 icon '{node.get('name') or node.get('iconName')}' {field}='{val}' "
                     f"— 무조건 $token(fg-light) (brand-solid 위 흰 아이콘 정석). "
                     f"fg-white(alias)/fg-primary_on-brand/검정/raw RGB 모두 금지. "
                     f"2026-05-28 사용자 명시 절대 룰."),
                    Phase.LINT,
                )


def _inject(bp: dict) -> int:
    fixed = 0
    for node, path in walk_blueprint(bp):
        if not _under_fab(path):
            continue
        if not _is_icon_role(node):
            continue
        for field in ("iconColor", "fill", "stroke", "strokeColor"):
            val = node.get(field)
            if val is None:
                continue
            if _color_field_wrong(val):
                node[field] = _FG_LIGHT
                fixed += 1
    if fixed:
        print(f"[inject R57] FAB icon color {fixed}건 → $token(fg-light) 강제")
    return fixed


register(Rule(
    rule_id="R57-fab-icon-fg-light",
    title="FAB 안 icon color must be fg-light",
    description=(
        "FAB 의 아이콘은 brand-solid 보라 위 흰색이 정석. blueprint 가 fg-white "
        "(alias 라 silent skip 위험) / fg-primary_on-brand / 검정 / raw RGB 로 박았으면 "
        "inject 가 자동으로 $token(fg-light) 로 교정. 라이브 트리도 cmd_post_fix 끝의 "
        "_enforce_fab_icon_color_live 가 마지막에 fg-light 로 덮어씀."
    ),
    check_blueprint_fn=_check,
    inject_blueprint_fn=_inject,
))
