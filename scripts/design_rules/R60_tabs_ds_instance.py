"""R60 — 콘텐츠/뷰 전환 탭(2+ 텍스트 탭)은 underline tabs 가 기본, Segmented_control 은 명시적 토글만 (2026-06-01 박힘 / 2026-06-12 전면 개편).

사용자 명시(2026-06-01): *"상단에 tabs 메 '거래현황', '누적거래' 2 tabs가 있는데
tabs component가 사용되지 않았다. 새 세션에서 생성했을때 또 지금과 같은 컴포넌트를
사용하지 않는 일이 없어야 된다."*

🔴 2026-06-12 사용자 룰 (전면 개편): *"지금 화면에 내에서 tabs 컴포넌트로 쓰여야할
ui들이 segmented control로 쓰여지고 있어서. 그거 규칙 수정하고 코드도 수정해야한다.
예를들어 내가 지금 피그마에서 선택한 노드들이 그러해."* (입금/지급 'View Tabs' 가
Segmented_control 인스턴스로 빌드된 것을 가리킴)

**판별 기준 (tabs vs segmented control):**
  • **underline tabs (기본)** — 콘텐츠/뷰를 전환하는 네비게이션 탭. 라벨이 보여줄
    내용·카테고리(입금/지급, 추천/전체, 거래현황/누적거래, 후기/문의 등). 이름에
    'tab(s)' 포함하거나 화면/카드의 뷰를 바꾸는 모든 멀티옵션 텍스트 컨트롤.
    → **이게 디폴트.** styled raw frame(라벨 + active 밑줄 bar)로 표현.
  • **Segmented_control (예외)** — 같은 뷰 안의 컴팩트 on/off 토글·필터(주/월/년 등).
    오직 노드에 `_forceSegmented: true` 마커가 있을 때만. (0-V 사용자 룰)

원인 (과거 분석): blueprint 작성자/생성기가 입금·지급 같은 뷰 전환 탭을
`_segLabels`(Segmented_control) 로 작성 → 컴팩트 토글처럼 보임.

수정 (4중 방어):
  L2 lint   — raw tab-nav frame / `_segLabels` 뷰탭 마커(non-forced) 발견 시 WARN
  L3 inject — **underline tabs styled frame 으로 변환** (라벨 + active 밑줄 bar).
              raw frame 의 cell 라벨 추출 또는 `_segLabels` 라벨 사용. `_forceSegmented`
              면 변환 안 함(Segmented_control 유지).
  L4 post-fix — (no-op) underline tabs 는 frame 으로 직접 생성되므로 텍스트 매핑 불필요.
  L5 verify — raw tab-nav frame 이 underline 처리 안 된 채 남으면 WARN.

스코프 (탭 nav 로 인식되는 패턴):
  • name 이 "tabs wrap" / "tabs row" / "mode tabs" / "section tabs" / "top tabs" /
    "page tabs" / "underline tabs" / "view tab(s)" 포함
  • AND HORIZONTAL auto-layout, children 2~6개, 각 child 가 'tab cell'(TEXT 만, icon 없음)
  • 또는 `_segLabels` 마커(2+ 라벨)를 가진 노드 — `_forceSegmented` 아니면 변환
"""
from __future__ import annotations

from typing import Iterable, List, Tuple

from .base import Phase, Rule, Severity, Violation, register, walk_blueprint, walk_tree


# 🔴 2026-06-02 DS v7 → Imin Design System 마이그레이션. 'Segmented_control'
# (component_set 143ee3e3…). 단, 2026-06-12 부로 탭 nav 는 Segmented 가 아니라
# underline tabs(styled frame)가 기본 — Segmented_control 은 `_forceSegmented` 토글만.
_SEGMENTED_CONTROL_KEY = "143ee3e3fdd529c89c4360e3d70a583be4a83f53"
# Segmented_control 컴포넌트 키들 (componentKey 만으로 seg 인스턴스 식별용)
_SEG_COMPONENT_KEYS = {
    "47a01673a46dc3bc9bfd62948c10e5fa9f2e5e78",  # Style=hug
    "2ee9d12d4c904650ab496b9bcdf874a648e73ceb",  # Style=fill
    "143ee3e3fdd529c89c4360e3d70a583be4a83f53",  # set
}

