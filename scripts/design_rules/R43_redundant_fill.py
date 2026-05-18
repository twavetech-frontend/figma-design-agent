"""R43 — redundant layout-frame fill.

부모와 똑같은 색으로 채워진 순수 레이아웃 래퍼 프레임은 fill 이 불필요하다.
부모 배경이 그대로 비치므로 채우면 중복이고, 토큰 변경 시 불일치 위험만 늘린다.

대상: autoLayout 을 가진 "순수 레이아웃 프레임" — cornerRadius/stroke/effects 가
없어 시각적으로 구분되는 표면(카드)이 아닌 그룹핑 전용 프레임.
이런 프레임의 fill 이 가장 가까운 조상의 유효 배경색과 같으면 fill 을 제거한다.

카드(cornerRadius·stroke·그림자 중 하나라도 있음)는 같은 색이라도 독립 표면이므로 유지.

INJECT: 중복 fill 제거.  VERIFY: 빌드 트리에서 중복 fill 발견 시 WARN.
"""
from __future__ import annotations

from typing import Iterable

from .base import Phase, Rule, Severity, Violation, register


def _same_fill(a, b) -> bool:
    if a is None or b is None:
        return False
    if isinstance(a, str) and isinstance(b, str):
        return a.strip() == b.strip()
    if isinstance(a, dict) and isinstance(b, dict):
        keys = ("r", "g", "b", "a")
        return all(abs((a.get(k, 0) or 0) - (b.get(k, 0) or 0)) < 1e-4 for k in keys)
    return False


def _is_pure_layout_frame(node: dict) -> bool:
    """카드가 아닌 순수 레이아웃/그룹핑 프레임인가."""
    if node.get("type") not in (None, "frame", "FRAME"):
        return False
    if not node.get("autoLayout"):
        return False
    if node.get("cornerRadius") or node.get("topLeftRadius"):
        return False
    if node.get("stroke") or node.get("strokes"):
        return False
    if node.get("effects"):
        return False
    return True


def _inject(bp: dict) -> dict:
    def walk(node: dict, parent_eff_fill, is_root: bool):
        node_fill = node.get("fill")
        eff = node_fill if node_fill is not None else parent_eff_fill
        if (not is_root and node_fill is not None
                and _is_pure_layout_frame(node)
                and _same_fill(node_fill, parent_eff_fill)):
            del node["fill"]
            eff = parent_eff_fill
        for c in node.get("children") or []:
            walk(c, eff, False)

    walk(bp, None, True)
    return bp


def _check_built(tree: dict, ctx: dict) -> Iterable[Violation]:
    def fill_of(node):
        fills = node.get("fills")
        if isinstance(fills, list) and fills:
            fl = fills[0]
            if fl.get("type") == "SOLID" and fl.get("visible", True):
                # 완전 투명 fill 은 사실상 fill 없음 — 제외
                if (fl.get("opacity", 1) or 0) <= 0.001:
                    return None
                color = fl.get("color") or {}
                if (color.get("a", 1) or 0) <= 0.001:
                    return None
                return color
        return None

    def walk(node, path, parent_eff):
        node_fill = fill_of(node)
        eff = node_fill if node_fill is not None else parent_eff
        if (node_fill is not None and parent_eff is not None
                and _is_pure_layout_frame_built(node)
                and _same_fill(node_fill, parent_eff)):
            yield Violation(
                "R43-redundant-fill", Severity.WARN, path,
                "pure layout frame filled with the same color as its parent "
                "— fill is redundant, should be transparent",
                Phase.VERIFY,
            )
        for c in node.get("children") or []:
            yield from walk(c, f"{path}/{c.get('name', '?')}", eff)

    yield from walk(tree, tree.get("name", "root"), None)


def _is_pure_layout_frame_built(node: dict) -> bool:
    """빌드 트리 버전 — cornerRadius/strokes/effects 없는 auto-layout 프레임."""
    if node.get("type") not in ("FRAME", "frame"):
        return False
    if not (node.get("layoutMode") and node.get("layoutMode") != "NONE"):
        return False
    if node.get("cornerRadius") or node.get("topLeftRadius"):
        return False
    if node.get("strokes"):
        return False
    if node.get("effects"):
        return False
    return True


register(Rule(
    rule_id="R43-redundant-fill",
    title="redundant layout-frame fill",
    description="부모와 동일 색으로 채운 순수 레이아웃 래퍼 프레임의 fill 제거 "
                "(카드는 cornerRadius/stroke/effects 로 구분되므로 예외).",
    inject_blueprint_fn=_inject,
    check_built_fn=_check_built,
))
