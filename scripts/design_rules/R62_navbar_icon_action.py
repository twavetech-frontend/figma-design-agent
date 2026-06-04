"""R62 — 상단 NavBar 우측 액션은 텍스트가 아니라 아이콘 버튼 (2026-06-04 사용자 룰).

사용자 명시: *"상단 네비게이션바 우측에 일반적으로 아이콘 버튼이 위치하는데 지금처럼
텍스트 버튼이 들어가면 안되. 아주 특수한 경우에만 텍스트 버튼을 사용할거야."*

→ NavBar(상단 네비게이션) 우측의 액션 라벨(공유/완료/편집/저장/닫기 등)은 아이콘으로
   바꾼다. **아주 특수한 경우**(매핑에 없는 라벨, 또는 `_navTextAllowed:true` 마커)만 텍스트 유지.

설계 — 보수적 (오탐 방지):
  • 액션 라벨 → 아이콘 매핑(_ACTION_ICON)에 **정확히 일치**하는 TEXT 만 변환.
    제목("도토리 1만 들어오세요." 등)은 매핑에 없으니 그대로 둔다 → 안전.
  • NavBar 판정: ancestor/자기 이름에 navbar/nav bar/app bar/top bar/header 포함 HORIZONTAL frame.
  • L3 inject 에서 TEXT 노드 dict 를 ICON 노드 dict 로 **교체** (build 가 svg_icon 생성).
  • 텍스트 유지 예외: 노드에 `_navTextAllowed: true` 가 있으면 변환 안 함.
"""
from __future__ import annotations

from typing import Iterable

from .base import Phase, Rule, Severity, Violation, register


# 액션 라벨(소문자/공백제거) → Untitled UI 아이콘 이름
_ACTION_ICON = {
    "공유": "share-07", "share": "share-07",
    "완료": "check", "확인": "check", "저장": "check", "등록": "check", "적용": "check",
    "done": "check", "save": "check",
    "편집": "edit-02", "수정": "edit-02", "edit": "edit-02",
    "닫기": "x-close", "취소": "x-close", "close": "x-close", "cancel": "x-close",
    "다음": "arrow-right", "next": "arrow-right",
    "더보기": "dots-vertical", "more": "dots-vertical",
    "검색": "search-lg", "search": "search-lg",
    "알림": "bell-01", "삭제": "trash-01", "필터": "filter-lines",
    "설정": "settings-01",
}

_NAVBAR_NAME_HINTS = ("navbar", "nav bar", "app bar", "appbar", "top bar",
                      "topbar", "header bar", "nav header")


def _norm(s) -> str:
    return (str(s or "")).strip().lower().replace(" ", "")


def _is_navbar(node: dict) -> bool:
    name = (node.get("name") or "").lower()
    al = node.get("autoLayout") or {}
    mode = al.get("layoutMode") or node.get("layoutMode")
    if mode and mode != "HORIZONTAL":
        return False
    return any(h in name for h in _NAVBAR_NAME_HINTS) or name == "navbar"


def _action_icon_for(node: dict) -> str | None:
    """TEXT 노드가 알려진 액션 라벨이면 아이콘 이름, 아니면 None."""
    if (node.get("type") or "").lower() != "text":
        return None
    if node.get("_navTextAllowed"):  # 특수 케이스 — 텍스트 유지
        return None
    chars = node.get("characters")
    return _ACTION_ICON.get(_norm(chars))


def _icon_node_from_text(text_node: dict, icon_name: str) -> dict:
    """TEXT 노드를 대체할 ICON 노드 dict 생성. 색은 navbar 액션 표준 fg-primary."""
    label = str(text_node.get("characters") or "action").strip()
    return {
        "type": "icon",
        "iconName": icon_name,
        "size": 24,
        "iconColor": "$token(fg-primary)",
        "name": f"{label} Icon",
    }


def _navbar_action_texts(bp: dict):
    """(parent, index, text_node, icon_name) 목록 — navbar 안 액션 라벨 TEXT."""
    results = []

    def _walk(n, ancestors):
        if not isinstance(n, dict):
            return
        in_navbar = any(_is_navbar(a) for a in ancestors) or _is_navbar(n)
        if in_navbar:
            for i, c in enumerate(n.get("children") or []):
                ic = _action_icon_for(c)
                if ic:
                    results.append((n, i, c, ic))
        new_anc = ancestors + [n]
        for c in n.get("children") or []:
            _walk(c, new_anc)

    _walk(bp, [])
    return results


# ── L2 lint (blueprint) ───────────────────────────────────────────

def _check_blueprint(bp: dict, ctx: dict) -> Iterable[Violation]:
    for parent, idx, tnode, icon in _navbar_action_texts(bp):
        yield Violation(
            "R62-navbar-icon-action",
            Severity.WARN,
            f"{parent.get('name','?')}/{tnode.get('characters','?')}",
            (f"NavBar 우측 액션 '{tnode.get('characters')}' 가 텍스트 버튼 — "
             f"아이콘('{icon}')이어야 한다. inject 가 교체. "
             f"(특수 케이스면 노드에 _navTextAllowed:true)"),
            Phase.LINT,
        )


# ── L3 inject (blueprint) ─────────────────────────────────────────

def _inject(bp: dict) -> dict:
    swaps = _navbar_action_texts(bp)
    if not swaps:
        return bp
    n = 0
    for parent, idx, tnode, icon in swaps:
        kids = parent.get("children") or []
        if 0 <= idx < len(kids) and kids[idx] is tnode:
            kids[idx] = _icon_node_from_text(tnode, icon)
            n += 1
    if n:
        print(f"  ✓ R62 inject: NavBar 우측 텍스트 액션 → 아이콘 {n}건")
    return bp


# ── L5 verify (built tree) ────────────────────────────────────────

def _verify(tree: dict, ctx: dict) -> Iterable[Violation]:
    def _walk(n, ancestors):
        if not isinstance(n, dict):
            return
        in_navbar = any(_is_navbar(a) for a in ancestors) or _is_navbar(n)
        if in_navbar and (n.get("type") or "").lower() == "text":
            if _norm(n.get("characters")) in _ACTION_ICON and not n.get("_navTextAllowed"):
                yield Violation(
                    "R62-navbar-icon-action",
                    Severity.WARN,
                    f"…/{n.get('name')}",
                    (f"NavBar 액션 '{n.get('characters')}' 가 여전히 텍스트 — "
                     f"아이콘이어야 한다"),
                    Phase.VERIFY,
                )
        new_anc = ancestors + [n]
        for c in n.get("_children_full") or n.get("children") or []:
            yield from _walk(c, new_anc)

    yield from _walk(tree, [])


register(Rule(
    rule_id="R62-navbar-icon-action",
    title="NavBar 우측 액션은 아이콘 버튼 (텍스트는 특수 케이스만)",
    description=(
        "상단 NavBar 우측의 액션 라벨(공유/완료/편집/저장/닫기 등)은 텍스트가 아니라 "
        "아이콘 버튼이어야 한다. 알려진 액션 라벨 → 아이콘 매핑으로 inject 단계에서 교체. "
        "매핑에 없는 라벨이나 _navTextAllowed:true 마커는 텍스트 유지(특수 케이스)."
    ),
    check_blueprint_fn=_check_blueprint,
    inject_blueprint_fn=_inject,
    check_built_fn=_verify,
))
