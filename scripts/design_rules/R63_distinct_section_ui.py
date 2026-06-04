"""R63 — 다른 정보를 같은 레이아웃/UI 로 표현 금지 (2026-06-04 사용자 룰).

사용자 명시: *"다른 정보인데 같은 레이아웃, UI로 표현하지 말것! 똑같아서 같은 정보
같잖아."* — 인접한 두 섹션이 **동일한 카드 구조**(같은 layout mode + 같은 카드 그리드
형태)를 쓰면, 내용이 달라도 같은 정보처럼 보인다. 시각 언어를 차별화해야 한다.

사례(이번 회귀): '시작 방법 카드'(차근차근/빠르게)와 '출석/초대 카드'가 둘 다
[틴트 아이콘 원 + 제목 + 부제] 2-up 그리드라 구분이 안 됨 → 한쪽을 리스트 행으로 변경.

설계 — 보수적(오탐 방지):
  • root 직계 '섹션' 자식들에 대해 **구조 시그니처**(텍스트 내용·색 무시, layout mode +
    rounded 여부 + 자식 구조)를 계산.
  • **카드 그리드**(자식 frame 중 rounded frame ≥2 를 품은 row)를 가진 섹션만 비교 대상.
  • **인접한** 두 섹션의 시그니처가 같으면 WARN (자동 차단 X — 디자인 판단).
  • 같은 섹션 안의 반복 카드(리스트)는 대상 아님 — 그건 R27 담당.
"""
from __future__ import annotations

from typing import Iterable, Optional

from .base import Phase, Rule, Severity, Violation, register

_MAX_DEPTH = 3


def _children(node: dict) -> list:
    return node.get("children") or node.get("_children_full") or []


def _layout_mode(node: dict) -> str:
    al = node.get("autoLayout") or {}
    return (al.get("layoutMode") or node.get("layoutMode") or "")[:1].upper()


def _rounded(node: dict) -> bool:
    cr = node.get("cornerRadius")
    if isinstance(cr, (int, float)) and cr >= 8:
        return True
    for k in ("topLeftRadius", "topRightRadius", "bottomLeftRadius", "bottomRightRadius"):
        v = node.get(k)
        if isinstance(v, (int, float)) and v >= 8:
            return True
    return False


def _sig(node: dict, depth: int = 0) -> tuple:
    """구조 시그니처 — 텍스트 내용/색 무시, 형태만. (type, mode, rounded, children)."""
    if not isinstance(node, dict) or depth > _MAX_DEPTH:
        return ()
    t = (node.get("type") or "frame").lower()
    if t in ("text", "icon", "vector", "rectangle", "ellipse", "instance"):
        return (t[0],)  # leaf — 내용 무시
    mode = _layout_mode(node)
    rb = "r" if _rounded(node) else ""
    kids = tuple(_sig(c, depth + 1) for c in _children(node))
    return ("f", mode, rb, kids)


def _has_card_grid(node: dict) -> bool:
    """섹션이 '카드 그리드'(row 안 rounded frame ≥2)를 품는가."""
    def walk(n: dict, depth: int = 0) -> bool:
        if not isinstance(n, dict) or depth > _MAX_DEPTH:
            return False
        kids = [c for c in _children(n) if isinstance(c, dict)]
        rounded_frames = [c for c in kids
                          if (c.get("type") or "frame").lower() in ("frame",) and _rounded(c)]
        if len(rounded_frames) >= 2:
            return True
        return any(walk(c, depth + 1) for c in kids)
    return walk(node)


def _check_blueprint(blueprint: dict, ctx: dict) -> Iterable[Violation]:
    root = blueprint.get("root") or blueprint
    sections = [c for c in _children(root) if isinstance(c, dict)
                and (c.get("type") or "frame").lower() == "frame"]
    # 카드 그리드 섹션만 추출 (인덱스 보존)
    indexed = [(i, s) for i, s in enumerate(sections) if _has_card_grid(s)]
    for a in range(len(indexed) - 1):
        i1, s1 = indexed[a]
        i2, s2 = indexed[a + 1]
        if i2 != i1 + 1:
            continue  # 인접한 섹션만 (사이에 다른 섹션 있으면 skip)
        if _sig(s1) == _sig(s2):
            n1 = s1.get("name") or f"#{i1}"
            n2 = s2.get("name") or f"#{i2}"
            yield Violation(
                "R63-distinct-section-ui",
                Severity.WARN,
                f"root/{n2}",
                (f"인접 섹션 '{n1}' 과 '{n2}' 가 **동일한 카드 레이아웃/UI** — 다른 정보를 "
                 f"같은 모양으로 그리면 같은 정보처럼 보인다(2026-06-04 사용자 룰). 한쪽의 "
                 f"시각 언어를 바꿀 것: 예) 2-up 그리드 ↔ 리스트 행, 카드 크기/틴트/아이콘 "
                 f"배치 차등. (RULE 0-C 창의적 재해석)"),
                Phase.LINT,
            )


register(Rule(
    rule_id="R63-distinct-section-ui",
    title="다른 정보는 다른 레이아웃/UI 로 (인접 동일 카드 섹션 금지)",
    description=(
        "인접한 두 섹션이 동일한 카드 구조를 쓰면 내용이 달라도 같은 정보처럼 보인다. "
        "구조 시그니처가 같은 인접 카드-그리드 섹션을 WARN — 시각 언어를 차별화하라."
    ),
    check_blueprint_fn=_check_blueprint,
))
