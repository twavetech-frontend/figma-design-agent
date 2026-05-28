"""R50 — wireframe 회색 placeholder 1:1 복제 금지 (2026-05-28 사용자 명시).

문제: 와이어프레임의 회색 placeholder 박스 (라운지 카드, 참여중 빈 카드 등) 를
실제 디자인 산출물에 그대로 박는 회귀. 와이어는 "여기에 카드가 들어간다" 의
intent indicator인데 빌드 결과물이 그대로 회색 박스면 디자인 안 한 것.

Detection (lint ERROR):
  - bg-secondary / bg-tertiary fill 인 FRAME
  - children 0개 또는 1개 (단순 텍스트 라벨만)
  - width >= 80 AND height >= 60 (placeholder-shaped)
  - 이름이 "card" / "lounge" / "empty" / "placeholder" 포함

이 조건 모두 만족하면 "실 콘텐츠/이미지 채우거나 empty state 디자인하라" ERROR.

Bypass: `_placeholderAllowed: "<reason>"` (skeleton loading 같은 의도된 경우).

새 세션 회귀 차단 핵심 룰.
"""
from __future__ import annotations

import re
from typing import Iterable

from .base import Phase, Rule, Severity, Violation, register, walk_blueprint


_PLACEHOLDER_NAME_RE = re.compile(r"\b(card|lounge|empty|placeholder|product|slot)\b", re.I)
_BG_PLACEHOLDER_TOKENS = (
    "bg-secondary",
    "bg-tertiary",
    "bg-quaternary",
    "fg-quaternary",
)


def _fill_is_placeholder(node: dict) -> bool:
    fill = node.get("fill") or ""
    if isinstance(fill, str):
        for tok in _BG_PLACEHOLDER_TOKENS:
            if tok in fill:
                return True
    return False


def _has_real_content(node: dict) -> bool:
    """노드 안에 실 콘텐츠 신호가 있는가."""
    if node.get("imageQuery"):
        return True
    if node.get("imageUrl") or node.get("image"):
        return True
    children = node.get("children", []) or []
    if len(children) >= 2:
        # 2개 이상 자식 = 일정 수준 콘텐츠
        return True
    # icon 자식이 있으면 OK
    for ch in children:
        if (ch.get("type") or "").lower() in ("icon", "instance", "rectangle"):
            return True
        # 하위 자식이 있으면 OK
        if ch.get("children"):
            return True
    return False


def _is_placeholder_shape(node: dict) -> bool:
    if (node.get("type") or "").lower() != "frame":
        return False
    if node.get("_placeholderAllowed"):
        return False
    if not _fill_is_placeholder(node):
        return False
    name = node.get("name") or ""
    if not _PLACEHOLDER_NAME_RE.search(name):
        return False
    # 2026-05-28 v15 회귀 fix: layoutSizingHorizontal=FILL/HUG 케이스 누락
    # 이전 코드는 width 필드 명시된 FIXED 카드만 검사 → FILL 카드 다 통과시킴.
    # v15 의 Empty Card 1/2 (FILL, height=78) 통과시킨 회귀 원인.
    h = node.get("height") or 0
    w = node.get("width") or 0
    sizing_h = node.get("layoutSizingHorizontal") or ""
    sizing_v = node.get("layoutSizingVertical") or ""
    # FIXED 가 명시된 경우 80×60 미만은 작은 dot/badge 로 보고 skip
    if w > 0 and w < 80:
        return False
    if h > 0 and h < 60:
        return False
    # FILL/HUG 인데 height 도 명시 없으면 — name 매칭 + bg-secondary + children<=1 만으로 결정
    # (와이어 placeholder 의 표준 형태)
    if _has_real_content(node):
        return False
    return True


def _check(bp: dict, ctx: dict) -> Iterable[Violation]:
    for node, path in walk_blueprint(bp):
        if not _is_placeholder_shape(node):
            continue
        name = node.get("name") or "<unnamed>"
        yield Violation(
            "R50-no-placeholder-content",
            Severity.ERROR,
            path,
            (f"frame '{name}' is a bare grey placeholder (bg-secondary/-tertiary + name has "
             f"card/lounge/empty/product/slot/placeholder + children≤1, no imageQuery/icon). "
             f"와이어의 회색 placeholder 1:1 복제 금지 (RULE 0-C). "
             f"실 콘텐츠로 채우기: (1) `imageQuery: \"<scene>\"` 박아 사진 fetch, "
             f"(2) icon + 텍스트 + 부제 ≥3개 자식, (3) DS instance 사용, "
             f"또는 (4) empty-state hint card 1개로 통합 후 이 placeholder 삭제. "
             f"Bypass: `_placeholderAllowed: '<reason>'` 박기 (skeleton loading 등 의도된 경우)."),
            Phase.LINT,
        )


register(Rule(
    rule_id="R50-no-placeholder-content",
    title="No wireframe placeholder 1:1 clone — 회색 빈 박스 build 차단",
    description=(
        "와이어프레임의 회색 placeholder 박스 (라운지/empty/product slot 등) 를 "
        "실 콘텐츠 없이 디자인 산출물에 그대로 박으면 build 차단. 실 이미지/icon/"
        "콘텐츠로 채우거나 empty state 디자인으로 통합. 2026-05-28 사용자 명시."
    ),
    check_blueprint_fn=_check,
))
