"""R60 — 2-tab 이상 텍스트 탭 nav 는 raw frame 금지, DS Horizontal Tabs instance 사용 강제 (2026-06-01 사용자 룰).

사용자 명시: *"상단에 tabs 메 '거래현황', '누적거래' 2 tabs가 있는데 tabs component가
사용되지 않았다. 왜 사용하지 않았는지 원인을 찾고 재발하지 않도록 문제 수정해.
새 세션에서 생성했을때 또 지금과 같은 컴포넌트를 사용하지 않는 일이 없어야 된다."*

원인 (분석 결과):
  1. DS 카탈로그에 'Underline Tab Item' (개별 탭 cell) 만 등록 — 전체 'Horizontal tabs'
     세트 키(setKey: f11bda3cf5430bdb7052591a5beead9d5abdf093) 누락 → resolve_component_key
     가 "Mode Tabs Wrap" / "Mode Tabs" 같은 이름을 매칭 못 함.
  2. R23 의 is_container() 가 'tabs' / 'wrap' suffix 를 container 로 분류 →
     R23 inject 가 자동 swap 대상에서 제외.
  3. blueprint 작성자(Claude)가 raw HORIZONTAL frame 으로 2개 tab cell 직접 작성.

수정 (3중 방어):
  L2 lint   — "Mode Tabs Wrap" / "Section Tabs" / "Top Tabs" 등 패턴의 raw frame 발견 시 WARN
  L3 inject — 자동으로 type:"instance" + componentKey 박기 + 라벨/active idx 메타 저장.
              raw children 은 _originalChildren 로 보존(라벨 매핑 위해).
  L4 post-fix — built instance 내부 TEXT 노드 findAll + 라벨 순서대로 set_text_content.
                active marker 가 있으면 variant property 'Selected' 도 적용 시도.
  L5 verify — built tree 의 동일 위치가 INSTANCE 가 아니면 ERROR.

스코프 (탭 nav wrapper 로 인식되는 패턴):
  • name 이 "tabs wrap" / "tabs row" / "mode tabs" / "section tabs" / "top tabs" /
    "page tabs" / "underline tabs" 끝나거나 정확히 포함
  • AND HORIZONTAL auto-layout
  • AND children 2~6개, 각 child 가 'tab cell' (TEXT descendant 만 있고 icon 없음)
"""
from __future__ import annotations

from typing import Iterable, List, Tuple

from .base import Phase, Rule, Severity, Violation, register, walk_blueprint, walk_tree


# 2026-06-01 — Horizontal Tabs Underline 컴포넌트 키 (Mobile, sm/md, Full/non-Full)
# setKey: f11bda3cf5430bdb7052591a5beead9d5abdf093
_TAB_KEYS = {
    ("underline", "sm", False): "6b613d270ba98d67c4a8d210721f332ab53fac0d",
    ("underline", "md", False): "3d2c0c82adc08b47904314fc1ce041efaf45d305",
    ("underline", "sm", True):  "9b76638ee31a8aa32e2be0b7030d4d4d03341453",
    ("underline", "md", True):  "e1bbacea93585cdafe0fdd348d28717d8d2f173b",
}

