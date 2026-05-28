"""R42 — drop-shadow clearance.

그림자(DROP_SHADOW)가 달린 프레임(카드)은 부모 안에서 그림자가 잘리거나
인접 형제에 덮이지 않도록 충분한 여백이 필요하다.

증상: 섹션 래퍼의 paddingBottom=0 → 카드 그림자(~12px)가 다음 섹션의
불투명 배경에 덮여 "그림자가 잘려 보임".

INJECT (빌드 전 자동 보정):
  • 그림자 자식을 가진 부모 autoLayout 의 padding 4면을 그림자 extent 이상으로
  • 그림자 자식들이 늘어선 부모의 itemSpacing 을 그림자 extent 이상으로
  • 그림자 노드의 조상 중 clipsContent=true 인 프레임을 false 로
    (단, 가로 캐로셀 — HORIZONTAL+clipsContent — 은 의도적 클립이므로 보존)

VERIFY (빌드 후 검사): 그림자 노드의 부모 padding 이 extent 미만이면 WARN.
"""
from __future__ import annotations

import math
from typing import Iterable

from .base import Phase, Rule, Severity, Violation, register, walk_blueprint


def _drop_shadows(node: dict) -> list:
    out = []
    for e in node.get("effects") or []:
        if e.get("type") == "DROP_SHADOW" and e.get("visible", True):
            out.append(e)
    return out


def _extents(node: dict):
    """노드 그림자의 (top, right, bottom, left) 여백 필요량 — ceil."""
    top = right = bottom = left = 0.0
    for e in _drop_shadows(node):
        r = e.get("radius", 0) or 0
        s = e.get("spread", 0) or 0
        off = e.get("offset") or {}
        ox = off.get("x", 0) or 0
        oy = off.get("y", 0) or 0
        bottom = max(bottom, r + s + max(0, oy))
        top = max(top, r + s + max(0, -oy))
        right = max(right, r + s + max(0, ox))
        left = max(left, r + s + max(0, -ox))
    return (math.ceil(top), math.ceil(right), math.ceil(bottom), math.ceil(left))


def _inject(bp: dict) -> dict:
    # 1) 그림자 자식을 가진 부모의 padding / itemSpacing 보정
    for node, _path in walk_blueprint(bp):
        kids = node.get("children") or []
        al = node.get("autoLayout")
        if not kids or not al:
            continue
        T = R = B = L = 0
        any_shadow = False
        for c in kids:
            t, r, b, l = _extents(c)
            if t or r or b or l:
                any_shadow = True
            T, R, B, L = max(T, t), max(R, r), max(B, b), max(L, l)
        if not any_shadow:
            continue
        al["paddingTop"] = max(al.get("paddingTop", 0) or 0, T)
        al["paddingBottom"] = max(al.get("paddingBottom", 0) or 0, B)
        al["paddingLeft"] = max(al.get("paddingLeft", 0) or 0, L)
        al["paddingRight"] = max(al.get("paddingRight", 0) or 0, R)
        mode = al.get("layoutMode") or al.get("direction")
        if mode == "VERTICAL":
            al["itemSpacing"] = max(al.get("itemSpacing", 0) or 0, B)
        elif mode == "HORIZONTAL":
            al["itemSpacing"] = max(al.get("itemSpacing", 0) or 0, R)

    # 2) 그림자 노드의 조상 clipsContent 해제 (가로 캐로셀 제외)
    def _unclip(node: dict, ancestors: list):
        if _drop_shadows(node):
            for anc in ancestors:
                al = anc.get("autoLayout") or {}
                mode = al.get("layoutMode") or al.get("direction")
                is_h_clipper = mode == "HORIZONTAL" and anc.get("clipsContent")
                if anc.get("clipsContent") and not is_h_clipper:
                    anc["clipsContent"] = False
        for c in node.get("children") or []:
            _unclip(c, ancestors + [node])

    _unclip(bp, [])
    return bp


def _check_built(tree: dict, ctx: dict) -> Iterable[Violation]:
    def walk(node, path, parent):
        if _drop_shadows(node) and parent is not None:
            t, r, b, l = _extents(node)
            pt = parent.get("paddingTop", 0) or 0
            pb = parent.get("paddingBottom", 0) or 0
            pl = parent.get("paddingLeft", 0) or 0
            pr = parent.get("paddingRight", 0) or 0
            short = []
            if pt < t: short.append(f"top {pt}<{t}")
            if pb < b: short.append(f"bottom {pb}<{b}")
            if pl < l: short.append(f"left {pl}<{l}")
            if pr < r: short.append(f"right {pr}<{r}")
            if short:
                yield Violation(
                    "R42-shadow-clearance", Severity.WARN, path,
                    f"shadowed frame's parent padding too small ({', '.join(short)}) "
                    f"— shadow will be clipped/occluded",
                    Phase.VERIFY,
                )
        for c in node.get("children") or []:
            yield from walk(c, f"{path}/{c.get('name', '?')}", node)

    yield from walk(tree, tree.get("name", "root"), None)


register(Rule(
    rule_id="R42-shadow-clearance",
    title="drop-shadow clearance",
    description="그림자 카드는 부모 padding/itemSpacing 으로 그림자 여백 확보, "
                "조상 clipsContent 해제 (가로 캐로셀 제외).",
    inject_blueprint_fn=_inject,
    check_built_fn=_check_built,
))
