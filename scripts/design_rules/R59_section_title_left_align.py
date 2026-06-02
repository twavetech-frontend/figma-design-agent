"""R59 — Section title 텍스트는 왼쪽 정렬 (2026-06-01 사용자 룰).

사용자 명시: "다른 섹션들은 그렇게 되어 있는데 왜 이것만 중앙으로 배치했는지
이해가 되지 않는다." — 섹션 헤더/타이틀 텍스트는 일관성을 위해 항상 좌측 정렬.

두 가지 패턴이 중앙 정렬을 만들어내는 것을 잡는다:

1. **명시적 CENTER 박힘**: TEXT 노드에 직접 `textAlignHorizontal: "CENTER"` 가 박혀 있음.
   → blueprint 작성 실수. inject 단계에서 LEFT 로 교정.

2. **`primaryAxisAlignItems: SPACE_BETWEEN` + 자식 1개**: HORIZONTAL row 가
   SPACE_BETWEEN 인데 자식이 1개뿐이면 Figma 는 그 자식을 row 의 정중앙에 배치한다.
   다른 섹션의 Title Row 들이 우측에 CTA(예: "전체 보기", 예치금 라벨) 자식을 가져
   좌우 분배가 되는 것과 일관성을 맞추려면 single child 일 땐 MIN(=시작 정렬) 로 바꿔야 한다.
   → inject 단계에서 SPACE_BETWEEN → MIN 교정.

스코프 — 섹션 타이틀로 인식되는 텍스트만 잡는다:
  • 부모 frame name 이 "*Title Row" / "*Title" / "*Header Row"
  • 또는 텍스트 노드 자체의 name 이 "* Title" / "*-title" / "section-title"
"""
from __future__ import annotations

from typing import Iterable

from .base import Phase, Rule, Severity, Violation, register, walk_blueprint, walk_tree


# ── Detection helpers ─────────────────────────────────────────────
#
# 2026-06-01 사용자 피드백: "갑자기 모든 정렬이 왼쪽 정렬로 고정된거 같다. 아까 내가
# 말한건 섹션 타이틀만 왼쪽 정렬이어야 한다는거였어"
# → scope 좁힘:
#   • 'title row' / 'header row' frame 의 직계 TEXT 자식만 잡는다 (TEXT name 매칭은 제거)
#   • ancestor 가 카드/Empty 등 컨텐츠 컨테이너면 제외 — 카드 내부는 무관
#   • TEXT 의 fontSize ≥ 15 만 — 작은 body/label 텍스트 제외
#   • 'Title Row' / 'Header Row' frame 도 ancestor 가 카드/Empty 안이면 SPACE_BETWEEN 변환 안 함

_TITLE_PARENT_NAME_HINTS = ("title row", "header row")

# ancestor 이름에 이 패턴이 있으면 "내부 컨텐츠" 컨텍스트 → R59 스킵
# ⚠️ "card" 는 의도적으로 제외 — "Day Strip Title" 처럼 카드 안에 있어도 사용자가
# "섹션 타이틀" 로 인식하는 경우가 있음 (첫 사용자 요청). 대신 "empty"/"modal" 등
# 명확한 inner 컨텐츠 컨테이너만 스킵 — empty state 안내 텍스트가 LEFT 강제되지 않도록.
_CONTENT_CONTAINER_HINTS = (
    "empty",      # Stage Empty / Cal Empty / 빈 상태 안내
    "modal",      # 모달 안
    "dialog",
    "sheet",
    "popover",
    "tooltip",
)

# section-title 로 인정하는 최소 fontSize — body/label 텍스트 차단
_MIN_TITLE_FONT_SIZE = 15


def _ancestor_is_content_container(ancestors: list[dict]) -> bool:
    """ancestor chain 에 'card'/'empty'/'modal' 등 컨텐츠 컨테이너 이름이 있으면 True."""
    for a in ancestors:
        name = (a.get("name") or "").lower()
        for h in _CONTENT_CONTAINER_HINTS:
            if h in name:
                return True
    return False


