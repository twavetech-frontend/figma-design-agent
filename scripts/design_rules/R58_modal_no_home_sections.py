"""R58 — Modal/bottom-sheet must contain ONLY wireframe content, never home sections.

2026-05-28 사용자 분노 (반복): "이 화면은 메인화면에서 스테이지 내역 tap 하면 뜨는
full modal 이야. 상단엔 X 버튼만 있어야되고 tab bar 나 fab 가 없어야지. 왜 와이어프레임에
없는 정보가 가득있지? 메인화면에 있는 섹션들이 그대로 남아있는데."

근본 원인: 모달을 만들 때 unified imin_home 베이스를 끌어다 써서 홈 대시보드 섹션
(Tab Bar / FAB / Footer / Screen Hero / Top Alert / Recommend Stage / Lounge /
Attendance / Mode Tabs / Sub-card CTA / Participating) 이 통째로 박힘.
[feedback_wireframe_is_truth] 메모리 룰은 있었지만 하드 코드 게이트가 없어서 반복 위반.

이 룰은 root `_screenType` 이 modal / bottom-sheet 일 때:
  - 절대 금지(절대 규칙 0-D): Tab Bar / FAB / Footer  → ERROR (build BLOCKED)
  - 홈 전용 auto/polish 섹션 (unified imin_home generator 산물) → ERROR
바이패스: blueprint root 에 `_modalAllowSections: ["Lounge", ...]` 로 명시하면 해당
이름은 허용 (와이어에 진짜 그 섹션이 있는 드문 경우).
"""
from __future__ import annotations

from typing import Iterable, List

from .base import Phase, Rule, Severity, Violation, register, walk_blueprint

_MODAL_TYPES = ("modal", "bottom-sheet", "bottomsheet")

# 모달에서 절대 금지 (절대 규칙 0-D)
_FORBIDDEN = ("tab bar", "tabbar", "bottom tab", "bottom nav", "fab", "footer")

# 홈 대시보드 전용 섹션 (unified imin_home generator 산물) — 모달에 있으면 거의 확실히
# 홈 베이스를 잘못 끌어온 것. 와이어에 실제로 있으면 _modalAllowSections 로 허용.
_HOME_ONLY = (
    "screen hero", "top alert", "recommend stage", "lounge",
    "attendance banner", "mode tabs", "sub-card cta", "subcard cta",
    "participating", "calc callout",
)


def _norm(s) -> str:
    return (s or "").strip().lower()


def _check(bp: dict, ctx: dict) -> Iterable[Violation]:
    st = _norm(bp.get("_screenType") or bp.get("screenType"))
    if st not in _MODAL_TYPES:
        return []

    allow = {_norm(x) for x in (bp.get("_modalAllowSections") or [])}
    out: List[Violation] = []
    seen_forbidden = set()
    seen_home = set()

    for node, path in walk_blueprint(bp):
        if node is bp:
            continue
        name = _norm(node.get("name"))
        if not name:
            continue
        # 절대 금지 (Tab Bar / FAB / Footer)
        for kw in _FORBIDDEN:
            if kw in name and kw not in seen_forbidden and name not in allow:
                seen_forbidden.add(kw)
                out.append(Violation(
                    "R58.1-modal-forbidden-section", Severity.ERROR, path,
                    f"modal/bottom-sheet 에 '{node.get('name')}' 금지 — 절대 규칙 0-D "
                    f"(모달은 X 닫기만; Tab Bar/FAB/Footer 없음). 와이어에 없는 홈 요소 "
                    f"제거. Build BLOCKED.",
                    Phase.LINT,
                ))
        # 홈 전용 섹션 (베이스 잘못 끌어옴)
        for kw in _HOME_ONLY:
            if kw in name and kw not in seen_home and name not in allow:
                seen_home.add(kw)
                out.append(Violation(
                    "R58.2-modal-home-section", Severity.ERROR, path,
                    f"modal 에 홈 대시보드 섹션 '{node.get('name')}' — 와이어에 없는 홈 "
                    f"요소를 unified 베이스에서 잘못 끌어온 것. 와이어에 실제 있으면 "
                    f"root._modalAllowSections 에 추가, 아니면 제거. Build BLOCKED.",
                    Phase.LINT,
                ))
    return out


register(Rule(
    rule_id="R58-modal-no-home-sections",
    title="Modal screens contain only wireframe content",
    description="modal/bottom-sheet must not carry Tab Bar/FAB/Footer or home-dashboard "
                "sections dragged in from a unified home base. Wireframe is truth.",
    check_blueprint_fn=_check,
))
