"""R56 — Lounge/product 카드 imageQuery 만 박힘 → 실 fetch 없으므로 시각 fallback 강제 (2026-05-28).

문제: R52 가 imageQuery field 존재만 검사. 실 사진 fetch 메커니즘 없어서 빌드 결과
회색 빈 박스 + 좌하단 텍스트만. 와이어 1:1 복제와 동일.

Fix (inject): 'lounge'/'product'/'shop'/'recommend' 이름 카드에 imageQuery 있고
visual 자식 (icon/instance/image) 없으면 자동 fallback 자식 추가:
  1. icon (scene 기반 매핑) 56×56 brand-primary tint 원형
  2. 큰 라벨 (Bold)
  3. 작은 부제 (라벨 다음 줄)

빌드 시 카드 안에 minimum 시각 풍부함 박힘 — 회색 빈 박스 회귀 차단.
"""
from __future__ import annotations

import re

from .base import Rule, register, walk_blueprint


_CARD_NAME_RE = re.compile(r"\b(lounge|product|shop|recommend|item|good)\b", re.I)

# imageQuery scene 키워드 → DS icon 매핑
_SCENE_ICON_MAP = [
    (re.compile(r"caf[eé]|coffee|lounge", re.I), "coffee"),
    (re.compile(r"home|office|desk|workspace", re.I), "home-line"),
    (re.compile(r"travel|airport|suitcase|trip", re.I), "compass-03"),
    (re.compile(r"yoga|wellness|meditation|calm", re.I), "heart"),
    (re.compile(r"book|reading|library", re.I), "book-open-01"),
    (re.compile(r"food|restaurant|dining", re.I), "utensils"),
    (re.compile(r"shopping|store|mall", re.I), "shopping-bag-01"),
]


def _pick_icon(query: str) -> str:
    for pattern, icon in _SCENE_ICON_MAP:
        if pattern.search(query):
            return icon
    return "image-01"  # default


def _has_visual_child(node: dict) -> bool:
    for ch in (node.get("children") or []):
        t = (ch.get("type") or "").lower()
        if t in ("icon", "instance", "rectangle", "vector", "image"):
            return True
        if ch.get("imageQuery") or ch.get("imageUrl"):
            return True
        # 2026-05-28 v15 회귀 fix: icon-wrap / image-wrap 이름 frame 자식이 있으면
        # 이미 시각 콘텐츠 있는 것 — R56 이 또 박는 중복 fallback 차단.
        ch_name = (ch.get("name") or "").lower()
        if t == "frame" and ("icon" in ch_name or "image" in ch_name or "thumbnail" in ch_name):
            return True
    return False


def _inject(bp: dict) -> dict:
    fixed = 0
    for node, _ in walk_blueprint(bp):
        if (node.get("type") or "").lower() != "frame":
            continue
        name = node.get("name") or ""
        if not _CARD_NAME_RE.search(name):
            continue
        query = node.get("imageQuery")
        if not query:
            continue
        if _has_visual_child(node):
            continue
        # 카드 안에 icon wrap + 기존 텍스트 자식 보존 + 부제 추가
        icon_name = _pick_icon(query)
        existing_children = node.get("children", []) or []
        new_children = [
            {
                "name": "card-icon-wrap",
                "type": "frame",
                "width": 48,
                "height": 48,
                "fill": "$token(bg-brand-primary)",
                "cornerRadius": 12,
                "autoLayout": {
                    "layoutMode": "HORIZONTAL",
                    "primaryAxisAlignItems": "CENTER",
                    "counterAxisAlignItems": "CENTER",
                    "paddingLeft": 0, "paddingRight": 0,
                    "paddingTop": 0, "paddingBottom": 0,
                },
                "children": [{
                    "type": "icon",
                    "iconName": icon_name,
                    "size": 28,
                    "iconColor": "$token(fg-brand-primary)",
                }],
            },
        ] + existing_children
        # 부제 — 마지막 라벨 자식 옆에 작은 보조 텍스트 추가 (자식 1개 + icon wrap 만 있으면)
        if len(existing_children) == 1 and (existing_children[0].get("type") or "").lower() == "text":
            label_text = existing_children[0].get("text") or existing_children[0].get("characters") or ""
            new_children.append({
                "type": "text",
                "text": f"바로가기",
                "fontSize": 11,
                "fontName": {"family": "Pretendard", "style": "Medium"},
                "fontColor": "$token(text-tertiary)",
                "name": "card-subtitle",
            })
        node["children"] = new_children
        # 카드 autoLayout 보장
        al = node.setdefault("autoLayout", {})
        if not al.get("layoutMode"):
            al["layoutMode"] = "VERTICAL"
            al["paddingLeft"] = 14
            al["paddingRight"] = 14
            al["paddingTop"] = 14
            al["paddingBottom"] = 14
            al["itemSpacing"] = 10
            al["primaryAxisAlignItems"] = "MIN"
        fixed += 1
    if fixed:
        print(f"[inject R56] Lounge/product 카드 시각 fallback (icon + subtitle) 자동 박음 {fixed}건 (imageQuery fetch 미구현 회피)")
    return bp


register(Rule(
    rule_id="R56-lounge-visual-fallback",
    title="Lounge card visual fallback when no imageQuery fetch",
    description=(
        "imageQuery 만 박혀있고 실 사진 fetch 안 됨 → 자동 icon + subtitle 추가. "
        "회색 빈 박스 회귀 차단. 2026-05-28 사용자 명시."
    ),
    inject_blueprint_fn=_inject,
))
