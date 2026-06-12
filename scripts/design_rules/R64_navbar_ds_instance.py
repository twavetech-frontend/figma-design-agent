"""R64 — 상단 툴바(NavBar)는 raw frame 금지, DS 'Tool Bar' 인스턴스 사용 강제 (2026-06-12 사용자 룰).

사용자 명시: *"상단 tool bar(네비게이션바)를 매번 새로 그리는게 아니라, 컴포넌트
인스턴스를 쓸 것! 메인과 서브 화면은 컴포넌트 props 옵션을 선택해서 사용하는걸로"*

Imin DS 'Tool Bar' 컴포넌트 셋 (https://…?node-id=17677-1332, set key c9299ef0…):
  • Type=Home        — 메인/탭바 홈: 로고 + 우측 아이콘 버튼 2개
  • Type=Detail view — 서브 화면: back 버튼 + 중앙 타이틀 + 우측 아이콘 버튼

variant 개별 키가 비공개(셋만 게시)라 componentKey 는 "SET:<setKey>:<Variant>" 형식
— code.js `importComponentFlexible` 가 importComponentSetByKeyAsync 로 셋을 import 후
variant 이름("Type=Home")을 prop 단위로 매칭해 인스턴스를 만든다.

3중 방어:
  L2 lint   — raw NavBar frame 발견 시 WARN (swap 예고)
  L3 inject — 빌드 직전 자동 swap:
              · 로고 자식 있음(back 없음) → Type=Home
              · back 버튼 자식 있음     → Type=Detail view + `_navTitle`(타이틀 텍스트) 마커
              실제 타이틀 적용은 cmd_post_fix 의 `_configure_tool_bar` 가 빌드된 인스턴스
              내부 TEXT 를 scan_text_nodes 로 찾아 set_text_content (R60/seg-tabs 패턴).
  L5 verify — 빌드 후에도 NavBar 가 FRAME 으로 남아 있으면 WARN.

스코프 제외 (swap 안 함):
  • `_customNavBar: true` 마커 — 검색바 등 특수 navbar 는 author 의도 존중
  • modal/bottom-sheet 화면 (`_screenType`) — X-only 헤더는 별도 패턴 (2-D)
  • x-close 아이콘만 든 navbar — modal 헤더
  • 로고도 back 도 없는 navbar — 의도 불명, WARN 만 (파괴적 swap 회피)
"""
from __future__ import annotations

from typing import Iterable

from .base import Phase, Rule, Severity, Violation, register, walk_blueprint, walk_tree
from .ds_catalog import COMPONENT_KEYS

_TOOLBAR_HOME_KEY = COMPONENT_KEYS["Tool Bar Home"]
_TOOLBAR_DETAIL_KEY = COMPONENT_KEYS["Tool Bar Detail"]
_TOOLBAR_SET_PREFIX = "SET:c9299ef0c3c7cc271850a048025a3c8d0e82b230"

# figma_mcp_client._NAVBAR_NAME_HINTS 와 동일 (rule 모듈은 client 를 import 못해 복제)
_NAVBAR_NAME_HINTS = ("navbar", "nav bar", "app bar", "appbar", "top bar",
                      "topbar", "header bar", "nav header")

_BACK_ICON_HINTS = ("chevron-left", "arrow-left", "arrow-narrow-left",
                    "arrow-circle-left", "caret-left", "chevron-circle-left")
_XCLOSE_HINTS = ("x-close", "x close", "xclose", "close")


def _iter_descendants(node: dict):
    for c in node.get("children") or []:
        if isinstance(c, dict):
            yield c
            yield from _iter_descendants(c)


def _has_logo(navbar: dict) -> bool:
    for d in _iter_descendants(navbar):
        if "logo" in (d.get("name") or "").lower():
            return True
    return False


def _has_back(navbar: dict) -> bool:
    for d in _iter_descendants(navbar):
        nm = (d.get("name") or "").lower()
        ic = (d.get("iconName") or "").lower()
        if any(w in nm for w in ("back", "뒤로")):
            return True
        if any(a in nm for a in _BACK_ICON_HINTS) or any(a in ic for a in _BACK_ICON_HINTS):
            return True
    return False


def _has_xclose(navbar: dict) -> bool:
    for d in _iter_descendants(navbar):
        nm = (d.get("name") or "").lower()
        ic = (d.get("iconName") or "").lower()
        if any(x in ic for x in _XCLOSE_HINTS) or "x-close" in nm:
            return True
    return False


def _extract_title(navbar: dict):
    """navbar 안 첫 TEXT 노드의 내용 (Detail view 타이틀로 사용)."""
    for d in _iter_descendants(navbar):
        if (d.get("type") or "").lower() == "text":
            t = d.get("text") or d.get("characters")
            if t:
                return str(t)
    return None


def _is_navbar_frame(node: dict) -> bool:
    if not isinstance(node, dict):
        return False
    if (node.get("type") or "frame").lower() != "frame":
        return False
    if node.get("_customNavBar"):
        return False
    name = (node.get("name") or "").lower().strip()
    return any(h in name for h in _NAVBAR_NAME_HINTS)


