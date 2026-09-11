# -*- coding: utf-8 -*-
"""figma-design-agent — 안정적 기계 판독 에러 코드 (Astryx CLI 패턴 차용, 2026-07-08).

## 왜 코드인가
빌드 게이트/검증이 출력하는 사람용 메시지(한글 prose)는 표현을 다듬을 때마다 바뀐다.
에이전트(새 세션 Claude)나 스크립트가 그 문장을 파싱해 분기하면, 리워딩하는 순간 조용히
깨진다. **`code` 필드가 안정 계약이다 — prose 로 분기하지 말 것.**

## 계약 (append-only)
- 한 번 배포된 코드는 **의미가 절대 변하지 않고, 절대 삭제되지 않는다.** 메시지는 자유롭게 바뀐다.
- 네이밍: `ERR_<SUBJECT>[_<QUALIFIER>]`, SCREAMING_SNAKE_CASE.
- 새 하드 게이트를 추가하면: ① ERROR_CODES 에 코드 추가, ② 게이트 이슈 문자열 태그
  (`"ERROR (<TAG>): ..."`)를 GATE_TAG_TO_CODE 에 등록.
  scripts/tests/test_error_codes.py 의 드리프트 가드가 미등록 태그를 CI 에서 잡는다.

소비처: cmd_build 끝의 BUILD-SUMMARY-JSON 블록(figma_mcp_client._emit_build_summary),
doctor --json 등.
"""
import re

# 코드 → 사람용 설명 (설명은 바뀔 수 있음 — 코드는 불변)
ERROR_CODES = {
    "ERR_UNKNOWN": "분류되지 않은 실패",
    "ERR_VALIDATION": "blueprint 구조 검증(validate_blueprint) ERROR",
    "ERR_PLANNING_GATE": "기획 digest 통독 게이트 미통과 — 빌드 차단 (준비 절차 5단계)",
    "ERR_REFERENCE_READ_PENDING": "레퍼런스 썸네일 미Read — 빌드 차단 (절대 규칙 0-G)",
    "ERR_SELF_VERIFY_PENDING": "직전 빌드 self-verify 미완료 — build/cleanup-qa 차단 (절대 규칙 0-F)",
    "ERR_ARCHETYPE_REUSE": "이전 빌드 config 콘텐츠 재사용 감지 (S22, 절대 규칙 0-E)",
    "ERR_WIREFRAME_CONTENT_MISSING": "root._wireframeContent dict 누락 (S23, 절대 규칙 0-E)",
    "ERR_CONCEPT_MISSING": "root._concept 선언 누락/공허 (S24 컨셉 게이트)",
    "ERR_DESIGN_DIRECTION_MISSING": "root._designDirection 선언 누락/불충분 (S25 디자인 방향 게이트)",
    "ERR_WIREFRAME_DIVERGENCE_MISSING": "root._wireframeDivergence 선언 누락 (S26 와이어 트레이싱 차단)",
    "ERR_RESTRUCTURE_MAP_MISSING": "root._restructureMap 선언 누락/불충분 (S27 재구성 맵 게이트)",
    "ERR_NOVELTY_DUPLICATE": "직전 빌드와 비주얼 시그니처/방향 동일 (novelty 게이트)",
    "ERR_MODAL_HOME_SECTIONS": "modal 에 홈 대시보드 섹션 유입 (R58)",
    "ERR_RULE_LINT": "design_rules L2 lint ERROR (개별 코드 미부여 룰)",
    "ERR_BUILD_FAILED": "batch_build_screen 실패 — root 노드 미생성",
    "ERR_ICON_UNRESOLVED": "type:'icon' 해석 실패 — icon-missing:* placeholder 잔존 (svg_icon 교체 필요, 2026-09-04)",
    "ERR_EXISTING_DESIGN_UNREVIEWED": "현재 페이지에 같은 화면이 있는데 검토/결정 선언 없음 — 빌드 차단 (규칙 0-G-3, 2026-09-11)",
}

# 게이트/룰 태그 → 코드. 이슈 문자열 "ERROR (<TAG>): ..." 의 <TAG> 를 매핑한다.
# 룰 id 는 "R58-modal-no-home-sections" 처럼 접미사가 붙으므로 base 태그("R58")로도 조회.
GATE_TAG_TO_CODE = {
    "S22": "ERR_ARCHETYPE_REUSE",
    "S23": "ERR_WIREFRAME_CONTENT_MISSING",
    "S24": "ERR_CONCEPT_MISSING",
    "S25": "ERR_DESIGN_DIRECTION_MISSING",
    "S26": "ERR_WIREFRAME_DIVERGENCE_MISSING",
    "S27": "ERR_RESTRUCTURE_MAP_MISSING",
    "novelty-gate": "ERR_NOVELTY_DUPLICATE",
    "R58": "ERR_MODAL_HOME_SECTIONS",
    "0-G-3": "ERR_EXISTING_DESIGN_UNREVIEWED",
}

_TAG_RE = re.compile(r"^ERROR\s*\(([^)]+)\)")


def classify_issue(issue: str) -> str:
    """이슈 문자열 1건 → 안정 에러 코드.

    "ERROR (S23): ..." → ERR_WIREFRAME_CONTENT_MISSING
    "ERROR (R58-modal-no-home-sections): ..." → ERR_MODAL_HOME_SECTIONS (base 태그 매칭)
    "ERROR (R60-...): ..." → ERR_RULE_LINT (개별 코드 미부여 룰)
    "ERROR: root fill ..." (태그 없음) → ERR_VALIDATION
    """
    m = _TAG_RE.match((issue or "").strip())
    if not m:
        return "ERR_VALIDATION"
    tag = m.group(1).strip()
    if tag in GATE_TAG_TO_CODE:
        return GATE_TAG_TO_CODE[tag]
    base = tag.split("-")[0]
    if base in GATE_TAG_TO_CODE:
        return GATE_TAG_TO_CODE[base]
    return "ERR_RULE_LINT"


def codes_for_issues(issues) -> list:
    """이슈 목록 → 중복 제거된 코드 목록 (첫 등장 순서 유지)."""
    seen, out = set(), []
    for i in issues or []:
        c = classify_issue(i)
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out