def _font_size(node: dict) -> float:
    fs = node.get("fontSize")
    try:
        return float(fs) if fs is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _is_section_title_text(node: dict, parent: dict | None = None, ancestors: list[dict] | None = None) -> bool:
    """section title TEXT 인지 — 좁혀진 scope.

    조건 (모두 만족):
      1. type == TEXT
      2. fontSize ≥ 15 (작은 본문 텍스트 제외)
      3. parent name 이 'title row' / 'header row' 패턴
      4. ancestor 에 'card'/'empty'/'modal' 등 컨텐츠 컨테이너 없음
    """
    if (node.get("type") or "").lower() != "text":
        return False
    if _font_size(node) < _MIN_TITLE_FONT_SIZE:
        return False
    if not parent:
        return False
    pname = (parent.get("name") or "").lower()
    if not any(h in pname for h in _TITLE_PARENT_NAME_HINTS):
        return False
    # ancestor 컨텍스트 검사
    if ancestors and _ancestor_is_content_container(ancestors):
        return False
    return True


def _is_title_row(node: dict, ancestors: list[dict] | None = None) -> bool:
    """node 가 섹션 타이틀 Row 인지 — 카드 내부면 제외."""
    if (node.get("type") or "").lower() != "frame":
        return False
    name = (node.get("name") or "").lower()
    if not any(h in name for h in _TITLE_PARENT_NAME_HINTS):
        return False
    al = node.get("autoLayout") or {}
    if (al.get("layoutMode") or node.get("layoutMode")) != "HORIZONTAL":
        return False
    # 카드 내부면 R59 스킵 (카드 내 헤더는 디자인 의도가 다를 수 있음)
    if ancestors and _ancestor_is_content_container(ancestors):
        return False
    return True


# ── L2 lint (blueprint) ───────────────────────────────────────────

def _check_blueprint(bp: dict, ctx: dict) -> Iterable[Violation]:
    # walk_blueprint 는 ancestors 미제공 → 자체 traversal
    def _walk(n, parent=None, ancestors=None, path=""):
        ancestors = ancestors or []
        if not isinstance(n, dict):
            return
        name = n.get("name", "?")
        cur_path = f"{path}/{name}" if path else name
        if _is_section_title_text(n, parent, ancestors):
            if n.get("textAlignHorizontal") == "CENTER":
                yield Violation(
                    "R59-section-title-left",
                    Severity.WARN,
                    cur_path,
                    (f"section title TEXT '{n.get('name')}' has "
                     f"textAlignHorizontal=CENTER — should be LEFT. "
                     f"Inject will fix."),
                    Phase.LINT,
                )
        if _is_title_row(n, ancestors):
            al = n.get("autoLayout") or {}
            align = al.get("primaryAxisAlignItems") or n.get("primaryAxisAlignItems")
            kids = n.get("children") or []
            if align == "SPACE_BETWEEN" and len(kids) <= 1:
                yield Violation(
                    "R59-section-title-left",
                    Severity.WARN,
                    cur_path,
                    (f"title row '{n.get('name')}' has SPACE_BETWEEN with "
                     f"{len(kids)} child(ren) → Figma will CENTER the single "
                     f"child. Inject will switch to MIN."),
                    Phase.LINT,
                )
        new_ancestors = ancestors + [n]
        for c in n.get("children") or []:
            yield from _walk(c, n, new_ancestors, cur_path)

    yield from _walk(bp)


# ── L3 inject (blueprint) ─────────────────────────────────────────

def _inject(bp: dict) -> dict:
    """Pre-build: textAlignHorizontal=CENTER on title TEXT → LEFT.
    SPACE_BETWEEN single-child title rows → MIN.

    scope: card/empty/modal 등 컨텐츠 컨테이너 안의 텍스트는 제외 (2026-06-01 사용자 피드백).
    """
    fixed_text = 0
    fixed_row = 0

    def _walk(n, parent=None, ancestors=None):
        nonlocal fixed_text, fixed_row
        ancestors = ancestors or []
        if not isinstance(n, dict):
            return
        if _is_section_title_text(n, parent, ancestors):
            if n.get("textAlignHorizontal") == "CENTER":
                n["textAlignHorizontal"] = "LEFT"
                fixed_text += 1
        if _is_title_row(n, ancestors):
            al = n.get("autoLayout")
            kids = n.get("children") or []
            if isinstance(al, dict):
                if al.get("primaryAxisAlignItems") == "SPACE_BETWEEN" and len(kids) <= 1:
                    al["primaryAxisAlignItems"] = "MIN"
                    fixed_row += 1
            elif (n.get("primaryAxisAlignItems") == "SPACE_BETWEEN"
                  and len(kids) <= 1):
                n["primaryAxisAlignItems"] = "MIN"
                fixed_row += 1
        new_ancestors = ancestors + [n]
        for c in n.get("children") or []:
            _walk(c, n, new_ancestors)

    _walk(bp)
    if fixed_text or fixed_row:
        print(f"  ✓ R59 inject: section-title textAlign CENTER→LEFT {fixed_text}건, "
              f"title row SPACE_BETWEEN→MIN {fixed_row}건")
    return bp


