"""R26 — Aqua 보조 액센트 권장 (2026-06-02 사용자 룰: 정책 반전).

사용자 명시 2026-06-02:
  "현재 포인트 컬러로 브랜드 컬러만 쓰고 있는데, 그로인해 생성된 디자인 화면들의
   컬러감이 너무 단조로워서 보조 컬러로 Utility / Aqua 컬러를 사용하도록 추가."

⚠️ 정책 반전 이력:
  • 2026-05-05 이전: R26 이 utility-blue-light 를 second accent 로 *권장* 했음.
  • 2026-05-05: 사용자가 "aqua 컬러 쓰지마라" → R26 이 aqua/cyan/teal 을 *차단(ERROR)*.
  • 2026-06-02: 사용자가 다시 뒤집음 → Aqua 를 보조 액센트로 *권장*. 차단 폐기.

규칙 (현재):
  • 브랜드 퍼플(`bg-brand-*`/`fg-brand-*`/`text-brand-*`) = **주 액센트** — 주 액션(CTA)·
    active 탭/네비·핵심 hero 수치. 그대로 유지.
  • **Aqua = 보조 액센트** — 브랜드 단색만 쓰면 단조로우므로, *의도된 지점*에 Aqua 를
    절제 사용해 컬러 리듬을 만든다:
      - 보조 아이콘 + 그 틴트 원형 (한 쌍의 카드 중 하나를 Aqua 로 차등화 등)
      - 정보/팁 하이라이트, 보조 통계 강조, 보조 인디케이터·도트·작은 바
    DS 의 semantic Aqua 토큰(2026-06-02 사용자 추가/명명):
      - solid/아이콘:  `$token(utility-aqua-500)` (#00c6d4)  / 텍스트 대비용 `utility-aqua-600`
      - 연한 틴트 bg:  `$token(utility-aqua-50)` · `utility-aqua-100`
      - 흰 배경 위 텍스트: `$token(utility-aqua-700)` (#007b84)
    (figmaPath: `Component colors/Utility/Aqua/utility-aqua-{N}`. 토큰 export 에 아직
     없을 때도 `_normalize_aqua_token` 이 동일 값 primitive `Colors/Aqua/{N}` 로 폴백 —
     해석·바인딩 모두 동작. primitive `$token(Colors/Aqua/{N})` 직접 사용도 가능.)
  • 단, "여러 색 난무"는 여전히 금지 — Aqua 는 *하나의 보조* 액센트일 뿐, 모든 카드·
    태그·통계에 무분별하게 깔지 않는다. 상태 컬러(success/warning/error)는 진짜 상태에만.

동작:
  • 차단 없음 (block 폐기). Aqua/cyan/teal 토큰은 이제 허용.
  • LINT WARN(advisory): 브랜드 액센트가 충분히 많은데(≥4) Aqua 보조 액센트가 0 이면
    "단조로움 — Aqua 보조 액센트 추가 권장" 1건 경고. 자동 치환은 하지 않는다
    (색 적용은 디자인 판단 — Claude 가 blueprint 저작 시 적용).
"""
from __future__ import annotations

import re
from typing import Iterable

from .base import Phase, Rule, Severity, Violation, register, walk_blueprint

_TOKEN_RE = re.compile(r"\$token\(\s*([^)]+?)\s*\)")

# 권장 Aqua 보조 액센트 토큰 (semantic — 2026-06-02 사용자 명명 utility-aqua-*)
APPROVED_AQUA_TOKENS = (
    "utility-aqua-500",   # solid / 아이콘
    "utility-aqua-600",   # 텍스트 대비
    "utility-aqua-700",   # 흰 배경 위 텍스트
    "utility-aqua-50",    # 연한 틴트 bg
    "utility-aqua-100",   # 연한 틴트 bg
    "utility-aqua-200",
)

_COLOR_FIELDS = ("fill", "fontColor", "iconColor", "stroke", "strokeColor")


def _scan_token_refs(obj, depth: int = 0):
    if depth > 12:
        return
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _scan_token_refs(v, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            yield from _scan_token_refs(v, depth + 1)
    elif isinstance(obj, str):
        for m in _TOKEN_RE.finditer(obj):
            yield m.group(1).strip()


def _check(bp: dict, ctx: dict) -> Iterable[Violation]:
    # 🔴 2026-06-05 정책 재반전 (사용자: "전에 아쿠아 컬러 사용하라고 했었는데 이젠 아쿠아
    #    컬러 사용을 자제하도록"): Aqua 권장 폐기 → Aqua 사용 자제. 사용 시 advisory 로
    #    중립/brand tint 대체를 권고한다(완전 차단은 아님 — '자제').
    aqua = 0
    for node, _path in walk_blueprint(bp):
        scan_target = {k: v for k, v in node.items() if k != "children"}
        for tok in _scan_token_refs(scan_target):
            if "aqua" in tok.lower():
                aqua += 1
    if aqua > 0:
        yield Violation(
            "R26-aqua-restraint", Severity.WARN, "root",
            f"Aqua {aqua}곳 사용 — 2026-06-05 사용자 룰: Aqua 컬러 사용을 자제한다. "
            "주 액센트 브랜드 퍼플 + 상태색(success/warning/error, 진짜 상태에만) 위주로 구성하고, "
            "Aqua 는 꼭 필요한 경우가 아니면 중립(bg-secondary/text-secondary 등) 또는 brand tint "
            "(bg-brand-secondary/text-brand-primary)로 대체할 것.",
            Phase.LINT,
        )


register(Rule(
    rule_id="R26-aqua-restraint",
    title="Aqua 보조 액센트 자제 (2026-06-05 정책 재반전)",
    description="브랜드 퍼플=주 액센트, 상태색=진짜 상태에만. Aqua 는 자제 — 사용 시 중립/brand "
                "tint 대체 advisory. (2026-06-02 'Aqua 권장' → 2026-06-05 '자제' 재반전)",
    check_blueprint_fn=_check,
))