# underline tabs 색/사이즈 (gen_stage_recommend 의 _utab 패턴과 동일)
_TAB_ACTIVE_TEXT = "$token(text-primary)"
_TAB_INACTIVE_TEXT = "$token(text-tertiary)"
_TAB_UNDERLINE_FILL = "$token(fg-primary)"
_TAB_DEFAULT_FONT_SIZE = 16  # DS Body md 스케일(바인딩 가능). 페이지 상단 탭은 _tabFontSize 로 키움

# Tab nav wrapper name patterns (case-insensitive)
_TAB_NAV_HINTS = (
    "mode tabs", "section tabs", "top tabs", "page tabs",
    "underline tabs", "tabs wrap", "tabs row", "view tabs", "view tab",
)


# ── Detection ─────────────────────────────────────────────────────

def _count_text_descendants(node: dict) -> int:
    if not isinstance(node, dict): return 0
    n = 1 if (node.get("type") or "").lower() == "text" else 0
    for c in node.get("children") or []:
        n += _count_text_descendants(c)
    return n


def _count_icon_descendants(node: dict) -> int:
    if not isinstance(node, dict): return 0
    t = (node.get("type") or "").lower()
    n = 1 if t in ("icon", "svg_icon", "vector") else 0
    for c in node.get("children") or []:
        n += _count_icon_descendants(c)
    return n


def _is_tab_cell(node: dict) -> bool:
    """tab cell = frame with exactly 1 TEXT descendant, no icons."""
    if not isinstance(node, dict): return False
    if (node.get("type") or "").lower() != "frame": return False
    return _count_text_descendants(node) == 1 and _count_icon_descendants(node) == 0


def _is_tab_nav_wrapper(node: dict) -> bool:
    if not isinstance(node, dict): return False
    # 🔴 2026-06-09 사용자 룰: 텍스트가 크게 보여야 하는 탭은 underline tabs(styled)로 둔다.
    # 이미 underline 으로 작성됐으면(또는 명시 Segmented 토글이면) 그대로 둠.
    if node.get("_underlineTabs") or node.get("_forceSegmented"):
        return False
    name = (node.get("name") or "").lower().strip()
    if not any(h in name for h in _TAB_NAV_HINTS):
        return False
    al = node.get("autoLayout") or {}
    if (al.get("layoutMode") or node.get("layoutMode")) != "HORIZONTAL":
        return False
    kids = node.get("children") or []
    if not (2 <= len(kids) <= 6):
        return False
    return all(_is_tab_cell(c) for c in kids)


def _seg_marker_labels(node: dict) -> list:
    """노드가 'Segmented_control 로 작성된 뷰 전환 탭' 이면 라벨 리스트 반환, 아니면 [].

    🔴 2026-06-12 사용자 룰: 입금/지급 같은 뷰 전환 탭이 `_segLabels`(Segmented_control)
    로 작성돼 컴팩트 토글처럼 보이던 문제 → underline tabs 로 변환 대상.
    `_forceSegmented: true` 면 의도된 컴팩트 토글이므로 변환 안 함([]).
    """
    if not isinstance(node, dict):
        return []
    if node.get("_forceSegmented") or node.get("_underlineTabs"):
        return []
    seg = node.get("_segLabels")
    if isinstance(seg, list) and len([s for s in seg if s]) >= 2:
        return [str(s) for s in seg if s]
    return []


def _underline_tab_cell(label: str, active: bool, font_size: int) -> dict:
    """gen_stage_recommend 의 _utab 와 동일한 underline 탭 cell."""
    return {
        "name": "Tab " + label,
        "type": "frame",
        "layoutSizingHorizontal": "HUG",
        "autoLayout": {"layoutMode": "VERTICAL", "itemSpacing": 7,
                       "counterAxisAlignItems": "CENTER"},
        "children": [
            {"type": "text", "text": label, "fontSize": font_size,
             "fontName": {"family": "Pretendard", "style": "Bold"},
             "fontColor": _TAB_ACTIVE_TEXT if active else _TAB_INACTIVE_TEXT},
            {"name": "Tab Underline " + label, "type": "frame",
             "layoutSizingHorizontal": "FILL", "layoutSizingVertical": "FIXED",
             "height": 3, "cornerRadius": 999,
             "fill": (_TAB_UNDERLINE_FILL if active else None)},
        ],
    }