# ── L4 post-fix (built tree) ──────────────────────────────────────

def _autofix(tree: dict, ctx: dict) -> int:
    """Built-tree post-fix: figma plugin 호출해 textAlignHorizontal=LEFT 설정.
    SPACE_BETWEEN single-child row 는 set_auto_layout 으로 MIN 변경.
    """
    import importlib, sys
    fmc = sys.modules.get("figma_mcp_client")
    if fmc is None:
        try:
            fmc = importlib.import_module("figma_mcp_client")
        except ImportError:
            return 0

    fixes = 0

    def _walk(n, parent=None, ancestors=None):
        nonlocal fixes
        ancestors = ancestors or []
        if not isinstance(n, dict):
            return
        node_id = n.get("id")
        if _is_section_title_text(n, parent, ancestors) and node_id:
            if n.get("textAlignHorizontal") == "CENTER":
                try:
                    fmc.call_tool("set_text_align", {
                        "nodeId": node_id,
                        "textAlignHorizontal": "LEFT",
                    })
                    print(f"  R59 section-title: '{n.get('name')}' align CENTER→LEFT")
                    fixes += 1
                except Exception as e:
                    print(f"  ⚠️ R59 set_text_align 실패 ({n.get('name')}): {e}")
        if _is_title_row(n, ancestors) and node_id:
            kids = n.get("_children_full") or n.get("children") or []
            if (n.get("primaryAxisAlignItems") == "SPACE_BETWEEN"
                    and len(kids) <= 1):
                try:
                    fmc.call_tool("set_auto_layout", {
                        "nodeId": node_id,
                        "layoutMode": "HORIZONTAL",
                        "primaryAxisAlignItems": "MIN",
                    })
                    print(f"  R59 title-row: '{n.get('name')}' SPACE_BETWEEN→MIN")
                    fixes += 1
                except Exception as e:
                    print(f"  ⚠️ R59 set_auto_layout 실패 ({n.get('name')}): {e}")
        new_ancestors = ancestors + [n]
        for c in n.get("_children_full") or n.get("children") or []:
            _walk(c, n, new_ancestors)

    _walk(tree)
    return fixes


# ── L5 verify (built tree) ────────────────────────────────────────

def _verify(tree: dict, ctx: dict) -> Iterable[Violation]:
    def _walk(n, parent=None, ancestors=None):
        ancestors = ancestors or []
        if not isinstance(n, dict):
            return
        if _is_section_title_text(n, parent, ancestors):
            align = n.get("textAlignHorizontal")
            if align == "CENTER":
                yield Violation(
                    "R59-section-title-left",
                    Severity.WARN,
                    f"…/{n.get('name')}",
                    f"section title still CENTER aligned post-fix",
                    Phase.VERIFY,
                )
        if _is_title_row(n, ancestors):
            kids = n.get("_children_full") or n.get("children") or []
            if (n.get("primaryAxisAlignItems") == "SPACE_BETWEEN"
                    and len(kids) <= 1):
                yield Violation(
                    "R59-section-title-left",
                    Severity.WARN,
                    f"…/{n.get('name')}",
                    f"title row still SPACE_BETWEEN with single child",
                    Phase.VERIFY,
                )
        new_ancestors = ancestors + [n]
        for c in n.get("_children_full") or n.get("children") or []:
            yield from _walk(c, n, new_ancestors)

    yield from _walk(tree)


register(Rule(
    rule_id="R59-section-title-left",
    title="Section title TEXT is left-aligned (no CENTER, no SPACE_BETWEEN single child)",
    description=(
        "Section title TEXT nodes (name ends with 'title' / parent name "
        "contains 'Title Row' / 'Header Row') must use textAlignHorizontal=LEFT. "
        "Title rows with SPACE_BETWEEN and a single child are auto-corrected "
        "to MIN, since Figma centers a single SPACE_BETWEEN child."
    ),
    check_blueprint_fn=_check_blueprint,
    inject_blueprint_fn=_inject,
    auto_fix_built_fn=_autofix,
    check_built_fn=_verify,
))