# Tab nav wrapper name patterns (case-insensitive)
_TAB_NAV_HINTS = (
    "mode tabs", "section tabs", "top tabs", "page tabs",
    "underline tabs", "tabs wrap", "tabs row",
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
            # not yet instance — flag
            kids = node.get("children") or []
            labels = [_extract_text_label(c) or "?" for c in kids]
            yield Violation(
                "R60-tabs-ds-instance",
                Severity.WARN,
                path,
                (f"tab nav '{node.get('name')}' with {len(kids)} cells "
                 f"({labels}) is a raw frame — should be a DS Horizontal Tabs "
                 f"instance (Underline). Inject will auto-swap."),
                Phase.LINT,
            )


# ── L3 inject (blueprint) ─────────────────────────────────────────

def _inject(bp: dict) -> dict:
    """tab nav wrapper raw frame → DS Horizontal Tabs Underline instance.

    raw children 은 _originalChildren 으로 보존, 라벨/active idx 는 메타로 저장.
    실제 텍스트 매핑은 post-fix 가 빌드된 instance 내부 TEXT 를 찾아서 적용.
    """
    fixed = 0

    def _walk(n):
        nonlocal fixed
        if not isinstance(n, dict): return
        if _is_tab_nav_wrapper(n) and (n.get("type") or "frame").lower() == "frame":
            kids = n.get("children") or []
            labels = [_extract_text_label(c) or "" for c in kids]
            active_idx = _detect_active_index(kids)

            # Full-width 여부 — 모든 tab cell 이 FILL 이면 full=True, 아니면 False.
            # Project canonical: 거래스케줄/홈에선 좌측 좁게 모인 형태(Full=False).
            full_width = all(
                (c.get("layoutSizingHorizontal") or "").upper() == "FILL"
                for c in kids
            )
            # Size — sm 이 mobile 표준. md 는 size prop hint 가 있을 때만.
            size = "md" if n.get("_tabSize") == "md" else "sm"
            key = _TAB_KEYS[("underline", size, full_width)]

            # In-place swap: keep name + parent context, replace structure
            n["type"] = "instance"
            n["componentKey"] = key
            n["_dsResolvedRole"] = (
                f"Horizontal Tabs Underline {size} "
                f"{'Full ' if full_width else ''}Mobile"
            )
            n["_tabLabels"] = labels
            n["_tabActiveIndex"] = active_idx
            # raw children → _originalChildren (라벨 추적 + post-fix 매핑용)
            n["_originalChildren"] = kids
            n.pop("children", None)
            # autoLayout 은 master 가 가지므로 wrapper 의 autoLayout 은 제거
            # (사이즈만 유지 — parent FILL/HUG 컨텍스트는 그대로)
            n.pop("autoLayout", None)
            n.pop("layoutMode", None)
            n.pop("stroke", None)
            n.pop("strokes", None)
            n.pop("strokeWeight", None)
            n.pop("strokeTopWeight", None)
            n.pop("strokeBottomWeight", None)
            n.pop("strokeLeftWeight", None)
            n.pop("strokeRightWeight", None)
            n.pop("padding", None)
            for p in ("paddingTop", "paddingBottom", "paddingLeft", "paddingRight"):
                n.pop(p, None)
            fixed += 1
            return  # 인스턴스 안으로는 재귀 안 함
        for c in n.get("children") or []:
            _walk(c)

    _walk(bp)
    if fixed:
        print(f"[inject R60] Mode Tabs raw frame → DS Horizontal Tabs instance: {fixed}건")
    return bp


# ── L4 post-fix (built tree) ──────────────────────────────────────

def _autofix(tree: dict, ctx: dict) -> int:
    """built instance 내부 TEXT 노드에 _tabLabels 순서대로 텍스트 적용.

    blueprint 의 _tabLabels / _tabActiveIndex 가 built tree 에는 메타로 박힘.
    DS Tabs 의 internal text node 들을 findAll + sort + set_text_content.
    """
    import importlib, sys
    fmc = sys.modules.get("figma_mcp_client")
    if fmc is None:
        try:
            fmc = importlib.import_module("figma_mcp_client")
        except ImportError:
            return 0

    fixes = 0

    def _walk(n):
        nonlocal fixes
        if not isinstance(n, dict): return
        is_instance = (n.get("type") or "").upper() == "INSTANCE"
        labels = n.get("_tabLabels") or []
        if is_instance and labels and n.get("id"):
            node_id = n["id"]
            try:
                content = fmc.call_tool("scan_text_nodes", {"nodeId": node_id})
                result = fmc.parse_content(content)
                data = result.get("json") or {}
                text_nodes = data.get("nodes") or data.get("textNodes") or []
                # Sort by x then y (visual reading order)
                text_nodes.sort(key=lambda t: (t.get("x") or 0, t.get("y") or 0))
                # Apply labels in order
                for i, label in enumerate(labels):
                    if i < len(text_nodes) and label:
                        tid = text_nodes[i].get("id")
                        if not tid: continue
                        try:
                            fmc.call_tool("set_text_content", {
                                "nodeId": tid,
                                "text": str(label),
                            })
                            fixes += 1
                        except Exception as e:
                            print(f"  ⚠️ R60 set_text_content 실패 ({label}): {e}")
                print(f"  R60 Tabs instance: '{n.get('name')}' 라벨 {len(labels)}개 매핑")
            except Exception as e:
                print(f"  ⚠️ R60 scan_text_nodes 실패: {e}")
        for c in n.get("_children_full") or n.get("children") or []:
            _walk(c)

    _walk(tree)
    return fixes


# ── L5 verify (built tree) ────────────────────────────────────────

def _verify(tree: dict, ctx: dict) -> Iterable[Violation]:
    """built tree 의 tab nav wrapper 가 instance 인지 확인."""
    for node, path in walk_tree(tree):
        name = (node.get("name") or "").lower().strip()
        if not any(h in name for h in _TAB_NAV_HINTS):
            continue
        ntype = (node.get("type") or "").upper()
        if ntype != "INSTANCE":
            yield Violation(
                "R60-tabs-ds-instance",
                Severity.ERROR,
                path,
                (f"tab nav '{node.get('name')}' built as {ntype} — "
                 f"should be INSTANCE of DS Horizontal Tabs (Underline)."),
                Phase.VERIFY,
            )


register(Rule(
    rule_id="R60-tabs-ds-instance",
    title="Tab nav (2+ text tabs) must be a DS Horizontal Tabs instance, not a raw frame",
    description=(
        "HORIZONTAL frames named 'Mode Tabs Wrap' / 'Section Tabs' / 'Top Tabs' "
        "/ 'Tabs Wrap' / 'Tabs Row' with 2~6 text-only tab cells must be "
        "swapped for a DS 'Horizontal tabs' instance (Underline variant). "
        "Inject auto-swaps and post-fix maps tab labels into the instance's "
        "internal TEXT nodes."
    ),
    check_blueprint_fn=_check_blueprint,
    inject_blueprint_fn=_inject,
    auto_fix_built_fn=_autofix,
    check_built_fn=_verify,
))