def _to_underline_tabs(node: dict, labels: list, active_idx: int, font_size: int) -> None:
    """node 를 in-place 로 underline tabs styled frame 으로 변환.

    Segmented_control 인스턴스/raw tab-nav frame 양쪽을 동일한 underline 구조로 통일.
    """
    name = node.get("name") or "View Tabs"
    # 인스턴스/세그먼트/raw-tab 잔재 필드 제거
    for k in ("componentKey", "_segLabels", "_segActive", "_originalChildren",
              "_dsResolvedRole", "_tabLabels", "_tabActiveIndex", "_tabSize",
              "properties", "instanceProperties", "_instanceVariants",
              "componentProperties", "_instanceText",
              "fill", "fills", "stroke", "strokes", "strokeWeight",
              "strokeTopWeight", "strokeBottomWeight",
              "strokeLeftWeight", "strokeRightWeight", "cornerRadius",
              "padding", "paddingTop", "paddingBottom",
              "paddingLeft", "paddingRight", "layoutMode"):
        node.pop(k, None)
    node["type"] = "frame"
    node["name"] = name
    node["_underlineTabs"] = True
    node["layoutSizingHorizontal"] = "HUG"
    node["autoLayout"] = {"layoutMode": "HORIZONTAL", "itemSpacing": 18,
                          "counterAxisAlignItems": "MIN"}
    if active_idx < 0 or active_idx >= len(labels):
        active_idx = 0
    node["children"] = [
        _underline_tab_cell(lab, i == active_idx, font_size)
        for i, lab in enumerate(labels)
    ]


def _extract_text_label(cell: dict) -> str | None:
    """tab cell 내의 단일 TEXT 노드 라벨 추출."""
    def _find_text(n):
        if not isinstance(n, dict): return None
        if (n.get("type") or "").lower() == "text":
            return n.get("text") or n.get("characters")
        for c in n.get("children") or []:
            r = _find_text(c)
            if r: return r
        return None
    return _find_text(cell)


def _detect_active_index(kids: list) -> int:
    for i, c in enumerate(kids):
        name = (c.get("name") or "").lower()
        if "active" in name or "(selected)" in name or "[selected]" in name:
            return i
    return 0  # default first tab active


# ── L2 lint (blueprint) ───────────────────────────────────────────

def _check_blueprint(bp: dict, ctx: dict) -> Iterable[Violation]:
    for node, path in walk_blueprint(bp):
        if _is_tab_nav_wrapper(node) and (node.get("type") or "frame").lower() == "frame":
            kids = node.get("children") or []
            labels = [_extract_text_label(c) or "?" for c in kids]
            yield Violation(
                "R60-tabs-ds-instance",
                Severity.WARN,
                path,
                (f"tab nav '{node.get('name')}' with {len(kids)} cells "
                 f"({labels}) is a raw frame — inject will style it as underline tabs."),
                Phase.LINT,
            )
        seg_labels = _seg_marker_labels(node)
        if seg_labels:
            yield Violation(
                "R60-tabs-ds-instance",
                Severity.WARN,
                path,
                (f"'{node.get('name')}' is a Segmented_control 뷰 전환 탭 "
                 f"({seg_labels}) — 콘텐츠/뷰 전환 탭은 underline tabs 가 기본. "
                 f"inject 가 underline tabs 로 변환. (컴팩트 토글이면 _forceSegmented:true)"),
                Phase.LINT,
            )


# ── L3 inject (blueprint) ─────────────────────────────────────────

