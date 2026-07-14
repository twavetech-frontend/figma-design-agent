"""R65 — 와이어 트레이싱의 구조 시그니처(평면 나열) 감지.

2026-07-14 사용자: "와이어프레임이랑 아주 똑같다! 이러면 디자인 생성 맡길 이유가 없지" +
"원인을 찾아서 다신 그러지 않게 규칙 및 코드 강화해".

배경: S26(_wireframeDivergence)은 선언의 개수/길이만 검사해, 코스메틱 선언으로 형식만
채우고 와이어 배치를 그대로 그리는 트레이싱(imin_stage_joined/preparing_20260714 1차본)이
통과했다. 트레이싱의 구조적 시그니처 = **본문 컨테이너에 표면 그룹 없이 콘텐츠가 평면
나열**되는 것 (와이어는 원래 lo-fi 평면 스택이므로, 이를 그대로 옮기면 이 패턴이 나온다).

검사: 세로 스택 FRAME 중 직계 자식 ≥ _MIN_CHILDREN 인데, 자식 중 '표면 그룹'
(fill 또는 stroke 를 가진 frame/instance — 카드/밴드/박스/버튼)이 _MIN_SURFACE_RATIO
미만이면 ERROR. 콘텐츠를 카드/무대/밴드로 그룹핑해 재설계하라는 신호다.

정당한 평면 리스트 UI(설정 메뉴, 약관 목록 등)는 부모에
`_flatStackAllowed: "<reason>"` 마커로 opt-out.
"""
from __future__ import annotations

from typing import Iterable

from .base import Phase, Rule, Severity, Violation, register

_MIN_CHILDREN = 6        # 이 이상 평면 나열이면 트레이싱 의심
_MIN_SURFACE_RATIO = 0.34  # 표면 그룹 자식 비율이 이 미만이면 ERROR


def _has_surface(node: dict) -> bool:
    """자식이 '표면 그룹'인가 — fill/stroke 가 있는 frame/instance (카드·밴드·박스·버튼·인스턴스)."""
    if not isinstance(node, dict):
        return False
    nt = (node.get("type") or "frame").lower()
    if nt == "instance":
        return True  # DS 컴포넌트(버튼/pill 등)는 표면으로 인정
    if nt != "frame":
        return False
    fill = node.get("fill")
    has_fill = isinstance(fill, (str, dict)) and fill not in (None, "")
    has_stroke = bool(node.get("stroke"))
    # 자기 fill 이 없어도 직계 자식 절반 이상이 표면이면 그룹 래퍼로 인정
    kids = [c for c in (node.get("children") or []) if isinstance(c, dict)]
    if not (has_fill or has_stroke) and kids:
        surf_kids = sum(1 for c in kids if _has_surface(c))
        return surf_kids >= max(1, len(kids) // 2)
    return has_fill or has_stroke


def _is_naked_content(node: dict) -> bool:
    """페이지 바탕에 '맨몸'으로 떠 있는 콘텐츠 — 트레이싱의 핵심 시그니처.

    와이어는 lo-fi 라 텍스트/수치가 표면 없이 나열되는데, 이를 그대로 옮기면
    본문 스택 직계에 bare TEXT / 텍스트만 담은 무표면 frame 이 여러 개 뜬다.
    (디자인된 화면에서는 이런 콘텐츠가 카드/무대/밴드 표면 안에 산다.)
    """
    if not isinstance(node, dict):
        return False
    nt = (node.get("type") or "frame").lower()
    if nt == "text":
        return True
    if nt != "frame" or node.get("fill") or node.get("stroke"):
        return False
    kids = [c for c in (node.get("children") or []) if isinstance(c, dict)]
    if not kids:
        return False
    return all((c.get("type") or "").lower() == "text"
               or _is_naked_content(c) for c in kids)


def _walk(node: dict, path: str) -> Iterable[Violation]:
    if not isinstance(node, dict):
        return
    name = node.get("name") or "?"
    cur = f"{path}/{name}"
    kids = [c for c in (node.get("children") or []) if isinstance(c, dict)]
    al = node.get("autoLayout") or {}
    is_vertical = (al.get("layoutMode") or "").upper() == "VERTICAL"
    if (is_vertical and len(kids) >= _MIN_CHILDREN
            and not node.get("_flatStackAllowed")):
        surfaces = sum(1 for c in kids if _has_surface(c))
        naked = [c.get("name") or c.get("text", "?")[:12] for c in kids if _is_naked_content(c)]
        low_surface = surfaces / len(kids) < _MIN_SURFACE_RATIO
        if low_surface or len(naked) >= 3:
            yield Violation(
                "R65-flat-stack-tracing", Severity.ERROR, cur,
                (f"세로 스택 직계 자식 {len(kids)}개 — 맨몸 콘텐츠 {len(naked)}개"
                 f"({', '.join(str(n) for n in naked[:4])}…) / 표면 그룹 {surfaces}개. "
                 f"와이어 lo-fi 평면 나열을 그대로 옮긴 트레이싱 시그니처다. "
                 f"콘텐츠를 카드/무대/밴드 표면으로 그룹핑해 구조를 재설계할 것 (S26 구조 발산, "
                 f"2-L 은 메트릭 승계지 배치 트레이싱 면죄부가 아님 — 2026-07-14 사용자 룰). "
                 f"정당한 평면 리스트(설정 메뉴 등)면 _flatStackAllowed:'<reason>'."),
                Phase.LINT,
            )
    for c in kids:
        yield from _walk(c, cur)


def _check(blueprint: dict, ctx: dict) -> Iterable[Violation]:
    yield from _walk(blueprint, "root")


register(Rule(
    rule_id="R65-flat-stack-tracing",
    title="와이어 평면 나열 트레이싱 감지 (표면 그룹 부재)",
    description="본문 세로 스택에 카드/밴드 그룹 없이 ≥6 자식 평면 나열이면 구조 발산 부족.",
    check_blueprint_fn=_check,
))
