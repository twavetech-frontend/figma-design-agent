"""R51 — hero text fontSize 자동 승격 (2026-05-28 사용자 명시).

카드/섹션 안의 hero 텍스트 (의미: 핵심 수치/금액/목표) 가 22px 이하면
시각 위계가 약함. 28~32px 로 자동 승격.

Detection (inject):
  - text node 의 fontSize < 24 AND
  - node.name 또는 부모 frame name 에 hero/goal/title-amount/target-amount 포함 OR
  - text characters 에 통화 패턴 (천단위 콤마 + "원" 또는 "만원" 포함) AND
  - text characters 길이 >= 6 (작은 라벨 제외)

Fix: fontSize 30 + fontWeight Bold 로 자동 교체.

[feedback_text_hierarchy] 의 HERO 28~36px 가이드를 코드로 강제.
"""
from __future__ import annotations

import re

from .base import Rule, register


# 2026-05-28 fix: 'hero-caption' / 'hero-footnote' / 'amount-label' 같은
# sub-element 자동 승격 방지. 정확히 hero/goal/main 으로 끝나거나 단독 단어인
# 경우만 매칭 (sub-element 접미사 _RE 로 skip).
_HERO_NAME_RE = re.compile(r"(^|\s)(hero|goal|target|main)\s*$", re.I)
# sub-element 패턴 — caption / label / footnote / sub / small / hint / memo / note
# 2026-05-28 확장: product/price/cell/status/round/item/list/grid 등 카드 안 sub
# 2026-05-28 v17 위계 fix: polish-*, description, desc, copy, para, title 도 skip
#   (currency hero 보다 작은 description 텍스트가 30px 으로 승격되어 위계 무econd)
# 2026-05-28 v19 위계 fix: amount/stage-amount/card-amount 도 skip
#   (Stage Card 안 "월 10만원" 18px 의도가 30px 으로 승격되어 위계 깨짐)
_HERO_SUB_RE = re.compile(r"(caption|label|footnote|sub|small|hint|memo|note|dot|tag|chip|product|price|cell|status|round|item|list|grid|day|row|stepper|pill|badge|track|fill|track-fill|polish|description|desc|copy|para|title|currency|amount|stage)", re.I)
# 통화 패턴: "1,300만원" / "총 1,300만원" — 짧은 "+0원" / "0원" 은 길이 가드로 제외
_CURRENCY_RE = re.compile(r"(\d{1,3}(,\d{3})+|\d{4,}).*원|총.*원|만원")


def _walk(node, parent_name=""):
    yield node, parent_name
    for ch in (node.get("children") or []):
        yield from _walk(ch, node.get("name") or "")


def _inject(bp: dict) -> dict:
    for node, parent_name in _walk(bp):
        if (node.get("type") or "").lower() != "text":
            continue
        text = node.get("text") or node.get("characters") or ""
        if len(text) < 6:
            continue
        # 2026-05-28 위계 fix (사용자 분노): fontSize 명시되어 있으면 사용자 의도 보존.
        # 이전 코드 `fs >= 24 only skip` 은 17/18 등 명시 fontSize 도 30 으로 덮어씀.
        # "이번 달 1,240,000원 수령했어요" footnote 12px + "+14,420,320원" 17px 명시인데
        # currency 매칭으로 둘 다 30px 박혀 위계 무너짐. 명시 fontSize 는 무조건 보존.
        fs = node.get("fontSize")
        if fs is not None:
            continue
        name = node.get("name") or ""
        # sub-element 자동 승격 차단: hero-caption/hero-label/hero-footnote 등
        if _HERO_SUB_RE.search(name):
            continue
        has_hero_name = bool(_HERO_NAME_RE.search(name) or _HERO_NAME_RE.search(parent_name))
        has_currency = bool(_CURRENCY_RE.search(text))
        if not (has_hero_name or has_currency):
            continue
        # 카드 안에 박힌 hero — 부모 width 가 좁으면 (≤200) skip (cell/badge wrap 방지)
        # blueprint 단계에서는 부모 width 모를 수 있으므로 일단 promote
        node["fontSize"] = 30
        font = node.get("fontName") or {}
        font["family"] = font.get("family") or "Pretendard"
        font["style"] = "Bold"
        node["fontName"] = font
        node["_promotedByR51"] = True
    return bp


register(Rule(
    rule_id="R51-hero-scale",
    title="Hero text scale-up — fontSize<24 자동 28~32 승격",
    description=(
        "카드/섹션 안의 hero 텍스트 (이름 hero/goal/target/amount + 통화 패턴) "
        "fontSize<24 이면 시각 위계 약함 → 자동 30px Bold 로 승격. "
        "[feedback_text_hierarchy] HERO 28~36 가이드 코드 강제. 2026-05-28."
    ),
    inject_blueprint_fn=_inject,
))