def _classify(navbar: dict):
    """swap 대상 분류 → ('home'|'detail'|None, title)."""
    if _has_xclose(navbar):           # modal X-only 헤더 — 별도 패턴 (2-D)
        return None, None
    back = _has_back(navbar)
    if back:
        return "detail", _extract_title(navbar)
    if _has_logo(navbar):
        return "home", None
    return None, None


def _is_modal_screen(bp: dict) -> bool:
    st = (bp.get("_screenType") or "").lower()
    return st in ("modal", "bottom-sheet")


# ── L2 lint (blueprint) ───────────────────────────────────────────

def _check_blueprint(bp: dict, ctx: dict) -> Iterable[Violation]:
    if _is_modal_screen(bp):
        return
    for node, path in walk_blueprint(bp):
        if not _is_navbar_frame(node):
            continue
        kind, title = _classify(node)
        if kind:
            yield Violation(
                "R64-navbar-ds-instance",
                Severity.WARN,
                path,
                (f"NavBar '{node.get('name')}' is a raw frame — should be a DS "
                 f"'Tool Bar' instance (Type={'Home' if kind == 'home' else 'Detail view'}"
                 f"{', title=' + repr(title) if title else ''}). Inject will auto-swap."),
                Phase.LINT,
            )
        else:
            yield Violation(
                "R64-navbar-ds-instance",
                Severity.WARN,
                path,
                (f"NavBar '{node.get('name')}' is a raw frame with no logo/back "
                 f"hint — use a DS 'Tool Bar' instance directly, or mark "
                 f"_customNavBar:true if intentionally custom."),
                Phase.LINT,
            )


# ── L3 inject (blueprint) ─────────────────────────────────────────

def _inject(bp: dict) -> dict:
    """raw NavBar frame → DS 'Tool Bar' 인스턴스 (Type=Home / Type=Detail view).

    raw children 은 _originalChildren 으로 보존. Detail view 타이틀은 `_navTitle`
    마커로 저장 — cmd_post_fix 의 `_configure_tool_bar` 가 빌드된 인스턴스 내부
    TEXT 에 적용한다.
    """
    if _is_modal_screen(bp):
        return bp
    fixed = 0

    def _walk(n):
        nonlocal fixed
        if not isinstance(n, dict):
            return
        if _is_navbar_frame(n):
            kind, title = _classify(n)
            if kind:
                n["type"] = "instance"
                n["componentKey"] = _TOOLBAR_HOME_KEY if kind == "home" else _TOOLBAR_DETAIL_KEY
                n["_dsResolvedRole"] = f"Tool Bar Type={'Home' if kind == 'home' else 'Detail view'}"
                if title:
                    n["_navTitle"] = title
                n["_originalChildren"] = n.get("children") or []
                n.pop("children", None)
                # master 가 layout/fill/stroke 를 가지므로 wrapper 속성 제거
                for k in ("autoLayout", "layoutMode", "fill", "fills", "stroke",
                          "strokes", "strokeWeight", "strokeTopWeight",
                          "strokeBottomWeight", "strokeLeftWeight",
                          "strokeRightWeight", "padding", "paddingTop",
                          "paddingBottom", "paddingLeft", "paddingRight",
                          "height", "cornerRadius"):
                    n.pop(k, None)
                n["layoutSizingHorizontal"] = "FILL"
                fixed += 1
                return  # 인스턴스 안으로는 재귀 안 함
        for c in n.get("children") or []:
            _walk(c)

    _walk(bp)
    if fixed:
        print(f"[inject R64] NavBar raw frame → DS Tool Bar instance: {fixed}건")
    return bp


# ── L5 verify (built tree) ────────────────────────────────────────

def _verify(tree: dict, ctx: dict) -> Iterable[Violation]:
    bp = (ctx or {}).get("blueprint") or {}
    if _is_modal_screen(bp):
        return
    for node, path in walk_tree(tree):
        name = (node.get("name") or "").lower().strip()
        if not any(h in name for h in _NAVBAR_NAME_HINTS):
            continue
        ntype = (node.get("type") or "").upper()
        if ntype == "FRAME":
            yield Violation(
                "R64-navbar-ds-instance",
                Severity.WARN,
                path,
                (f"NavBar '{node.get('name')}' built as FRAME — should be an "
                 f"INSTANCE of DS 'Tool Bar' (Type=Home/Detail view) unless "
                 f"intentionally custom (_customNavBar)."),
                Phase.VERIFY,
            )


register(Rule(
    rule_id="R64-navbar-ds-instance",
    title="Top NavBar must be a DS 'Tool Bar' instance (Type=Home / Detail view), not a raw frame",
    description=(
        "Top navigation bars (name hints: navbar/nav bar/app bar/top bar/"
        "header bar) must use the Imin DS 'Tool Bar' component instance — "
        "Type=Home (logo + right icons) for main/tab-home screens, "
        "Type=Detail view (back + centered title + right icons) for sub "
        "screens. Inject auto-swaps raw frames; the title is applied "
        "post-build via the _navTitle marker. Opt-out: _customNavBar:true. "
        "Modal X-only headers are exempt (rule 2-D)."
    ),
    check_blueprint_fn=_check_blueprint,
    inject_blueprint_fn=_inject,
    check_built_fn=_verify,
))