def _inject(bp: dict) -> dict:
    """탭 nav 를 underline tabs styled frame 으로 변환 (2026-06-12 개편).

    두 경로:
      1. raw tab-nav frame (이름 힌트 + 텍스트 cell) → underline tabs
      2. `_segLabels`(Segmented_control) 뷰 전환 탭 → underline tabs
         (단 `_forceSegmented:true` 면 변환 안 함 — 컴팩트 토글 유지)
    """
    from_frame = 0
    from_seg = 0

    def _walk(n):
        nonlocal from_frame, from_seg
        if not isinstance(n, dict): return
        # 경로 2: Segmented_control 뷰 전환 탭 → underline
        seg_labels = _seg_marker_labels(n)
        if seg_labels:
            active = n.get("_segActive", 0) or 0
            fs = n.get("_tabFontSize") or _TAB_DEFAULT_FONT_SIZE
            _to_underline_tabs(n, seg_labels, active, fs)
            from_seg += 1
            return  # 변환된 children(밑줄 bar 등)으로 재귀 안 함
        # 경로 1: raw tab-nav frame → underline
        if _is_tab_nav_wrapper(n) and (n.get("type") or "frame").lower() == "frame":
            kids = n.get("children") or []
            labels = [_extract_text_label(c) or "" for c in kids]
            active_idx = _detect_active_index(kids)
            # font size — 첫 cell 텍스트 크기 유지(없으면 기본). 페이지 상단 탭은 _tabFontSize.
            fs = n.get("_tabFontSize")
            if not fs:
                for c in kids:
                    def _ft(x):
                        if not isinstance(x, dict): return None
                        if (x.get("type") or "").lower() == "text":
                            return x.get("fontSize")
                        for cc in x.get("children") or []:
                            r = _ft(cc)
                            if r: return r
                        return None
                    sz = _ft(c)
                    if sz:
                        fs = sz
                        break
            fs = fs or _TAB_DEFAULT_FONT_SIZE
            _to_underline_tabs(n, [l for l in labels if l] or labels, active_idx, fs)
            from_frame += 1
            return
        for c in n.get("children") or []:
            _walk(c)

    _walk(bp)
    if from_frame:
        print(f"[inject R60] raw tab-nav frame → underline tabs: {from_frame}건")
    if from_seg:
        print(f"[inject R60] Segmented_control 뷰 전환 탭 → underline tabs: {from_seg}건 "
              f"(컴팩트 토글은 _forceSegmented 로 유지)")
    return bp


# ── L4 post-fix (built tree) ──────────────────────────────────────

def _autofix(tree: dict, ctx: dict) -> int:
    """no-op — underline tabs 는 inject 에서 frame 으로 직접 생성되므로 텍스트 매핑 불필요.

    (구버전: Segmented_control 인스턴스 내부 TEXT 를 라벨로 매핑했으나, 이제 변환 단계에서
    라벨이 styled frame 의 TEXT 노드로 직접 들어간다.)
    """
    return 0


# ── L5 verify (built tree) ────────────────────────────────────────

def _verify(tree: dict, ctx: dict) -> Iterable[Violation]:
    """built tree 의 tab nav 가 underline 처리됐는지 확인 (WARN — 차단 안 함).

    Segmented_control 인스턴스로 남았으면(뷰 전환 탭인데 변환 안 됨) WARN.
    """
    for node, path in walk_tree(tree):
        name = (node.get("name") or "").lower().strip()
        if not any(h in name for h in _TAB_NAV_HINTS):
            continue
        ntype = (node.get("type") or "").upper()
        # 인스턴스로 남았는데 _forceSegmented 의도가 아니면 변환 누락 가능성 — WARN
        if ntype == "INSTANCE":
            cp = node.get("componentProperties") or {}
            is_seg = ("segmented" in name) or any(
                str(k).startswith("Show Segment") for k in cp.keys())
            if is_seg:
                yield Violation(
                    "R60-tabs-ds-instance",
                    Severity.WARN,
                    path,
                    (f"뷰 전환 탭 '{node.get('name')}' 이 Segmented_control 인스턴스로 "
                     f"남음 — underline tabs 가 기본. 의도된 컴팩트 토글이면 무시."),
                    Phase.VERIFY,
                )


register(Rule(
    rule_id="R60-tabs-ds-instance",
    title="콘텐츠/뷰 전환 탭(2+ 텍스트 탭)은 underline tabs 가 기본 — Segmented_control 은 _forceSegmented 토글만",
    description=(
        "뷰/콘텐츠를 전환하는 멀티옵션 텍스트 탭(입금/지급, 추천/전체, 거래현황/누적거래 등)은 "
        "underline tabs styled frame(라벨 + active 밑줄 bar)이 기본. raw tab-nav frame 과 "
        "`_segLabels`(Segmented_control) 뷰 전환 탭을 inject 가 underline tabs 로 변환한다. "
        "Segmented_control 은 같은 뷰 안 컴팩트 on/off 토글에만, `_forceSegmented:true` 명시 시."
    ),
    check_blueprint_fn=_check_blueprint,
    inject_blueprint_fn=_inject,
    auto_fix_built_fn=_autofix,
    check_built_fn=_verify,
))
