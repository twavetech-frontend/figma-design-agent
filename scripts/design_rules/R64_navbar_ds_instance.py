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
  • `_customNavBar: "<사유>"` 마커 — 검색바 등 특수 navbar 는 author 의도 존중
  • modal/bottom-sheet 화면 (`_screenType`) — X-only 헤더는 별도 패턴 (2-D)
  • 로고도 back 도 없는 navbar — 의도 불명, WARN 만 (파괴적 swap 회피)

🔴 2026-08-04 사용자 룰 ("왜 tool bar instance 안 쓰고 일반 프레임으로 만든거야"):
  x-close 모달 헤더도 **제외 대상 아님** — Tool Bar 는 View=modal variant +
  Back/Title/Num BOOLEAN prop 으로 X-only 헤더를 표현할 수 있다 (실물 검증 2026-08-04).
  _classify 가 'modal' 로 분류 → inject 가 _navModal 마커로 swap,
  _configure_tool_bar 가 View=modal flip + Title/Back/Num off + x-close 아이콘 적용.
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


def _extract_right_icons(navbar: dict) -> list:
    """navbar 안 우측 액션 아이콘 이름 수집 (back/x-close 제외, 좌→우 순서).

    🔴 우측 버튼 개수 = Right Buttons `Type` variant (2026-06-12 사용자 룰):
    빈 리스트([]) = "empty"(버튼 없음), 1개 = "1 button", 2개 = "2 button" (최대 2).
    이 리스트가 `_navIcons` 마커가 되어 빌드 후 `_swap_tool_bar_icons` 가 variant
    flip + 중첩 아이콘 swap 한다. 와이어에 우측 아이콘이 없으면 빈 리스트 → empty
    (마스터 기본 버튼을 마음대로 남기지 않는다 — 와이어 1:1)."""
    icons = []
    for d in _iter_descendants(navbar):
        if (d.get("type") or "").lower() not in ("icon", "svg_icon"):
            continue
        ic = (d.get("iconName") or "").lower()
        if not ic:
            continue
        if any(a in ic for a in _BACK_ICON_HINTS):
            continue
        if any(x in ic for x in _XCLOSE_HINTS):
            continue
        icons.append(d.get("iconName"))
    return icons[:2]


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
    """swap 대상 분류 → ('home'|'detail'|'modal'|None, title)."""
    if _has_xclose(navbar):
        # 🔴 2026-08-04 사용자 룰: X 헤더도 Tool Bar 인스턴스 (View=modal variant)
        return "modal", _extract_title(navbar)
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
    # 🔴 2026-07-14 (사용자: "왜 NavBar 를 인스턴스 안 쓰고 직접 만드냐 — 규칙/코드에 박아뒀는데"):
    # _customNavBar 는 다른 bypass 와 달리 boolean 만으로 뚫리던 유일한 탈출구였다.
    # ① 사유 문자열 필수 (boolean true → ERROR)
    # ② '아이콘이 없다'류 사유 거부 — 미지원 아이콘은 우회 사유가 아니라 NAV_ICON_KEYS
    #    확장 대상 (search_design_system 으로 키 확보 → ds_catalog 등록).
    for node, path in walk_blueprint(bp):
        cnb = node.get("_customNavBar") if isinstance(node, dict) else None
        if cnb is None:
            continue
        if not isinstance(cnb, str) or len(cnb.strip()) < 5:
            yield Violation(
                "R64-custom-navbar-reason", Severity.ERROR, path,
                ("_customNavBar 는 boolean 금지 — 사유 문자열 필수 "
                 "(예: '검색바 내장 헤더 — Tool Bar variant 로 표현 불가'). "
                 "우측 아이콘이 NAV_ICON_KEYS 에 없다는 이유라면 우회가 아니라 "
                 "search_design_system 으로 키를 확보해 ds_catalog.NAV_ICON_KEYS 에 "
                 "등록할 것 (2026-07-14 사용자 룰)."),
                Phase.LINT,
            )
        elif any(k in cnb for k in ("아이콘", "icon", "키가 없", "키맵", "NAV_ICON")):
            yield Violation(
                "R64-custom-navbar-reason", Severity.ERROR, path,
                (f"_customNavBar 사유('{cnb[:40]}')가 아이콘 미지원 — 이는 우회 사유가 "
                 "아니다. search_design_system 으로 아이콘 키를 확보해 "
                 "ds_catalog.NAV_ICON_KEYS 에 등록하고 Tool Bar 인스턴스를 쓸 것."),
                Phase.LINT,
            )
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
                right_icons = _extract_right_icons(n)
                n["type"] = "instance"
                n["componentKey"] = _TOOLBAR_HOME_KEY if kind == "home" else _TOOLBAR_DETAIL_KEY
                n["_dsResolvedRole"] = ("Tool Bar View=modal" if kind == "modal" else
                                        f"Tool Bar Type={'Home' if kind == 'home' else 'Detail view'}")
                if kind == "modal":
                    # 🔴 2026-08-04: X 헤더 = View=modal variant (+Title/Back/Num off는
                    # _configure_tool_bar 가 처리). X 는 우측 1버튼 x-close 로 유지.
                    n["_navModal"] = True
                    if not right_icons:
                        right_icons = ["x-close"]
                if title:
                    n["_navTitle"] = title
                # 빈 리스트도 명시적으로 박는다 — 와이어에 우측 아이콘 없음 = Type=empty
                n["_navIcons"] = right_icons
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
