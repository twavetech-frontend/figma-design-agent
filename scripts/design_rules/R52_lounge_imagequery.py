"""R52 — 라운지/상품 카드는 imageQuery 필수 (2026-05-28 사용자 명시).

라운지/상품 카드처럼 시각 콘텐츠가 핵심인 카드에 imageQuery 가 없으면
회색 빈 박스로 나옴 → 와이어 placeholder 1:1 복제와 동일. build 차단.

Detection (lint ERROR):
  - FRAME 이름이 "lounge" / "product" / "shop" / "recommend" 포함 (카드)
  - children 중 type:"text" 만 있고 image/icon/instance 없음 OR
  - imageQuery / imageUrl / image field 없음
  - width >= 100 AND height >= 100

Fix guidance: `imageQuery: "<scene description>"` 추가 (cmd_build 이미지 fetch).

Bypass: `_imagelessAllowed: "<reason>"`.
"""
from __future__ import annotations

import re
from typing import Iterable

from .base import Phase, Rule, Severity, Violation, register, walk_blueprint


_CARD_NAME_RE = re.compile(r"\b(lounge|product|shop|recommend|item|good)\b", re.I)
_BG_NEUTRAL_TOKENS = ("bg-secondary", "bg-tertiary", "bg-primary")


def _has_visual_child(node: dict) -> bool:
    for ch in (node.get("children") or []):
        t = (ch.get("type") or "").lower()
        if t in ("icon", "instance", "rectangle", "vector", "image"):
            return True
        if ch.get("imageQuery") or ch.get("imageUrl") or ch.get("image"):
            return True
    return False


def _check(bp: dict, ctx: dict) -> Iterable[Violation]:
    for node, path in walk_blueprint(bp):
        if (node.get("type") or "").lower() != "frame":
            continue
        if node.get("_imagelessAllowed"):
            continue
        name = node.get("name") or ""
        if not _CARD_NAME_RE.search(name):
            continue
        w = node.get("width") or 0
        h = node.get("height") or 0
        if w < 100 or h < 100:
            continue
        # 이미 imageQuery / imageUrl 있으면 통과
        if node.get("imageQuery") or node.get("imageUrl") or node.get("image"):
            continue
        # 자식에 visual element 있으면 통과
        if _has_visual_child(node):
            continue
        # fill 이 bg-secondary/tertiary/primary 같은 neutral 이면 — placeholder 위험
        fill = node.get("fill") or ""
        neutral = any(tok in fill for tok in _BG_NEUTRAL_TOKENS) if isinstance(fill, str) else False
        if not neutral:
            continue
        yield Violation(
            "R52-lounge-imagequery",
            Severity.ERROR,
            path,
            (f"frame '{name}' 은 라운지/상품 카드 패턴인데 imageQuery / 시각 자식 "
             f"(icon/instance/rectangle) 없음. 빈 회색 박스 나옴 (RULE 0-C 위반). "
             f"`imageQuery: \"<scene description, e.g. cozy lounge cafe interior natural light>\"` "
             f"또는 icon + label 조합 (children ≥2) 추가. "
             f"Bypass: `_imagelessAllowed: '<reason>'`."),
            Phase.LINT,
        )


register(Rule(
    rule_id="R52-lounge-imagequery",
    title="Lounge/product cards require imageQuery or visual children",
    description=(
        "라운지/상품/추천 카드 (이름 lounge/product/shop/recommend/item) 가 "
        "neutral bg + 텍스트만 있으면 회색 빈 박스 → build 차단. "
        "imageQuery 또는 icon/instance 시각 자식 필수. 2026-05-28 사용자 명시."
    ),
    check_blueprint_fn=_check,
))
