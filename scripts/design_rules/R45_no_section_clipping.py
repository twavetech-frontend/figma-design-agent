"""R45 — 섹션/카드 frame 의 clipsContent=false 강제 (2026-05-24 사용자 분노).

Rule (from user, 2026-05-24):
  "섹션 autolayout frame의 clip content 옵션은 체크하지마. dropshadow나 가로 스크롤
  같은게 제대로 안보이게 되잖아."

Figma는 frame 생성 시 default `clipsContent=true`. 섹션이 clip 되면:
  - 카드 drop shadow 가 frame 경계에서 잘림
  - 가로 carousel 마지막 카드 peek 이 안 보임(R36 룰과 충돌)
  - ABSOLUTE tooltip 같은 자식이 부모 밖으로 못 나옴

Exception:
  - 이름에 'carousel'/'banner row'/'hero row'/'scroll row'/'carousel wrap' 포함된
    HORIZONTAL frame 은 viewport clip 의도라 유지.
  - root frame 은 viewport 자체 — 건드리지 않음.

Phases:
  L4 post-fix  — `_disable_section_clipping(root_id)` 가 빌드 후 트리 walk 하면서
                 비-carousel FRAME 의 clipsContent=true 를 false 로 일괄 강제.
                 batch_execute 로 한 번에 처리.
  L5 verify    — built tree 에 carousel 외 clipsContent=true 인 FRAME 있으면 WARN.
"""
from __future__ import annotations

from typing import Iterable

from .base import Phase, Rule, Severity, Violation, register


_CAROUSEL_KEYWORDS = ("carousel", "banner row", "hero row", "scroll row", "carousel wrap")


def _is_carousel_wrapper(node: dict) -> bool:
    nm = (node.get("name") or "").lower()
    return any(k in nm for k in _CAROUSEL_KEYWORDS)


def _wrap_disable_clipping(tree: dict, ctx: dict) -> int:
    """후처리 함수는 figma_mcp_client 의 실제 fix 함수에 위임."""
    import importlib
    import sys
    if "figma_mcp_client" not in sys.modules:
        import scripts  # noqa: F401
    mod = importlib.import_module("figma_mcp_client")
    root_id = ctx.get("root_id") or tree.get("id")
    if not root_id:
        return 0
    return mod._disable_section_clipping(root_id)


def _check_built(tree: dict, ctx: dict) -> Iterable[Violation]:
    """빌드 후 검증 — carousel 외 frame 이 clipsContent=true 면 WARN."""
    def walk(node, depth, path="root"):
        if depth > 0 and node.get("type") == "FRAME":
            if node.get("clipsContent") is True and not _is_carousel_wrapper(node):
                yield Violation(
                    rule_id="R45-no-section-clipping",
                    severity=Severity.WARN,
                    path=f"{path}/{node.get('name', '?')}",
                    message=(
                        "Section frame still has clipsContent=true — drop shadow / "
                        "carousel peek will be cropped. Post-fix should have cleared it."
                    ),
                    phase=Phase.VERIFY,
                )
        for i, c in enumerate(node.get("children", []) or []):
            yield from walk(c, depth + 1, f"{path}/{c.get('name', f'child[{i}]')}")
    yield from walk(tree, 0)


register(Rule(
    rule_id="R45-no-section-clipping",
    title="Section/card frame clipsContent=false (carousel excepted)",
    description=(
        "Figma defaults new frames to clipsContent=true. For sections this clips "
        "card drop shadows and horizontal carousel peeks. R45 force-disables "
        "clipsContent on every FRAME except carousel-like wrappers (named "
        "'carousel'/'banner row'/'hero row'/'scroll row'/'carousel wrap') and "
        "the root viewport itself."
    ),
    auto_fix_built_fn=_wrap_disable_clipping,
    check_built_fn=_check_built,
))
